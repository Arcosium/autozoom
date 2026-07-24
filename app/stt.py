"""STT 백엔드.

기본: Qwen3-ASR-0.6B GGUF 를 llama.cpp(llama-server)로 GPU 구동. 한국어 실측 35배속.
사장 지시대로 **상시 상주시키지 않는다** — 잡이 들어올 때 서버를 띄우고,
유휴 IDLE_UNLOAD_S 초가 지나면 프로세스째 내려 GPU/메모리를 비운다.

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
    if config.STT_BACKEND == "faster-whisper":
        return _fw_model is not None
    return _proc is not None and _proc.poll() is None


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
        log(f"Qwen3-ASR 서버 기동 (port {config.ASR_PORT})")
        _proc = subprocess.Popen(
            [config.LLAMA_SERVER, "-m", str(model), "--mmproj", str(mmproj),
             "--host", "127.0.0.1", "--port", str(config.ASR_PORT),
             "--no-webui", "-ngl", "999", "-c", "32768", "--jinja"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(120):
            if _server_alive():
                log("ASR 서버 준비 완료")
                _touch()
                return
            if _proc.poll() is not None:
                raise RuntimeError("ASR 서버가 기동 중 죽었다.")
            time.sleep(1)
        raise RuntimeError("ASR 서버 기동 타임아웃")


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
