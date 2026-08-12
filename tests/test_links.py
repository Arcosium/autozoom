from __future__ import annotations

from app import links


def test_zoom_host_is_checked_not_substring():
    assert links.is_zoom_url("https://worldquant.zoom.us/w/123")
    assert not links.is_zoom_url("https://example.com/?next=zoom.us")
    assert not links.is_zoom_url("https://zoom.us.example.com/j/123")


def test_resolve_rejects_internal_urls():
    try:
        links.resolve_url("http://127.0.0.1:8560/health")
    except ValueError as e:
        assert "내부망" in str(e)
    else:
        raise AssertionError("내부 주소를 허용함")
