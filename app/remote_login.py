"""관리자 화면에서 서버의 봇 브라우저를 원격 조작해 Zoom 에 직접 로그인한다.

자동 로그인(scripts/zoom_login.py)이 막힐 때의 우회로 — GenomicWQB 의 Persona 처럼
서버가 못 푸는 인증 단계를 사용자가 대시보드에서 1회 직접 완료한다.
화면은 JPEG 스냅샷 폴링, 입력은 클릭·타이핑 릴레이. playwright sync API 는
스레드 간 공유가 안 되므로 브라우저 조작은 전부 워커 스레드 하나에 가둔다.
"""
from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time

from . import bot_login, config

VIEW_W, VIEW_H = 1280, 800
IDLE_STOP_S = 600           # 입력이 이만큼 없으면 브라우저를 스스로 내린다
DISPLAY = ":97"             # zoom_login.py(:96)·회의 봇(:99)과 겹치지 않게
COOKIES = config.DATA / "zoom_cookies.json"

_cmd: queue.Queue = queue.Queue()
_shot: bytes = b""
_state = {"on": False, "message": "꺼짐"}
_worker: threading.Thread | None = None
_lock = threading.Lock()


def _set(on: bool, message: str) -> None:
    with _lock:
        _state.update(on=on, message=message)


def status() -> dict:
    with _lock:
        return dict(_state)


def screenshot() -> bytes:
    return _shot


def send(event: dict) -> None:
    if not status()["on"]:
        raise ValueError("원격 로그인 브라우저가 꺼져 있다")
    _cmd.put(event)


def stop() -> None:
    if status()["on"]:
        _cmd.put({"t": "quit"})


def start() -> dict:
    global _worker
    if status()["on"]:
        return status()
    if bot_login._has_active_zoom_job():
        return {"on": False, "message": "회의 봇이 실행 중이다 — 퇴장 후 다시 시도"}
    _worker = threading.Thread(target=_run, daemon=True)
    _worker.start()
    for _ in range(100):        # 브라우저가 뜰 때까지 최대 10초 기다렸다가 상태를 돌려준다
        time.sleep(0.1)
        s = status()
        if s["on"] or "실패" in s["message"]:
            break
    return status()


def _logged_in(page) -> bool:
    """scripts/zoom_login.py 와 같은 판정 — 프로필 화면의 실제 UI 로 확인한다."""
    try:
        body = re.sub(r"\s+", " ", page.inner_text("body"))
    except Exception:
        return False
    account_ui = ("My Account" in body or "내 계정" in body) and (
        "Profile Page" in body or "프로필 설정" in body)
    signin_ui = bool(re.search(r"(^|\s)(로그인|Sign In)(\s|$)", body, re.I))
    return "signin" not in page.url.lower() and account_ui and not signin_ui


def _save_session(ctx) -> tuple[bool, str]:
    """새 탭으로 프로필을 열어 로그인 확인 후 쿠키를 덤프한다. 사용자 화면은 안 건드린다."""
    check = ctx.new_page()
    try:
        check.goto("https://zoom.us/profile", wait_until="domcontentloaded", timeout=30000)
        check.wait_for_timeout(4000)
        if not _logged_in(check):
            return False, "아직 로그인 상태가 아니다 — 로그인을 마친 뒤 다시 저장"
    finally:
        check.close()
    zoom = [c for c in ctx.storage_state().get("cookies", [])
            if "zoom.us" in c.get("domain", "")]
    COOKIES.write_text(json.dumps(zoom, ensure_ascii=False), encoding="utf-8")
    COOKIES.chmod(0o600)
    bot_login.set_status("success", "원격 직접 로그인으로 세션 저장 완료.")
    return True, f"로그인 확인 — 쿠키 {len(zoom)}개 저장. 이제 봇을 회의에 보낼 수 있다."


def _run() -> None:
    global _shot
    from playwright.sync_api import sync_playwright

    lock_fd = bot_login.acquire_lock()
    if lock_fd is None:
        _set(False, "다른 로그인 작업이 이미 실행 중이다")
        return
    xvfb = None
    try:
        import os

        from . import zoom_bot

        zoom_bot.clear_profile_lock(config.PROFILE_DIR, lambda m: None)
        env = dict(os.environ, DISPLAY=DISPLAY,
                   XDG_RUNTIME_DIR=f"/run/user/{os.getuid()}")
        xvfb = subprocess.Popen(
            ["Xvfb", DISPLAY, "-screen", "0", f"{VIEW_W}x{VIEW_H}x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                str(config.PROFILE_DIR), channel=config.BROWSER_CHANNEL,
                headless=False, env=env, user_agent=config.USER_AGENT,
                locale=config.LOCALE, timezone_id=config.TIMEZONE,
                viewport={"width": VIEW_W, "height": VIEW_H},
                args=["--disable-blink-features=AutomationControlled",
                      "--disable-dev-shm-usage"])
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://zoom.us/signin", wait_until="domcontentloaded",
                      timeout=45000)
            _set(True, "브라우저 켜짐 — 화면을 눌러 로그인한다")
            last_input = time.time()
            last_shot = 0.0
            while True:
                try:
                    ev = _cmd.get(timeout=0.25)
                except queue.Empty:
                    ev = None
                if ev:
                    last_input = time.time()
                    t = ev.get("t")
                    try:
                        if t == "quit":
                            break
                        elif t == "click":
                            page.mouse.click(float(ev["x"]), float(ev["y"]))
                        elif t == "text":
                            page.keyboard.type(str(ev["v"])[:200], delay=40)
                        elif t == "key" and ev.get("v") in (
                                "Enter", "Tab", "Backspace", "Escape", "PageDown", "PageUp"):
                            page.keyboard.press(ev["v"])
                        elif t == "goto":
                            page.goto("https://zoom.us/signin",
                                      wait_until="domcontentloaded", timeout=45000)
                        elif t == "save":
                            ok, msg = _save_session(ctx)
                            _set(not ok, msg)   # 성공하면 꺼진 상태로 메시지를 남긴다
                            if ok:
                                break
                    except Exception as e:  # noqa: BLE001 — 입력 하나가 죽어도 화면은 계속
                        _set(True, f"{type(e).__name__}: {e}")
                if time.time() - last_input > IDLE_STOP_S:
                    _set(False, "입력이 없어 자동 종료됨")
                    break
                if time.time() - last_shot > 0.8:
                    try:
                        _shot = page.screenshot(type="jpeg", quality=55)
                    except Exception:
                        pass
                    last_shot = time.time()
            ctx.close()
    except Exception as e:  # noqa: BLE001
        _set(False, f"원격 로그인 실패: {type(e).__name__}: {e}")
        return
    finally:
        if xvfb and xvfb.poll() is None:
            xvfb.terminate()
        bot_login.release_lock(lock_fd)
        _shot = b""
    if status()["on"]:
        _set(False, "원격 로그인 종료")
