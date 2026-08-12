"""관리자 전용 Zoom 봇 로그인 제어의 단위 검증."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import bot_login, server, ui  # noqa: E402


def _isolate_paths(monkeypatch, tmp_path):
    for name in ("STATUS_PATH", "OTP_PATH", "LOG_PATH", "LOCK_PATH"):
        monkeypatch.setattr(bot_login, name, tmp_path / name.lower())


def test_otp_is_vault_state_and_is_one_time(monkeypatch, tmp_path):
    _isolate_paths(monkeypatch, tmp_path)
    bot_login.set_status("otp_required", "코드 입력", pid=os.getpid())
    status = bot_login.submit_otp("123456")

    assert status["state"] == "verifying"
    assert bot_login.OTP_PATH.read_text(encoding="utf-8") == "123456"
    assert bot_login.OTP_PATH.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        bot_login.submit_otp("12ab")


def test_login_lock_prevents_a_second_browser(monkeypatch, tmp_path):
    _isolate_paths(monkeypatch, tmp_path)
    first = bot_login.acquire_lock()
    try:
        assert first is not None
        assert bot_login.acquire_lock() is None
    finally:
        bot_login.release_lock(first)
    assert not bot_login.LOCK_PATH.exists()


def test_admin_button_and_routes_require_admin(monkeypatch):
    admin_request = SimpleNamespace(session={"user": "root"})
    plain_request = SimpleNamespace(session={"user": "plain"})
    monkeypatch.setattr(server.auth, "is_admin", lambda name: name == "root")

    with pytest.raises(HTTPException) as denied:
        server.start_bot_login(plain_request)
    assert denied.value.status_code == 403

    monkeypatch.setattr(server.bot_login, "start", lambda: (True, {"state": "running"}))
    response = server.start_bot_login(admin_request)
    assert response.status_code == 303 and response.headers["location"] == "/admin"

    html = ui.admin([], "root", {"state": "otp_required", "message": "코드를 입력"})
    assert 'action="/admin/zoom-login"' in html
    assert 'action="/admin/zoom-login/otp"' in html
    assert "setTimeout(() =&gt; location.reload()" not in html
    assert "setTimeout(() => location.reload()" in html
    assert "Autozoom 서버의 봇 브라우저" in html
