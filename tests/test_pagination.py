"""기록 페이지의 DB 범위, 페이지 경계와 URL 보존을 검사한다."""
import pytest
from fastapi.testclient import TestClient

from app import jobs, server, ui


@pytest.fixture
def archive(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs.config, "DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(jobs, "_ensure_scheduler", lambda: None)
    monkeypatch.setattr(server.auth, "internal_token", lambda: "test-pagination")
    jobs.init_db()
    with jobs._conn() as conn:
        conn.executemany(
            "INSERT INTO jobs (id,url,title,status,created_at) VALUES (?,?,?,'done',?)",
            [(f"{n:03}", "", f"회의 {n:03}", "2026-11-05T09:00:00")
             for n in range(56)])
    return TestClient(server.app, headers={"x-az-internal": "test-pagination"})


def test_database_pages_are_complete_and_stable(archive):
    assert jobs.count_jobs() == 56
    pages = [jobs.list_jobs(limit=5, offset=n) for n in range(0, 56, 5)]
    ids = [job["id"] for page in pages for job in page]
    assert ids == [f"{n:03}" for n in reversed(range(56))]
    assert len(jobs.list_jobs()) == 50  # 기존 API의 기본 범위 유지


def test_first_second_and_last_page(archive):
    for page, expected in [(1, range(55, 50, -1)), (2, range(50, 45, -1)),
                           (12, [0]), (999, [0])]:
        response = archive.get(f"/?page={page}")
        assert response.status_code == 200
        body = response.text
        ids = [f"{n:03}" for n in expected]
        assert body.count('<a class="title"') == len(ids)
        for job_id in ids:
            assert f'href="/jobs/{job_id}"' in body
        assert "전체 56건" in body
        assert "이 기기로 녹음하거나, 줌에 봇을 보내거나" not in body
        assert "location.pathname + location.search" in body


def test_page_validation_and_navigation(archive):
    for value in ("0", "-1", "abc"):
        assert archive.get(f"/?page={value}").status_code == 422
    assert 'href="/?page=11"' in archive.get("/").text
    last = archive.get("/?page=12").text
    assert 'href="/?page=10"' in last
    assert '<span aria-current="page">12</span>' in last
    assert 'href="/?page=13"' not in last


def test_empty_and_single_page(archive):
    with jobs._conn() as conn:
        conn.execute("DELETE FROM jobs WHERE id != '000'")
    assert 'class="pagination"' not in archive.get("/").text
    with jobs._conn() as conn:
        conn.execute("DELETE FROM jobs")
    response = archive.get("/?page=999")
    assert response.status_code == 200
    assert "아직 기록이 없다" in response.text
    assert 'class="pagination"' not in response.text
    assert ui.pagination(1, 5) == ""
