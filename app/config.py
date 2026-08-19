"""auto_zoom 설정. 값은 전부 환경변수로 덮어쓸 수 있다.

기본값은 2026-07-22 GB10 실측 검증을 통과한 조합이다. 특히 브라우저 설정은
Zoom 봇 탐지·오디오 출력 실측 결과가 반영돼 있으니 함부로 바꾸지 말 것
(자세한 근거는 README 의 '실측 근거' 참고).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("AZ_DATA", ROOT / "data"))
LOGS = Path(os.getenv("AZ_LOGS", ROOT / "logs"))
DB_PATH = DATA / "auto_zoom.db"
PROFILE_DIR = DATA / "chrome-profile"   # Zoom 로그인 쿠키 영속화
SILENCE_WAV = DATA / "silence.wav"      # 봇 마이크로 흘려보낼 무음

for _d in (DATA, LOGS, DATA / "audio", DATA / "transcripts", PROFILE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- 서버 ---
HOST = os.getenv("AZ_HOST", "127.0.0.1")
PORT = int(os.getenv("AZ_PORT", "8560"))

# --- 봇 / 브라우저 ---
BOT_NAME = os.getenv("AZ_BOT_NAME", "회의록봇")
# '내 할 일' 을 골라내기 위한 소유자 식별용 이름들(쉼표 구분). 첫 번째가 대표 이름.
OWNER_NAMES = [s.strip() for s in os.getenv("AZ_OWNER_NAMES", "김현호,사장님,사장,HK").split(",")
               if s.strip()]
BOT_NOTICE = os.getenv(
    "AZ_BOT_NOTICE",
    "안녕하세요. 이 봇은 회의록 작성을 위해 음성을 녹음하고 텍스트로 변환합니다.",
)
# 실측: headless 크롬은 PulseAudio 에 스트림만 등록하고 -91dB(무음)만 흘린다.
# 소리를 받으려면 Xvfb + headful 이어야 한다. 절대 headless 로 되돌리지 말 것.
DISPLAY = os.getenv("AZ_DISPLAY", ":99")
XVFB_SIZE = os.getenv("AZ_XVFB_SIZE", "1280x800x24")
# 실측: playwright 기본 headless shell 은 Zoom 이 봇으로 차단한다("Automated bots
# aren't allowed to join"). 정식 chromium 채널 + 아래 UA/로케일 조합이어야 통과한다.
BROWSER_CHANNEL = os.getenv("AZ_BROWSER_CHANNEL", "chromium")
USER_AGENT = os.getenv(
    "AZ_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.7727.0 Safari/537.36",
)
LOCALE = os.getenv("AZ_LOCALE", "ko-KR")
TIMEZONE = os.getenv("AZ_TIMEZONE", "Asia/Seoul")

JOIN_TIMEOUT_S = int(os.getenv("AZ_JOIN_TIMEOUT_S", "300"))
# 안전장치: 회의가 이 시간을 넘으면 무조건 나간다(정상 종료 감지가 실패해도 봇이
# 영원히 남지 않게). 무음은 종료 기준이 아니다 — 회의엔 조용한 구간이 흔하다.
MAX_MEETING_S = int(os.getenv("AZ_MAX_MEETING_S", str(4 * 3600)))
# 회의 시작 전이면 대기실/대기화면에서 이만큼까지 기다린다.
WAIT_START_S = int(os.getenv("AZ_WAIT_START_S", "5400"))

# --- STT ---
STT_BACKEND = os.getenv("AZ_STT_BACKEND", "qwen3-asr")   # qwen3-asr | faster-whisper
STT_LANG = os.getenv("AZ_STT_LANG", "ko")
LLAMA_SERVER = os.getenv("AZ_LLAMA_SERVER", "/usr/lib/ollama/llama-server")
GGML_BACKEND_PATH = os.getenv("AZ_GGML_BACKEND", "/usr/lib/ollama/cuda_v13/libggml-cuda.so")
GGML_LD_PATH = os.getenv("AZ_GGML_LD", "/usr/lib/ollama/cuda_v13:/usr/lib/ollama")
ASR_DIR = Path(os.getenv("AZ_ASR_DIR", "/home/arcosium/models/llm/qwen3-asr"))
ASR_MODEL = os.getenv("AZ_ASR_MODEL", str(ASR_DIR / "Qwen3-ASR-0.6B-Q8_0.gguf"))
ASR_MMPROJ = os.getenv("AZ_ASR_MMPROJ", str(ASR_DIR / "mmproj-Qwen3-ASR-0.6B-bf16.gguf"))
ASR_PORT = int(os.getenv("AZ_ASR_PORT", "11437"))
ASR_BASE_URL = os.getenv("AZ_ASR_BASE_URL", f"http://127.0.0.1:{ASR_PORT}")
# 실측: 60초까지는 37배속·무손실. 5분 통짜는 반복 환각(30문장→144문장)이 난다.
ASR_CHUNK_S = float(os.getenv("AZ_ASR_CHUNK_S", "45"))
# 실측: 완전 무음은 빈 출력이지만 미약한 노이즈엔 엉뚱한 외국어를 뱉는다 → 게이팅 필요.
ASR_MIN_DBFS = float(os.getenv("AZ_ASR_MIN_DBFS", "-45"))
# 사장 지시: 평소엔 메모리에 올려두지 않는다. 유휴 시 프로세스째 내린다.
ASR_IDLE_UNLOAD_S = int(os.getenv("AZ_ASR_IDLE_UNLOAD_S", "180"))
WHISPER_MODEL = os.getenv("AZ_WHISPER_MODEL", "large-v3")  # 폴백용

# --- 요약 LLM (상시 가동 중인 로컬 llama-server) ---
LLM_BASE_URL = os.getenv("AZ_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
LLM_MODEL = os.getenv("AZ_LLM_MODEL", "qwen3.6-35b-a3b-uncensored")  # 2026-07-24 styletwin LoRA 제거 → 순수 base(:11434, model명은 서버가 무시)
LLM_MAX_TOKENS = int(os.getenv("AZ_LLM_MAX_TOKENS", "24000"))
LLM_TIMEOUT_S = int(os.getenv("AZ_LLM_TIMEOUT_S", "1800"))
