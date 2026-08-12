"""사용자가 넣은 공개 링크를 실제 목적지까지 따라가 분류한다."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx


def _public(url: str) -> None:
    p = urlsplit(url)
    if p.scheme not in {"http", "https"} or not p.hostname:
        raise ValueError("http 또는 https 링크를 입력해 주세요")
    try:
        addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except OSError as e:
        raise ValueError("링크의 주소를 찾을 수 없습니다") from e
    for item in addresses:
        if not ipaddress.ip_address(item[4][0]).is_global:
            raise ValueError("내부망 주소는 사용할 수 없습니다")


def resolve_url(url: str, max_redirects: int = 8) -> str:
    """단축 URL도 매 단계 안전성을 확인하며 최종 공개 URL로 푼다."""
    current = (url or "").strip()
    headers = {"User-Agent": "Mozilla/5.0 AutoZoom/1.0"}
    with httpx.Client(timeout=12, follow_redirects=False, headers=headers) as client:
        for _ in range(max_redirects + 1):
            _public(current)
            try:
                response = client.head(current)
                if response.status_code in {403, 405}:
                    with client.stream("GET", current, headers={**headers, "Range": "bytes=0-0"}) as got:
                        status, location = got.status_code, got.headers.get("location")
                else:
                    status, location = response.status_code, response.headers.get("location")
            except httpx.HTTPError as e:
                raise ValueError("링크에 접속할 수 없습니다") from e
            if status in {301, 302, 303, 307, 308} and location:
                current = urljoin(current, location)
                continue
            if status >= 400:
                raise ValueError(f"링크가 응답하지 않습니다 (HTTP {status})")
            return current
    raise ValueError("링크의 이동 횟수가 너무 많습니다")


def is_zoom_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return host == "zoom.us" or host.endswith(".zoom.us")
