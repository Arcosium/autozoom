"""회의 요약을 ArcAI.ve Coresight 위키 카드로 올린다.

기존 세션 다이제스트 파이프라인(tools/sessions_to_coresight.py)과 동일한 계약을 따른다:
  * vault 에 .md 를 직접 쓰고(chroma 무접촉) `POST /api/coresight/reindex {"sync":true}`
    → 서비스가 단일 writer 로 동기화한다. ArcAI.ve 재시작 불필요.
  * 본문은 `_split_body` 규칙: `## 핵심` 앞이 summary, 뒤의 불릿이 logic_points 로 청크화된다.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_URL = os.environ.get("ARCAI_BASE_URL", "http://127.0.0.1:8080")
VAULT_WIKI = Path(os.environ.get(
    "CORESIGHT_VAULT_WIKI", "/home/arcosium/projects/ArcAI.ve/coresight_wiki/wiki"))
PROVENANCE = "auto_zoom_meeting"

SECTION = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
# 섹션명 → 불릿 앞에 붙일 라벨. 없는 섹션은 섹션명을 그대로 쓴다.
LABEL = {"주요 논의": "논의", "결정 사항": "결정", "액션 아이템": "할 일",
         "미해결·후속 논의": "후속", "미해결": "후속"}


def slugify(text: str, fallback: str) -> str:
    s = unicodedata.normalize("NFC", (text or "").strip())
    s = re.sub(r"[^\w가-힣\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-").lower()
    return (s or fallback)[:80]


def _parse_summary(summary: str) -> tuple[str, list[str]]:
    """회의 요약 마크다운 → (요약문, 핵심 불릿들).

    라벨이 되는 건 `##` 최상위 섹션뿐이다. `###` 이하 하위 제목은 그룹 헤더 불릿으로
    **한 번만** 넣는다 — 하위 제목을 항목마다 접두하면 긴 제목이 항목 수만큼 반복돼
    카드가 중복 텍스트로 뒤덮인다(실측: 한 회의에서 같은 제목이 6번씩 반복).
    헤딩은 `#` 개수로 깊이를 재야 한다. `^##` 로만 잡으면 `###` 이 두 칸만 먹혀
    남은 `#` 이 섹션명에 붙는다(`# 1. 세션 진행…`).
    번호 목록(`1.`)도 불릿으로 받는다 — 안 받으면 그 섹션이 통째로 사라진다.
    들여쓴 하위 항목은 `↳` 로 계층을 남긴다(청크가 불릿 단위라 평평해지면 소속을 잃는다).
    """
    lead: list[str] = []
    bullets: list[str] = []
    label = ""
    in_lead = False
    for raw in (summary or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = SECTION.match(line.strip())
        if m:
            depth, name = len(m.group(1)), m.group(2).strip()
            if depth <= 2:
                label = LABEL.get(name, name)
                in_lead = "요약" in name
            elif name:
                bullets.append(f"{label} · ▸ {name}" if label else f"▸ {name}")
            continue
        b = BULLET.match(line)
        if b:
            item = re.sub(r"^\[[ x]\]\s*", "", b.group(2).strip())   # 체크박스 제거
            if not item or item == "없음":
                continue
            if len(b.group(1)) >= 2:            # 들여쓴 하위 항목
                item = f"↳ {item}"
            bullets.append(f"{label} · {item}" if label else item)
        elif in_lead or not label:
            lead.append(line.strip())
    return " ".join(lead).strip(), bullets


def build_card(job: dict) -> tuple[str, str]:
    """(slug, 마크다운) 을 만든다."""
    title = (job.get("title") or "").strip()
    when = (job.get("ended_at") or job.get("created_at") or "")[:10] or \
        datetime.now().strftime("%Y-%m-%d")
    if not title:
        title = f"Zoom 회의 {when}"
    lead, bullets = _parse_summary(job.get("summary") or "")

    mins = int((job.get("duration_s") or 0) // 60)
    meta_line = f"{when} Zoom 회의 자동 기록" + (f" · {mins}분" if mins else "")
    body_summary = f"{meta_line}. {lead}".strip()

    tags = ["회의록", "zoom", "auto_zoom", "meeting-minutes"]
    fm = {
        "title": title,
        "tags": tags,
        "authored_by": "ai",
        "provenance": PROVENANCE,
        "confidence": 0.7,
        "created_at": int(time.time()),
        "access_count": 0,
        "corrections": [],
        "source_id": job["id"],
    }
    head = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            if not v:
                head.append(f"{k}: []")      # 빈 리스트를 null 로 흘리지 않는다
                continue
            head.append(f"{k}:")
            head.extend(f"- {x}" for x in v)
        else:
            head.append(f"{k}: {v}")
    head.append("---")

    md = "\n".join(head) + "\n\n" + body_summary + "\n"
    if bullets:
        md += "\n## 핵심\n" + "\n".join(f"- {b}" for b in bullets) + "\n"
    return slugify(title, f"zoom-meeting-{job['id'][:8]}"), md


def publish(job: dict, reindex: bool = True) -> dict:
    """카드를 vault 에 쓰고 재색인을 요청한다."""
    if not (job.get("summary") or "").strip():
        raise ValueError("요약이 아직 없다")
    if not VAULT_WIKI.is_dir():
        raise RuntimeError(f"Coresight vault 를 찾을 수 없다: {VAULT_WIKI}")

    slug, md = build_card(job)
    dst = VAULT_WIKI / f"{slug}.md"
    dst.write_text(md, encoding="utf-8")

    reindexed = False
    if reindex:
        req = urllib.request.Request(
            f"{BASE_URL}/api/coresight/reindex", data=json.dumps({"sync": True}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=300) as r:
            json.loads(r.read())
        reindexed = True
    return {"slug": slug, "path": str(dst), "reindexed": reindexed}
