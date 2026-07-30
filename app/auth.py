"""사용자 저장소 — 승인제 가입(관리자가 승인한 계정만 로그인). Image Studio 와 같은 방식.

저장은 `data/users.json` (data/ 는 vault 심링크 — 회원 정보는 레포에 남지 않는다).
비밀번호는 salt+pbkdf2-sha256(200k) 해시만 저장하고, 평문도 해시도 코드에 넣지 않는다.
계정 생성은 CLI 로만:  .venv/bin/python -m app.auth add <아이디> [--admin]
로그인 시도 제한은 인메모리(재시작 시 초기화 — 영속화 불필요).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

from . import config

USERS_PATH = config.DATA / "users.json"
SECRET_PATH = config.DATA / ".session_secret"
ITERATIONS = 200_000
_DUMMY_SALT = "00" * 16          # 사용자 열거 방지 — 없는 아이디에도 같은 pbkdf2 비용을 지불한다
MAX_ATTEMPTS = int(os.getenv("AZ_LOGIN_MAX_ATTEMPTS", "5"))
LOCKOUT_S = int(os.getenv("AZ_LOGIN_LOCKOUT_S", "900"))

_lock = threading.Lock()
_attempts: dict[str, dict] = {}


def session_secret() -> str:
    """서명 쿠키용 비밀. 재시작해도 세션이 유지되도록 vault 에 한 번만 만든다."""
    if not SECRET_PATH.exists():
        SECRET_PATH.write_text(secrets.token_hex(32), encoding="utf-8")
        SECRET_PATH.chmod(0o600)
    return SECRET_PATH.read_text(encoding="utf-8").strip()


def _hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", (password or "").encode(),
                               bytes.fromhex(salt_hex), ITERATIONS).hex()


def _load() -> dict:
    try:
        return json.loads(USERS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(users: dict) -> None:
    tmp = USERS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(USERS_PATH)


def _patch(username: str, **fields) -> bool:
    with _lock:
        users = _load()
        if username not in users:
            return False
        users[username].update(fields)
        _save(users)
    return True


def create_pending(username: str, password: str) -> tuple[bool, str]:
    """가입 신청 — 승인 대기 상태로 만든다."""
    username = (username or "").strip()
    if not username or not password:
        return False, "아이디와 비밀번호를 입력하세요."
    with _lock:
        users = _load()
        if username in users:
            return False, "이미 존재하는 아이디입니다."
        salt = secrets.token_hex(16)
        users[username] = {"username": username, "salt": salt, "hash": _hash(password, salt),
                           "role": "user", "status": "pending", "created": int(time.time())}
        _save(users)
    return True, "가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다."


def add_user(username: str, password: str, admin: bool = False) -> str:
    """CLI 전용 — 승인까지 끝난 계정을 바로 만든다."""
    ok, msg = create_pending(username, password)
    if not ok:
        return msg
    _patch(username.strip(), status="approved", role="admin" if admin else "user")
    return f"{username} 생성 완료 ({'admin' if admin else 'user'})"


def verify_credentials(username: str, password: str) -> bool:
    u = _load().get(username or "")
    if not u or u.get("status") != "approved":
        _hash(password, _DUMMY_SALT)
        return False
    return hmac.compare_digest(u.get("hash", ""), _hash(password, u.get("salt", "")))


def check_login(username: str, password: str) -> bool:
    """로그인 게이트. MAX_ATTEMPTS 연속 실패 시 LOCKOUT_S 동안 잠근다."""
    username = (username or "").strip()
    now = time.time()
    with _lock:
        st = _attempts.get(username)
        if st and st["locked_until"] > now:
            return False
    ok = verify_credentials(username, password)
    with _lock:
        if ok:
            _attempts.pop(username, None)
            return True
        st = _attempts.get(username) or {"count": 0, "locked_until": 0.0}
        st["count"] += 1
        if st["count"] >= MAX_ATTEMPTS:
            st.update(count=0, locked_until=now + LOCKOUT_S)
        _attempts[username] = st
    return False


def is_admin(username: str | None) -> bool:
    u = _load().get(username or "")
    return bool(u and u.get("role") == "admin" and u.get("status") == "approved")


def list_users() -> list[dict]:
    """관리 화면용 — 대기 신청이 먼저 보이게 정렬한다."""
    order = {"pending": 0, "approved": 1, "rejected": 2}
    return sorted(({k: v for k, v in rec.items() if k not in ("salt", "hash")}
                   for rec in _load().values()),
                  key=lambda r: (order.get(r.get("status"), 9), r.get("username", "")))


def approve(username: str) -> bool:
    return _patch(username, status="approved")


def reject(username: str) -> bool:
    return _patch(username, status="rejected")


def remove(username: str) -> bool:
    """계정 삭제 — 거절된 사람이 다시 신청할 수 있게 아이디를 비운다."""
    with _lock:
        users = _load()
        if users.pop(username, None) is None:
            return False
        _save(users)
    return True


if __name__ == "__main__":       # 계정 생성 CLI (비밀번호는 입력받는다 — 인자·코드에 남기지 않는다)
    import getpass
    import sys

    argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] != "add":
        sys.exit("사용법: python -m app.auth add <아이디> [--admin]")
    print(add_user(argv[1], getpass.getpass("비밀번호: "), admin="--admin" in argv))
