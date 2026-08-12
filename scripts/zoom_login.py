"""봇 계정 Zoom 로그인 → 프로필 + 쿠키 파일(data/zoom_cookies.json) 양쪽에 세션을 남긴다.

프로필만 믿으면 안 된다(실측: 브라우저 종료 후 세션이 날아간 적 있음). 쿠키를 따로
덤프해 두고, zoom_bot 이 기동 시 주입한다.

사용법:
  python3 scripts/zoom_login.py            # OTP 필요 시 data/otp.txt 를 기다린다
  관리자 화면의 '인증 코드 전송'            # 웹 버튼으로 코드 투입
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright  # noqa: E402

from app import bot_login, config  # noqa: E402

OTP_FILE = config.DATA / "otp.txt"
COOKIES = config.DATA / "zoom_cookies.json"
CREDENTIALS_FILE = Path(os.getenv("AZ_ZOOM_CREDENTIALS_FILE",
                                  str(config.DATA / "zoom-login.env")))
DISPLAY = os.getenv("AZ_LOGIN_DISPLAY", ":96")


def credentials() -> tuple[str, str]:
    """환경변수 또는 vault 전용 파일에서만 봇 계정 자격 증명을 읽는다."""
    values: dict[str, str] = {}
    try:
        for line in CREDENTIALS_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() in {"AZ_ZOOM_EMAIL", "AZ_ZOOM_PASSWORD"}:
                values[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
    email = os.getenv("AZ_ZOOM_EMAIL") or values.get("AZ_ZOOM_EMAIL", "")
    password = os.getenv("AZ_ZOOM_PASSWORD") or values.get("AZ_ZOOM_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("Zoom 봇 계정 자격 증명이 vault에 없습니다.")
    return email, password


def click_any(p, names, timeout=6000) -> bool:
    for nm in names:
        for loc in (lambda n=nm: p.get_by_role("button", name=n, exact=True).first,
                    lambda n=nm: p.locator(f"button:has-text('{n}')").first):
            try:
                loc().click(timeout=timeout / 2)
                print(f"  '{nm}' 클릭", flush=True)
                return True
            except Exception:
                pass
    return False


def logged_in(p) -> bool:
    """Zoom 프로필의 실제 로그인 UI로 판정한다(URL만 보면 오인할 수 있다)."""
    try:
        body = re.sub(r"\s+", " ", p.inner_text("body"))
    except Exception:
        return False
    account_ui = ("My Account" in body or "내 계정" in body) and (
        "Profile Page" in body or "프로필 설정" in body)
    signin_ui = bool(re.search(r"(^|\s)(로그인|Sign In)(\s|$)", body, re.I))
    return "signin" not in p.url.lower() and account_ui and not signin_ui


def main() -> int:
    lock = bot_login.acquire_lock()
    if lock is None:
        bot_login.set_status("busy", "다른 봇 계정 로그인 작업이 실행 중입니다.")
        return 3
    xvfb = None
    OTP_FILE.unlink(missing_ok=True)
    try:
        email, password = credentials()
        bot_login.set_status("running", "Zoom 로그인 페이지를 열고 있습니다.", pid=os.getpid())
        env = dict(os.environ)
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
        env["DISPLAY"] = DISPLAY
        xvfb = subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        if xvfb.poll() is not None:
            raise RuntimeError(f"Xvfb를 시작하지 못했습니다 (종료 코드 {xvfb.returncode}).")
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                str(config.PROFILE_DIR), channel="chromium", headless=False, env=env,
                user_agent=config.USER_AGENT, locale=config.LOCALE,
                timezone_id=config.TIMEZONE, viewport={"width": 1280, "height": 800},
                args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage"])
            p = ctx.pages[0] if ctx.pages else ctx.new_page()
            body = lambda: re.sub(r"\s+", " ", p.inner_text("body"))  # noqa: E731

            p.goto("https://zoom.us/profile", wait_until="domcontentloaded", timeout=45000)
            p.wait_for_timeout(6000)
            if logged_in(p):
                print("이미 로그인 상태", flush=True)
            else:
                p.goto("https://zoom.us/signin", wait_until="domcontentloaded", timeout=45000)
                p.wait_for_timeout(5000)
                click_any(p, ["모든 쿠키 허용"], 3000)
                p.wait_for_timeout(800)
                p.locator("input[type=email], #email").first.fill(email, timeout=10000)
                click_any(p, ["다음", "Next"])
                p.wait_for_timeout(6000)
                p.locator("input[type=password]").first.fill(password, timeout=15000)
                # '로그인 상태 유지' 류 체크박스가 있으면 켠다(세션 지속용).
                for lbl in ("로그인 상태 유지", "Stay signed in", "이 장치 기억"):
                    try:
                        p.get_by_label(re.compile(lbl)).first.check(timeout=2500)
                        print(f"  '{lbl}' 체크", flush=True)
                        break
                    except Exception:
                        pass
                click_any(p, ["로그인", "Sign In"])
                p.wait_for_timeout(12000)

                if "otp" in p.url or "일회용 암호" in body():
                    print("OTP 필요 — data/otp.txt 대기중", flush=True)
                    bot_login.set_status("otp_required", "Zoom 인증 코드를 입력해 주세요.",
                                         pid=os.getpid())
                    code = None
                    for _ in range(220):
                        if OTP_FILE.exists():
                            c = OTP_FILE.read_text().strip()
                            if re.fullmatch(r"\d{4,8}", c):
                                code = c
                                break
                        time.sleep(3)
                    if not code:
                        print("OTP 타임아웃", flush=True)
                        bot_login.set_status("failed", "인증 코드 입력 시간이 지났습니다.")
                        return 2
                    print("OTP 수신", flush=True)
                    bot_login.set_status("verifying", "인증 코드를 확인하고 있습니다.",
                                         pid=os.getpid())
                    # OTP 는 <input> 이 아니라 contenteditable 6칸이다(실측).
                    boxes = p.locator("[contenteditable]")
                    for i, ch in enumerate(code):
                        try:
                            boxes.nth(i).click(timeout=4000)
                        except Exception:
                            pass
                        p.keyboard.type(ch, delay=120)
                        p.wait_for_timeout(220)
                    if not click_any(p, ["확인", "Verify", "제출"]):
                        p.keyboard.press("Enter")
                    p.wait_for_timeout(14000)

                p.goto("https://zoom.us/profile", wait_until="domcontentloaded", timeout=45000)
                p.wait_for_timeout(7000)
                if not logged_in(p):
                    print("로그인 실패", flush=True)
                    bot_login.set_status("failed", "Zoom 계정 로그인이 완료되지 않았습니다.")
                    return 1

            state = ctx.storage_state()
            zoom = [c for c in state.get("cookies", []) if "zoom.us" in c.get("domain", "")]
            COOKIES.write_text(json.dumps(zoom, ensure_ascii=False), encoding="utf-8")
            COOKIES.chmod(0o600)
            sess = sum(1 for c in zoom if not c.get("expires") or c["expires"] < 0)
            print(f"로그인 성공 — zoom 쿠키 {len(zoom)}개 저장 (세션쿠키 {sess}개) → {COOKIES}",
                  flush=True)
            bot_login.set_status("success", "Zoom 봇 계정 로그인 확인과 세션 저장이 완료되었습니다.")
            return 0
    except Exception as e:  # noqa: BLE001
        print(f"로그인 실패: {type(e).__name__}: {e}", flush=True)
        bot_login.set_status("failed", "로그인에 실패했습니다. 관리자 로그를 확인해 주세요.")
        return 1
    finally:
        OTP_FILE.unlink(missing_ok=True)
        if xvfb and xvfb.poll() is None:
            xvfb.terminate()
            try:
                xvfb.wait(timeout=5)
            except subprocess.TimeoutExpired:
                xvfb.kill()
        bot_login.release_lock(lock)


if __name__ == "__main__":
    raise SystemExit(main())
