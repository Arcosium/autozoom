"""관리자 화면에서 시작하는 Zoom 봇 계정 로그인 작업.

로그인 프로세스의 상태·OTP·로그는 모두 ``data/``(vault 심링크)에만 둔다.
이 모듈에는 Zoom 자격 증명을 보관하지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import config

STATUS_PATH = config.DATA / "zoom_login_status.json"
OTP_PATH = config.DATA / "otp.txt"
LOG_PATH = config.DATA / "zoom_login.log"
LOCK_PATH = config.DATA / "zoom_login.lock"
SCRIPT_PATH = config.ROOT / "scripts" / "zoom_login.py"

_proc: subprocess.Popen | None = None
_OTP_RE = re.compile(r"\d{4,8}")
_LIVE_STATES = {"running", "otp_required", "verifying"}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _pid_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def set_status(state: str, message: str, *, pid: int | None = None) -> dict:
    """민감정보 없이 로그인 진행 상태를 vault에 원자적으로 기록한다."""
    value = {"state": state, "message": message, "updated_at": _now()}
    if pid:
        value["pid"] = pid
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(STATUS_PATH)
    return value


def status() -> dict:
    """마지막 로그인 상태. 끝난 프로세스의 stale '진행 중' 표시도 정리한다."""
    try:
        value = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "idle", "message": "아직 로그인 작업을 시작하지 않았습니다."}
    if not isinstance(value, dict):
        return {"state": "idle", "message": "아직 로그인 작업을 시작하지 않았습니다."}
    if value.get("state") in _LIVE_STATES and not _pid_alive(value.get("pid")):
        return set_status("failed", "로그인 프로세스가 끝났습니다. 다시 시작해 주세요.")
    return value


def _has_active_zoom_job() -> bool:
    """회의 브라우저와 로그인 브라우저가 같은 프로필을 동시에 쓰지 않게 한다."""
    from . import jobs  # jobs import는 로그인 스크립트를 가볍게 유지하려고 여기서만 한다.

    return any(
        job.get("status") in {"queued", "joining", "recording"}
        and "zoom.us" in (job.get("url") or "")
        for job in jobs.list_jobs(limit=200)
    )


def start() -> tuple[bool, dict]:
    """로그인 스크립트를 한 번만 백그라운드로 실행한다."""
    global _proc
    current = status()
    if current.get("state") in _LIVE_STATES and _pid_alive(current.get("pid")):
        return False, current
    if _has_active_zoom_job():
        return False, set_status("busy", "회의 봇이 실행 중입니다. 퇴장한 뒤 로그인해 주세요.")

    OTP_PATH.unlink(missing_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"\n[{_now()}] 관리자 요청으로 봇 계정 로그인을 시작합니다.\n")
        log.flush()
        _proc = subprocess.Popen(
            [sys.executable, str(SCRIPT_PATH)], cwd=config.ROOT,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    return True, set_status("running", "로그인 창을 열고 있습니다.", pid=_proc.pid)


def submit_otp(otp: str) -> dict:
    """관리자에게 받은 OTP를 vault의 일회용 파일로 전달한다."""
    code = (otp or "").strip()
    if not _OTP_RE.fullmatch(code):
        raise ValueError("인증 코드는 숫자 4~8자리여야 합니다.")
    current = status()
    if current.get("state") != "otp_required" or not _pid_alive(current.get("pid")):
        raise ValueError("현재 인증 코드를 받을 로그인 작업이 없습니다.")
    OTP_PATH.write_text(code, encoding="utf-8")
    OTP_PATH.chmod(0o600)
    return set_status("verifying", "인증 코드를 확인하고 있습니다.",
                      pid=current.get("pid"))


def acquire_lock() -> int | None:
    """별도 클릭·직접 실행에서도 로그인 브라우저가 겹치지 않게 한다."""
    for _ in range(2):
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, str(os.getpid()).encode())
            return fd
        except FileExistsError:
            try:
                old_pid = int(LOCK_PATH.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                old_pid = 0
            if _pid_alive(old_pid):
                return None
            LOCK_PATH.unlink(missing_ok=True)
    return None


def release_lock(fd: int | None) -> None:
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    LOCK_PATH.unlink(missing_ok=True)
