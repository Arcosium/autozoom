"""요약 + 원문 기반 질의응답. 상시 가동 중인 로컬 llama-server(:11434)를 그대로 쓴다."""
from __future__ import annotations

import json
import urllib.request
from typing import Callable

from . import config

Log = Callable[[str], None]

SYSTEM = (
    "너는 회의록 정리 담당자다. 주어진 것은 음성인식(STT) 결과라 오탈자와 끊긴 문장이 섞여 있다. "
    "맥락으로 보정하되, 원문에 없는 사실·숫자·이름을 지어내지 마라. "
    "불확실한 대목은 '(불명확)' 으로 표시하라."
)

TEMPLATE = """다음은 회의 녹취 원문이다.

<원문>
{transcript}
</원문>

아래 형식의 한국어 마크다운으로 정리하라. 섹션 제목과 순서를 그대로 지켜라.

## 한 줄 요약
## 내 할 일
- [ ] 할 일 — 기한
  ("나"는 {owner} 다. 원문에서 {aliases} 에게 배정됐거나 본인이 하겠다고 말한 것만 여기 넣는다.
   기한이 언급되지 않았으면 "기한 미정" 이라고 쓴다.
   해당하는 것이 하나도 없으면 이 섹션에 "- 없음" 한 줄만 쓴다.)
## 주요 논의
- (핵심 주제별로 묶어서)
## 결정 사항
- (합의·확정된 것만. 없으면 "없음")
## 다른 사람 할 일
- [ ] 담당자 — 할 일 — 기한(언급 없으면 미정)
## 미해결·후속 논의
"""

ASK_SYSTEM = (
    "너는 회의 녹취록을 읽고 질문에 답하는 조수다. 답은 반드시 주어진 원문에 근거해야 한다. "
    "원문에 없는 내용은 추측하지 말고 '원문에서 확인되지 않는다' 고 답하라. "
    "가능하면 근거가 되는 시각([HH:MM:SS])을 함께 밝혀라. 한국어로 간결하게 답하라.\n"
    "질문자('나', '내가', '제가')는 {owner} 다({aliases} 는 모두 같은 사람을 가리킨다). "
    "질문자가 누구인지 되묻지 말고 이 전제로 답하라."
)

ASK_TEMPLATE = """<회의 원문>
{transcript}
</회의 원문>

질문: {question}
"""


def _chat(messages: list[dict], log: Log, temperature: float = 0.3) -> str:
    """빈 응답이면 한 번 재시도한다(로컬 추론모델의 알려진 실패 모드). thinking 은 끈다."""
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "max_tokens": config.LLM_MAX_TOKENS,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    for attempt in (1, 2):
        req = urllib.request.Request(
            f"{config.LLM_BASE_URL}/chat/completions",
            json.dumps(payload).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT_S) as r:
            out = json.load(r)
        text = (out["choices"][0]["message"].get("content") or "").strip()
        if text:
            return text
        log(f"LLM 이 빈 응답을 냈다 (시도 {attempt}) — 재시도")
        payload["temperature"] = min(temperature + 0.3, 1.0)
    return ""


def summarize(transcript: str, log: Log) -> str:
    if not transcript.strip():
        return "_(전사된 발화가 없어 요약할 내용이 없다)_"
    log(f"요약 시작 (원문 {len(transcript):,}자)")
    owner = config.OWNER_NAMES[0] if config.OWNER_NAMES else "나"
    aliases = "·".join(config.OWNER_NAMES) or owner
    prompt = TEMPLATE.format(transcript=transcript, owner=owner, aliases=aliases)
    text = _chat([{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": prompt}], log)
    return text or "_(요약 생성 실패 — 원문을 직접 확인할 것)_"


def ask(transcript: str, question: str, log: Log) -> str:
    """회의 원문을 근거로 질문에 답한다."""
    if not transcript.strip():
        return "원문이 없어 답할 수 없다."
    log(f"질문: {question[:60]}")
    owner = config.OWNER_NAMES[0] if config.OWNER_NAMES else "질문자"
    system = ASK_SYSTEM.format(owner=owner, aliases="·".join(config.OWNER_NAMES) or owner)
    text = _chat([{"role": "system", "content": system},
                  {"role": "user", "content": ASK_TEMPLATE.format(
                      transcript=transcript, question=question)}], log, temperature=0.2)
    return text or "_(답변 생성 실패 — 다시 시도해달라)_"
