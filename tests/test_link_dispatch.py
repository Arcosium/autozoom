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
