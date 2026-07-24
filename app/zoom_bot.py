"""Zoom 웹 클라이언트에 참가하는 봇.

Zoom API / Meeting SDK 를 쓰지 않는다. 무료 플랜에선 RTMS·클라우드 녹화가 모두
유료라, 브라우저로 정상 참가한 뒤 스피커로 나오는 소리를 캡처한다.

아래 설정은 전부 2026-07-22 실회의 대상 실측으로 확정된 것이다:
  * headless 는 Zoom 이 봇으로 차단하고, 통과하더라도 오디오가 -91dB(무음)이다.
    → Xvfb + headful 필수.
  * --use-fake-ui-for-media-stream 은 카메라까지 자동 승인해 초록 화면을 송출한다.
    → 쓰지 않는다. 마이크 권한만 주고, 입장 전에 '음소거' 를 눌러 들어간다.
  * 정식 URL 은 /wc/{회의ID}/join?{쿼리} 다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

from . import config

Log = Callable[[str], None]

BOT_BLOCKED = re.compile(r"(Automated bots aren't allowed|자동화된 봇)", re.I)
LOGIN_WALL = re.compile(r"(로그인하여 이 회의 참가|sign in to join|계정으로 로그인할 것을 요구)", re.I)
# 실측(2026-07-22): 웨비나 종료 문구는 "이 웨비나는 호스트에 의해 종료되었습니다." 다.
# 예전 패턴('호스트가...종료', '회의가 종료되었')은 조사도 명사도 어긋나 못 잡았고,
# 모달 뒤에 툴바가 DOM 에 남아 있어 툴바 판정도 통과해 버려서 봇이 안 나갔다.
ENDED = re.compile(
    r"((회의|웨비나)[^.]{0,20}종료되었|호스트[^.]{0,12}종료(되|했|합)|"
    r"This (meeting|webinar) has been ended|(Meeting|Webinar) has ended|"
    r"회의 링크가 잘못되었|meeting link is invalid|회의에서 나갔습니다)", re.I)
WAITING = re.compile(
    r"(호스트가 이 회의를 시작할 때까지|대기실|Waiting for the host|"
    r"has not started|시작되기를 기다)", re.I)


class JoinError(RuntimeError):
    pass


@dataclass
class MeetingResult:
    joined: bool
    reason: str
    duration_s: float
    speakers: list[dict] = field(default_factory=list)


def to_web_client_url(url: str) -> str:
    """초대 URL(/j/, /w/) → 웹 클라이언트 URL. 이미 /wc/ 면 그대로 둔다."""
    url = url.strip()
    if "/wc/" in url:
        return url
    m = re.match(r"(https://[\w.-]*zoom\.us)/(?:j|s|w)/(\d+)(?:\?(.*))?$", url)
    if not m:
        raise ValueError(f"Zoom 회의/웨비나 URL 로 보이지 않는다: {url}")
    host, mid, query = m.group(1), m.group(2), m.group(3) or ""
    return f"{host}/wc/{mid}/join" + (f"?{query}" if query else "")


def ensure_silence_wav() -> None:
    """봇 마이크로 흘려보낼 무음 파일. Chrome 기본 가짜 마이크는 1kHz 삐 소리라 필수."""
    if config.SILENCE_WAV.exists():
        return
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=48000:cl=mono", "-t", "10", str(config.SILENCE_WAV)],
        check=True,
    )


def free_display(preferred: str) -> str:
    """비어 있는 X 디스플레이 번호를 고른다.

    고정 번호를 쓰면 이전 실행의 고아 Xvfb 와 충돌해 브라우저가 아예 못 뜬다.
    """
    nums = [preferred.lstrip(":")] + [str(n) for n in range(90, 130)]
    for n in nums:
        if not Path(f"/tmp/.X11-unix/X{n}").exists():
            return f":{n}"
    return preferred


def clear_profile_lock(profile: Path, log: Log) -> None:
    """비정상 종료로 남은 크로미움 싱글턴 잠금을 치운다(현재 사용 중이면 건드리지 않음)."""
    if any(profile.name in p for p in _running_cmdlines()):
        return
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        p = profile / name
        try:
            if p.is_symlink() or p.exists():
                p.unlink()
                log(f"묵은 프로필 잠금 제거: {name}")
        except OSError:
            pass


def _running_cmdlines() -> list[str]:
    out = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                out.append(f.read().decode("utf-8", "replace"))
        except OSError:
            continue
    return out


class Xvfb:
    """headful 크롬을 띄우기 위한 가상 디스플레이."""

    def __init__(self, display: str, size: str):
        self.display, self.size = display, size
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> "Xvfb":
        if not shutil.which("Xvfb"):
            raise JoinError("Xvfb 가 없다. `sudo apt-get install -y xvfb` 필요.")
        self._proc = subprocess.Popen(
            ["Xvfb", self.display, "-screen", "0", self.size, "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        return self

    def __exit__(self, *exc) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def restore_cookies(ctx, log: Log) -> int:
    """저장된 Zoom 쿠키를 주입한다.

    프로필만으로는 부족하다 — Zoom 세션 쿠키의 상당수가 비영속(expires<0)이라
    브라우저를 닫으면 사라지고 로그인이 풀린다(실측). scripts/zoom_login.py 가
    덤프해 둔 쿠키를 매 기동 시 다시 넣어 준다.
    """
    path = config.DATA / "zoom_cookies.json"
    if not path.exists():
        return 0
    try:
        cookies = json.loads(path.read_text(encoding="utf-8"))
        ctx.add_cookies(cookies)
        log(f"Zoom 쿠키 {len(cookies)}개 복원")
        return len(cookies)
    except Exception as e:  # noqa: BLE001
        log(f"쿠키 복원 실패(무시하고 진행): {type(e).__name__}: {e}")
        return 0


def ensure_display_name(page: Page, desired: str, log: Log) -> bool:
    """Zoom 계정의 표시 이름을 잡별 지정값으로 맞춘다.

    로그인 상태로 입장하면 Zoom 은 이름 입력창을 아예 띄우지 않고 계정 프로필의
    표시 이름을 쓴다(실측). 그래서 폼에 적은 '입장 이름' 을 반영하려면 입장 직전에
    프로필을 고쳐야 한다. 실패해도 회의 참가는 그대로 진행한다(fail-soft).
    """
    desired = (desired or "").strip()
    if not desired:
        return False
    try:
        page.goto("https://us05web.zoom.us/profile", wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(6000)
        if "signin" in page.url:
            log("프로필 접근 불가(로그인 안 됨) — 이름 변경 건너뜀")
            return False
        page.get_by_text("편집", exact=True).first.click(timeout=8000)
        page.wait_for_timeout(2500)
        box = page.locator("#displayName")
        current = (box.input_value(timeout=5000) or "").strip()
        if current == desired:
            log(f"표시 이름 이미 '{desired}' — 변경 불필요")
            for nm in ("취소", "Cancel"):
                if _click(page, nm, 2500):
                    break
            return True
        box.fill(desired, timeout=5000)
        if not (_click(page, "저장", 6000) or _click(page, "Save", 6000)):
            log("저장 버튼을 못 찾아 이름 변경 실패 — 계속 진행")
            return False
        page.wait_for_timeout(5000)
        log(f"표시 이름 변경: '{current}' → '{desired}'")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"이름 변경 실패(계속 진행): {type(e).__name__}: {str(e)[:80]}")
        return False


def _body(page: Page) -> str:
    try:
        return re.sub(r"\s+", " ", page.inner_text("body"))
    except Exception:
        return ""


def _visible_labels(page: Page, limit: int = 40) -> list[str]:
    out: list[str] = []
    try:
        n = min(page.locator("button").count(), limit)
    except Exception:
        return out
    for i in range(n):
        b = page.locator("button").nth(i)
        try:
            if b.is_visible():
                t = (b.inner_text() or "").strip() or (b.get_attribute("aria-label") or "").strip()
                if t:
                    out.append(t.replace("\n", "/"))
        except Exception:
            pass
    return out


# 회의/웨비나 툴바에 함께 뜨는 것들. 대기실에는 이런 게 없다(대기실은 '끝내기' 하나뿐).
TOOLBAR = ("음소거", "참가자", "채팅", "손들기", "Q&A", "비디오",
           "Mute", "Participants", "Chat", "Raise Hand")
LEAVE_LABELS = ("나가기", "끝내기", "회의 나가기", "Leave", "End")


def _in_meeting(page: Page) -> bool:
    """실제로 회의/웨비나 안에 들어왔는지.

    주의: 웨비나 대기실도 '끝내기' 버튼을 보여준다. 그래서 나가기 버튼만으로 판정하면
    대기 중을 입장으로 오인한다. 반대로 '나가기' 만 찾으면 웨비나 참석자 화면을
    영영 인식 못 해 '대기 시간 초과' 로 실패한다. 툴바 요소 2개 이상을 기준으로 삼는다.
    """
    labels = _visible_labels(page)
    if any("나가기" in x for x in labels):
        return True
    return sum(1 for k in TOOLBAR if any(k in x for x in labels)) >= 2


def _click(page: Page, name: str, timeout: float = 5000) -> bool:
    """접근성 이름 정확 일치 → :has-text 폴백 순으로 클릭한다."""
    try:
        page.get_by_role("button", name=name, exact=True).first.click(timeout=timeout)
        return True
    except Exception:
        pass
    try:
        page.locator(f"button:has-text('{name}')").last.click(timeout=timeout / 2)
        return True
    except Exception:
        return False


def join_and_wait(
    meeting_url: str,
    browser_env: dict,
    log: Log,
    should_stop: Callable[[], bool],
    on_tick: Callable[[float], str | None] | None = None,
    bot_name: str = "",
) -> MeetingResult:
    """회의에 참가해 종료(또는 중단 요청)까지 머문다.

    browser_env 는 audio.SinkRecorder.browser_env() 가 준 PULSE_SINK 포함 환경.
    on_tick(elapsed) 이 문자열을 돌려주면 그 사유로 즉시 퇴장한다(무음 감지 등).
    """
    ensure_silence_wav()
    web_url = to_web_client_url(meeting_url)
    log(f"웹 클라이언트 URL: {web_url}")
    started = time.time()
    speakers: list[dict] = []

    display = free_display(config.DISPLAY)
    if display != config.DISPLAY:
        log(f"{config.DISPLAY} 가 사용 중 — {display} 로 띄운다")
    clear_profile_lock(config.PROFILE_DIR, log)

    with Xvfb(display, config.XVFB_SIZE):
        env = dict(browser_env)
        env["DISPLAY"] = display
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=str(config.PROFILE_DIR),
                channel=config.BROWSER_CHANNEL,
                headless=False,
                env=env,
                permissions=["microphone"],          # 카메라는 일부러 미부여
                user_agent=config.USER_AGENT,
                locale=config.LOCALE,
                timezone_id=config.TIMEZONE,
                viewport={"width": 1280, "height": 800},
                args=[
                    "--disable-blink-features=AutomationControlled",
                    # 강제 종료 흔적이 있으면 '페이지를 복원하시겠습니까?' 팝업이 클릭을 가로챈다.
                    "--hide-crash-restore-bubble",
                    "--disable-session-crashed-bubble",
                    "--use-fake-device-for-media-stream",
                    f"--use-file-for-fake-audio-capture={config.SILENCE_WAV}",
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-dev-shm-usage",
                    "--window-size=1280,800",
                ],
            )
            restore_cookies(ctx, log)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            joined, reason = False, "정상 종료"
            display_name = (bot_name or "").strip() or config.BOT_NAME
            try:
                # 로그인 세션 입장에선 이름 입력창이 안 뜬다 → 프로필 표시 이름을 먼저 맞춘다.
                ensure_display_name(page, display_name, log)

                page.goto(web_url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_timeout(9000)

                body = _body(page)
                if BOT_BLOCKED.search(body):
                    return MeetingResult(False, "Zoom 봇 탐지에 차단됨", time.time() - started)
                if LOGIN_WALL.search(body):
                    return MeetingResult(False, "로그인 필요(봇 계정 로그인 프로필 필요)",
                                         time.time() - started)
                if ENDED.search(body):
                    return MeetingResult(False, "회의 링크가 유효하지 않음/종료됨",
                                         time.time() - started)

                # 이름 입력 → 마이크 끄기 → 참가
                try:
                    page.locator("#input-for-name").first.fill(display_name, timeout=15_000)
                    log(f"표시 이름: {display_name}")
                except Exception:
                    log("이름 입력창 없음 — 로그인 세션으로 참가하는 것으로 보임")
                # 라벨은 '동작' 기준이라 '음소거' 가 보이면 현재 켜져 있다는 뜻이다.
                if _click(page, "음소거", 4000) or _click(page, "Mute", 4000):
                    log("마이크 음소거 후 입장")
                page.wait_for_timeout(800)
                if not (_click(page, "참가", 8000) or _click(page, "Join", 8000)):
                    log("참가 버튼을 찾지 못했다 — 대기 화면일 수 있다")

                # 입장/대기 관찰
                deadline = time.time() + config.WAIT_START_S
                while time.time() < deadline:
                    if should_stop():
                        return MeetingResult(False, "사용자 중단", time.time() - started)
                    if _in_meeting(page):
                        joined = True
                        log("회의 입장 완료")
                        break
                    body = _body(page)
                    if BOT_BLOCKED.search(body):
                        return MeetingResult(False, "Zoom 봇 탐지에 차단됨", time.time() - started)
                    if LOGIN_WALL.search(body):
                        return MeetingResult(False, "로그인 필요", time.time() - started)
                    if ENDED.search(body):
                        return MeetingResult(False, "회의가 종료됨", time.time() - started)
                    if WAITING.search(body):
                        log("대기 중 — 호스트가 시작하기를 기다린다")
                    # 대기 화면에서 오디오 참가 버튼이 뜨는 경우
                    _click(page, "컴퓨터 오디오로 참가", 1500)
                    time.sleep(5)
                else:
                    return MeetingResult(False, "대기 시간 초과", time.time() - started)

                _click(page, "컴퓨터 오디오로 참가", 3000)
                if config.BOT_NOTICE:
                    _post_notice(page, log)

                # 회의 종료까지 감시
                gone = 0
                while True:
                    elapsed = time.time() - started
                    if should_stop():
                        reason = "사용자 중단"
                        break
                    if elapsed > config.MAX_MEETING_S:
                        reason = "최대 시간 초과"
                        break
                    if page.is_closed():
                        reason = "브라우저 페이지가 닫힘"
                        break
                    # Zoom 툴바는 마우스가 멈춰 있으면 자동으로 숨는다. Xvfb 엔 마우스
                    # 움직임이 없어 툴바가 사라지고 '종료' 로 오인된다 → 매 틱 흔들어 준다.
                    try:
                        page.mouse.move(600 + (int(elapsed) % 40), 400)
                    except Exception:
                        pass
                    if ENDED.search(_body(page)):
                        reason = "회의 종료"
                        break
                    if not _in_meeting(page):
                        gone += 1
                        if gone >= 4:      # 일시적 렌더 변화로 성급히 나가지 않는다
                            reason = "회의 종료(툴바 소실)"
                            break
                    else:
                        gone = 0
                    spk = _active_speaker(page)
                    if spk and (not speakers or speakers[-1]["name"] != spk):
                        speakers.append({"t": elapsed, "name": spk})
                    if on_tick:
                        r = on_tick(elapsed)
                        if r:
                            reason = r
                            break
                    time.sleep(3)
            except PWTimeout as e:
                reason = f"타임아웃: {str(e)[:120]}"
            except Exception as e:  # noqa: BLE001
                reason = f"오류: {type(e).__name__}: {str(e)[:120]}"
            finally:
                for lb in LEAVE_LABELS:      # 웨비나는 '끝내기' 다
                    try:
                        if _click(page, lb, 2500):
                            break
                    except Exception:
                        pass
                ctx.close()

    return MeetingResult(joined, reason, time.time() - started, speakers)


def _active_speaker(page: Page) -> str | None:
    """활성 발언자 이름(화자 라벨 근사용). DOM 구조에 의존하므로 실패해도 무시한다."""
    for sel in ("[class*='speaker-active']", "[class*='active-speaker']",
                "[class*='speaker-bar__name']"):
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible(timeout=500):
                t = (el.inner_text() or "").strip()
                if t:
                    return t.splitlines()[0][:40]
        except Exception:
            continue
    return None


def _post_notice(page: Page, log: Log) -> None:
    """입장 고지를 채팅으로 남긴다. 실패해도 회의 진행에는 영향이 없다."""
    try:
        page.locator("button:has-text('채팅')").first.click(timeout=5000)
        box = page.get_by_role("textbox").last
        box.fill(config.BOT_NOTICE, timeout=5000)
        box.press("Enter")
        log("녹음 고지를 채팅으로 전송했다.")
    except Exception:
        log("채팅 고지 실패(웨비나는 참석자 채팅이 막혀 있을 수 있다) — 계속 진행")
