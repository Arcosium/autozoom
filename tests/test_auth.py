"""인증 + '입장 전 중지 = 삭제' 최소 검증.

AZ_DATA 를 임시 디렉터리로 먼저 돌려놓는다 — 실제 회원 파일·DB 를 건드리면 안 된다.
실행: .venv/bin/python -m pytest tests/test_auth.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["AZ_DATA"] = tempfile.mkdtemp(prefix="az-test-")   # config import 보다 먼저
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, jobs  # noqa: E402


def test_signup_needs_approval():
    ok, _ = auth.create_pending("bob", "pw1234")
    assert ok
    assert not auth.check_login("bob", "pw1234")      # 승인 전엔 못 들어온다
    assert auth.approve("bob")
    assert auth.check_login("bob", "pw1234")
    assert not auth.check_login("bob", "틀린비번")
    assert not auth.create_pending("bob", "pw1234")[0]   # 중복 아이디


def test_rejected_and_removed():
    auth.add_user("eve", "pw1234")
    assert auth.check_login("eve", "pw1234")
    auth.reject("eve")
    assert not auth.check_login("eve", "pw1234")
    assert auth.remove("eve")
    assert auth.create_pending("eve", "pw1234")[0]       # 삭제 후 재신청 가능


def test_admin_role():
    auth.add_user("root", "pw1234", admin=True)
    auth.add_user("plain", "pw1234")
    assert auth.is_admin("root")
    assert not auth.is_admin("plain")
    assert not auth.is_admin(None)
    assert "hash" not in auth.list_users()[0]           # 해시는 화면으로 새지 않는다


def test_lockout():
    auth.add_user("locky", "right-pw")
    for _ in range(auth.MAX_ATTEMPTS):
        assert not auth.check_login("locky", "wrong")
    assert not auth.check_login("locky", "right-pw")    # 잠긴 동안은 맞는 비번도 거절


def test_stop_before_join_deletes_record():
    jid = jobs.create_job("https://zoom.us/j/1", "예약회의", "2099-01-01T09:00")
    assert jobs.get_job(jid)["status"] == "scheduled"
    jobs.stop_job(jid)
    assert jobs.get_job(jid) is None                    # 입장 전 중지 → 기록째 삭제


def test_title_set_and_edit():
    jid = jobs.create_job("https://zoom.us/j/3", "주간 전략 회의", "2099-01-01T09:00")
    assert jobs.get_job(jid)["title"] == "주간 전략 회의"      # 생성 폼의 제목이 실제로 들어간다
    assert jobs.set_title(jid, "  이름 바꾼 회의  ")
    assert jobs.get_job(jid)["title"] == "이름 바꾼 회의"       # 앞뒤 공백은 턴다
    assert jobs.set_title(jid, "가" * 200)
    assert len(jobs.get_job(jid)["title"]) == 80               # 길이 상한
    assert not jobs.set_title("없는아이디", "x")


SUMMARY = """## 한 줄 요약
2026 부트캠프 2주차: 알파 리서치 프레임워크와 LLM 활용 방법론 소개

## 내 할 일
- [ ] 뭐라뭐라"""


def test_one_line_extraction():
    from app import summarize
    assert summarize.one_line(SUMMARY).startswith("2026 부트캠프 2주차")
    assert "내 할 일" not in summarize.one_line(SUMMARY)      # 다음 섹션에서 멈춘다
    # 요약 LLM 이 깊이를 흔들어 '### 한 줄 요약' 으로 써도 잡아야 한다
    assert summarize.one_line("### 한 줄 요약\n본문입니다") == "본문입니다"
    assert summarize.one_line("## 주요 논의\n- x") == ""


def test_clean_title_strips_llm_slop():
    from app import summarize
    assert summarize.clean_title('"제목: 분기 실적 리뷰."') == "분기 실적 리뷰"
    assert summarize.clean_title("알파 리서치 세션\n(설명 줄)") == "알파 리서치 세션"
    assert summarize.clean_title("") == ""
    assert len(summarize.clean_title("가" * 200)) == 60


def _scheduled(title=""):
    return jobs.create_job("https://zoom.us/j/9", title, "2099-01-01T09:00")


def test_autotitle_fills_only_empty(monkeypatch):
    monkeypatch.setattr(jobs.summarize, "make_title", lambda *a, **k: "LLM 이 만든 제목")
    empty, named = _scheduled(), _scheduled("내가 붙인 제목")
    jobs.autotitle(empty, SUMMARY, lambda m: None)
    jobs.autotitle(named, SUMMARY, lambda m: None)
    assert jobs.get_job(empty)["title"] == "LLM 이 만든 제목"
    assert jobs.get_job(named)["title"] == "내가 붙인 제목"    # 사람이 붙인 건 덮지 않는다


def test_autotitle_survives_llm_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("llama-server 죽음")
    monkeypatch.setattr(jobs.summarize, "make_title", boom)
    jid = _scheduled()
    assert jobs.autotitle(jid, SUMMARY, lambda m: None) == ""   # 예외가 새지 않는다
    assert jobs.get_job(jid)["title"] == ""


def test_delete_past_record_removes_files():
    jid = jobs.create_job("https://zoom.us/j/2", "지난회의", "2099-01-01T09:00")
    tr = jobs.config.DATA / "transcripts" / f"{jid}.txt"
    tr.write_text("원문", encoding="utf-8")
    assert jobs.delete_job(jid)
    assert jobs.get_job(jid) is None and not tr.exists()
    assert not jobs.delete_job(jid)                     # 두 번째 삭제는 없는 기록
