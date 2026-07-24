"""봇 계정 Zoom 로그인 → 프로필 + 쿠키 파일(data/zoom_cookies.json) 양쪽에 세션을 남긴다.

프로필만 믿으면 안 된다(실측: 브라우저 종료 후 세션이 날아간 적 있음). 쿠키를 따로
덤프해 두고, zoom_bot 이 기동 시 주입한다.

사용법:
  python3 scripts/zoom_login.py            # OTP 필요 시 data/otp.txt 를 기다린다
  echo 123456 > data/otp.txt               # 다른 셸에서 코드 투입
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

from app import config  # noqa: E402

EMAIL = os.getenv("AZ_ZOOM_EMAIL", "arconomics1@gmail.com")
PW = os.getenv("AZ_ZOOM_PASSWORD", "Hh07290729!")
OTP_FILE = config.DATA / "otp.txt"
COOKIES = config.DATA / "zoom_cookies.json"
DISPLAY = os.getenv("AZ_LOGIN_DISPLAY", ":96")


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


def main() -> int:
    OTP_FILE.unlink(missing_ok=True)
    env = dict(os.environ)
    env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    env["DISPLAY"] = DISPLAY
    xvfb = subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    try:
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
            if "signin" not in p.url:
                print("이미 로그인 상태", flush=True)
            else:
                p.goto("https://zoom.us/signin", wait_until="domcontentloaded", timeout=45000)
                p.wait_for_timeout(5000)
                click_any(p, ["모든 쿠키 허용"], 3000)
                p.wait_for_timeout(800)
                p.locator("input[type=email], #email").first.fill(EMAIL, timeout=10000)
                click_any(p, ["다음", "Next"])
                p.wait_for_timeout(6000)
                p.locator("input[type=password]").first.fill(PW, timeout=15000)
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
                        ctx.close()
                        return 2
                    print(f"OTP 입력: {code}", flush=True)
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
                if "signin" in p.url:
                    print("로그인 실패", flush=True)
                    ctx.close()
                    return 1

            state = ctx.storage_state()
            zoom = [c for c in state.get("cookies", []) if "zoom.us" in c.get("domain", "")]
            COOKIES.write_text(json.dumps(zoom, ensure_ascii=False), encoding="utf-8")
            sess = sum(1 for c in zoom if not c.get("expires") or c["expires"] < 0)
            print(f"로그인 성공 — zoom 쿠키 {len(zoom)}개 저장 (세션쿠키 {sess}개) → {COOKIES}",
                  flush=True)
            ctx.close()
            return 0
    finally:
        xvfb.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
