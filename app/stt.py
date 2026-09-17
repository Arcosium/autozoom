"""STT 백엔드.

기본: Qwen3-ASR GGUF 를 llama.cpp(llama-server)로 GPU 구동.

운영(2026-09-17 밤 사장 지시): ASR 은 **항상 떠 있다**. asr-server.service(user, :11437,
Qwen3-ASR-1.7B, 컨텍스트 8192)가 서버를 쥐고, 이 모듈은 살아 있는 서버를 그대로 쓴다
(_ensure_server 가 /health 를 보고 바로 돌아온다). 올렸다 내렸다 하지 않는다 — 운영 유닛이
AZ_ASR_IDLE_UNLOAD_S 를 사실상 무한대로 준다. 예전의 "상시 상주 금지" 방침은 이것으로 끝났다.
그 서비스가 없을 때(단독 실행·개발)만 아래의 기동/유휴 언로드 경로가 돈다.
실측(같은 날): 0.6B→1.7B 로 Zeroth CER 5.01→3.36%, 유휴 GPU 점유 0~1%, 상주 메모리 4.0GB.

폴백: faster-whisper (CPU, 약 1배속). AZ_STT_BACKEND=faster-whisper 로 전환.
"""
from __future__ import annotations

import base64
import gc
import json
import os
import re
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from . import config

Log = Callable[[str], None]
_lock = threading.RLock()
_last_used = 0.0
_watchdog: threading.Thread | None = None
_proc: subprocess.Popen | None = None
_fw_model = None

ASR_TAG = re.compile(r"<asr_text>|</asr_text>", re.I)
LANG_PREFIX = re.compile(r"^\s*language\s+\w+\s*", re.I)


# ---------------------------------------------------------------- 공통 수명주기
def _watch() -> None:
    global _watchdog
    while True:
        time.sleep(15)
        with _lock:
            if not is_loaded():
                _watchdog = None
                return
            if time.time() - _last_used > config.ASR_IDLE_UNLOAD_S:
                unload()
                _watchdog = None
                return


def _touch() -> None:
    global _last_used, _watchdog
    _last_used = time.time()
    if _watchdog is None:
        _watchdog = threading.Thread(target=_watch, daemon=True)
        _watchdog.start()


def is_loaded() -> bool:
    """유휴 감시자가 내릴 대상이 있는가.

    우리가 띄운 프로세스가 아니어도(재시작 뒤 살아남은 고아 서버 등) 포트를 물고 있으면
    GPU 를 쥔 것이다 — 그때도 유휴 시 내려야 한다. unload() 가 포트로 찾아 끈다.
    """
    if config.STT_BACKEND == "faster-whisper":
        return _fw_model is not None
    return (_proc is not None and _proc.poll() is None) or _server_alive()


def _kill_port_listener(port: int) -> bool:
    """우리가 띄우지 않았더라도 이 포트를 물고 있는 ASR 서버를 내린다.

    별도 프로세스(테스트 스크립트 등)가 띄운 서버가 고아로 남아 GPU 를 계속
    점유하는 일을 막는다. 포트는 auto_zoom 전용이라 오폭 위험이 없다.
    """
    out = subprocess.run(["ss", "-lptnH", f"sport = :{port}"],
                         capture_output=True, text=True).stdout
    killed = False
    for pid in set(re.findall(r"pid=(\d+)", out)):
        try:
            os.kill(int(pid), signal.SIGTERM)
            killed = True
        except OSError:
            pass
    return killed


def unload() -> None:
    """모델을 메모리에서 내린다."""
    global _proc, _fw_model
    with _lock:
        if _proc and _proc.poll() is None:
            _proc.terminate()
            try:
                _proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                _proc.kill()
        elif _proc is None:
            _kill_port_listener(config.ASR_PORT)
        _proc = None
        _fw_model = None
        gc.collect()


# ---------------------------------------------------------------- Qwen3-ASR
def _server_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{config.ASR_BASE_URL}/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def drop_page_cache(*paths: Path) -> None:
    """이 파일들이 물고 있는 클린 페이지캐시를 놓는다(sudo 불필요, 다음 읽기만 느려진다).

    GB10 통합메모리에서 CUDA 할당은 페이지캐시를 회수하지 못한다 — 방금 읽은 GGUF·녹음 wav 가
    자기 캐시로 자기 로딩을 막아 모델을 올리기도 전에 cudaSetDevice 에서 OOM 으로 죽는다
    (2026-09-12 실측: 595개 파일 fadvise → MemFree 1.3GB→14GB, 죽던 서버가 19초 만에 기동).
    """
    for path in paths:
        try:
            fd = os.open(path, os.O_RDONLY)
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            os.close(fd)
        except OSError:
            pass


def _err_tail(path: Path, n: int = 2) -> str:
    """서버 로그에서 죽은 이유로 보이는 줄만 추려 한 줄로 만든다.

    llama-server 는 죽을 때 gdb 백트레이스를 길게 뱉는다 — 마지막 줄만 보면 정작 원인
    ('CUDA error: out of memory')을 놓친다. 오류 줄을 앞에서부터 집는다.
    """
    try:
        lines = [x.strip() for x in path.read_text("utf-8", "replace").splitlines() if x.strip()]
    except OSError:
        return ""
    hits = [x for x in lines if re.search(r"error|out of memory|failed", x, re.I)]
    return " / ".join((hits or lines[-n:])[:n])[:300]


def _ensure_server(log: Log) -> None:
    global _proc
    with _lock:
        if _server_alive():
            _touch()
            return
        model, mmproj = Path(config.ASR_MODEL), Path(config.ASR_MMPROJ)
        for p in (model, mmproj):
            if not p.exists():
                raise RuntimeError(f"ASR 모델 파일이 없다: {p} (scripts/fetch_models.sh 실행)")
        env = dict(os.environ)
        env["GGML_BACKEND_PATH"] = config.GGML_BACKEND_PATH
        env["LD_LIBRARY_PATH"] = config.GGML_LD_PATH
        errlog = config.DATA / "asr-server.log"
        for attempt in range(1, config.ASR_START_TRIES + 1):
            # 메모리가 빠듯하면 우리가 쥔 캐시부터 놓고 띄운다(모델 + 쌓아 둔 녹음).
            drop_page_cache(model, mmproj, *(config.DATA / "audio").glob("*.wav"))
            log(f"Qwen3-ASR 서버 기동 (port {config.ASR_PORT})")
            with errlog.open("wb") as fh:
                _proc = subprocess.Popen(
                    [config.LLAMA_SERVER, "-m", str(model), "--mmproj", str(mmproj),
                     "--host", "127.0.0.1", "--port", str(config.ASR_PORT),
                     "--no-webui", "-ngl", "999", "-c", str(config.ASR_CTX), "--jinja"],
                    env=env, stdout=fh, stderr=subprocess.STDOUT,
                )
            why = ""
            for _ in range(120):
                if _server_alive():
                    log("ASR 서버 준비 완료")
                    _touch()
                    return
                if _proc.poll() is not None:
                    why = "기동 중 죽었다"
                    break
                time.sleep(1)
            unload()
            why, detail = why or "기동 타임아웃", _err_tail(errlog)
            # 메모리 고갈은 남이 GPU 를 놓으면 풀린다 — 한 번에 접지 말고 몇 번 더 두드린다.
            if attempt == config.ASR_START_TRIES:
                raise RuntimeError(f"ASR 서버가 {why}. {detail}")
            log(f"ASR 서버가 {why} — {detail} / {config.ASR_START_WAIT_S}초 뒤 재시도 "
                f"({attempt}/{config.ASR_START_TRIES})")
            time.sleep(config.ASR_START_WAIT_S)


def _asr_chunk(wav: Path) -> str:
    b64 = base64.b64encode(wav.read_bytes()).decode()
    payload = {
        "model": "asr",
        "messages": [{"role": "user", "content": [
            {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}},
            {"type": "text", "text": "Transcribe the audio."},
        ]}],
        "max_tokens": 2048,
        "temperature": 0,
    }
    req = urllib.request.Request(
        f"{config.ASR_BASE_URL}/v1/chat/completions",
        json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.load(r)
    text = out["choices"][0]["message"]["content"]
    return ASR_TAG.sub("", LANG_PREFIX.sub("", text)).strip()


# ---------------------------------------------------------------- faster-whisper
def _fw_transcribe(wav: Path, log: Log, progress) -> dict:
    global _fw_model
    with _lock:
        if _fw_model is None:
            from faster_whisper import WhisperModel
            log(f"faster-whisper 로드: {config.WHISPER_MODEL} (cpu/int8)")
            _fw_model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        _touch()
    segments, info = _fw_model.transcribe(
        str(wav), language=config.STT_LANG or None, vad_filter=True,
        beam_size=5, condition_on_previous_text=False)
    out = []
    for seg in segments:
        out.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        _touch()
        if progress and info.duration:
            progress(min(seg.end / info.duration, 1.0))
    return {"segments": out, "duration": info.duration}


# ---------------------------------------------------------------- 공개 API
def transcribe(wav: Path, log: Log, progress: Callable[[float], None] | None = None) -> dict:
    """wav → {"segments": [{start,end,text}], "text": str, "duration": float}"""
    if config.STT_BACKEND == "faster-whisper":
        result = _fw_transcribe(wav, log, progress)
    else:
        from .chunker import split_on_silence

        _ensure_server(log)
        chunks = split_on_silence(wav, config.ASR_CHUNK_S)
        log(f"오디오 {len(chunks)}개 청크로 분할")
        segments = []
        for i, ch in enumerate(chunks):
            text = _asr_chunk(ch.path)
            _touch()
            if text:
                segments.append({"start": ch.start, "end": ch.end, "text": text})
            if progress:
                progress((i + 1) / len(chunks))
            ch.path.unlink(missing_ok=True)
        result = {"segments": segments, "duration": chunks[-1].end if chunks else 0.0}

    result["text"] = "\n".join(s["text"] for s in result["segments"] if s["text"])
    return result


def format_transcript(result: dict) -> str:
    def ts(s: float) -> str:
        return f"{int(s // 3600):02d}:{int(s // 60) % 60:02d}:{int(s % 60):02d}"

    return "\n".join(f"[{ts(s['start'])}] {s['text']}"
                     for s in result["segments"] if s["text"])
