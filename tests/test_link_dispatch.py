"""어느 링크 입력칸을 써도 최종 URL 종류에 맞게 작업이 생성되는지 검증한다."""
from app import server


def test_zoom_form_accepts_youtube(monkeypatch):
    made = []
    monkeypatch.setattr(server.links, "resolve_url", lambda _: "https://www.youtube.com/live/abc")
    monkeypatch.setattr(server.jobs, "create_media_job",
                        lambda url, title: made.append((url, title)))
    monkeypatch.setattr(server.jobs, "create_job",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Zoom으로 오분류")))

    response = server.create("https://short.example/x", "", "웨비나", "HK")
    assert made == [("https://www.youtube.com/live/abc", "웨비나")]
    assert response.status_code == 303 and response.headers["location"] == "/#media"


def test_media_form_accepts_zoom(monkeypatch):
    made = []
    monkeypatch.setattr(server.links, "resolve_url", lambda _: "https://worldquant.zoom.us/w/123")
    monkeypatch.setattr(server.jobs, "create_job",
                        lambda url, title: made.append((url, title)))
    monkeypatch.setattr(server.jobs, "create_media_job",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("영상으로 오분류")))

    response = server.create_media("https://short.example/x", "회의")
    assert made == [("https://worldquant.zoom.us/w/123", "회의")]
    assert response.status_code == 303 and response.headers["location"] == "/#zoom"


def test_internal_token_gets_json_job_id_and_tunnel_requests_are_refused(monkeypatch, tmp_path):
    """arka-voice 위임 호출: 토큰이 맞으면 로그인 없이 JSON 을 받고, 터널을 거친 요청은 같은 토큰이어도 막힌다."""
    from fastapi.testclient import TestClient
    monkeypatch.setattr(server.auth, "internal_token", lambda: "tok")
    monkeypatch.setattr(server.links, "resolve_url", lambda u: "https://zoom.us/j/1")
    monkeypatch.setattr(server.jobs, "create_job", lambda *a, **k: "job123")
    c = TestClient(server.app)
    form = {"url": "https://zoom.us/j/1"}
    ok = c.post("/jobs", data=form, headers={"X-AZ-Internal": "tok", "Accept": "application/json"})
    assert ok.status_code == 200 and ok.json() == {"ok": True, "job_id": "job123"}
    bad = c.post("/jobs", data=form, headers={"X-AZ-Internal": "nope", "Accept": "application/json"},
                 follow_redirects=False)
    assert bad.status_code == 303                       # 로그인으로 돌려보낸다
    tunneled = c.post("/jobs", data=form, follow_redirects=False,
                      headers={"X-AZ-Internal": "tok", "Accept": "application/json", "CF-Connecting-IP": "1.2.3.4"})
    assert tunneled.status_code == 303
