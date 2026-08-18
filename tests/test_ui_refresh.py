"""목록 자동 갱신이 폼 입력을 지우지 않는지 검증한다."""
from app import ui


def _job(status: str) -> dict:
    return {
        "id": "job1", "url": "https://zoom.us/j/1", "title": "예약 회의",
        "status": status, "reason": "", "created_at": "2026-08-18T18:00:00",
        "scheduled_at": "2026-08-19T20:58", "ended_at": None, "duration_s": 0,
    }


def test_future_schedule_does_not_refresh_index():
    html = ui.index([_job("scheduled")], "root", True)
    assert "const busy = false;" in html


def test_active_job_refresh_stops_after_form_edit():
    html = ui.index([_job("recording")], "root", True)
    assert "const busy = true;" in html
    assert "formDirty" in html
    assert "!editingForm()" in html


def test_detail_title_edit_is_protected():
    html = ui.detail(_job("recording"), "root", True)
    assert "if (!formDirty" in html
