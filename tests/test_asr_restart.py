"""ASR 서버 기동 실패 처리 — 로그에서 원인 추리기, 실패한 잡 재처리.

2026-09-12 실측 사고: 통합메모리가 차서 llama-server 가 cudaSetDevice 에서 죽었는데
로그를 DEVNULL 로 버려 잡에는 "죽었다" 한 줄만 남았다. 36분 회의가 그대로 실패로 끝났다.

실행: .venv/bin/python -m pytest tests/test_asr_restart.py
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["AZ_DATA"] = tempfile.mkdtemp(prefix="az-test-")   # config import 보다 먼저
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import jobs, stt  # noqa: E402

# 실제로 죽었을 때 llama-server 가 남기는 모양 — 원인 뒤로 gdb 백트레이스가 길게 붙는다.
CRASH_LOG = """\
ggml/src/ggml-cuda/ggml-cuda.cu:103: CUDA error
0.00.353.114 E CUDA error: out of memory
0.00.353.122 E   current device: 0, in function ggml_cuda_init at ggml-cuda.cu:309
0.00.353.123 E   cudaSetDevice(id)
[New LWP 1920953]
#0  0x0000e7f01bec7b74 in __GI___wait4 (pid=1920956)
#1  0x0000e7f01c38933c in ggml_print_backtrace ()
[Inferior 1 (process 1920950) detached]
"""


def test_err_tail_picks_the_cause_not_the_backtrace(tmp_path):
    log = tmp_path / "asr.log"
    log.write_text(CRASH_LOG, encoding="utf-8")
    tail = stt._err_tail(log)
    assert "out of memory" in tail          # 원인이 잡 로그까지 간다
    assert "Inferior" not in tail           # 백트레이스 꼬리가 아니라


def test_err_tail_falls_back_to_last_lines_and_missing_file(tmp_path):
    log = tmp_path / "plain.log"
    log.write_text("띄우는 중\n마지막 줄\n", encoding="utf-8")
    assert stt._err_tail(log) == "띄우는 중 / 마지막 줄"   # 오류 줄이 없으면 꼬리로
    assert stt._err_tail(tmp_path / "없는파일.log") == ""


def test_drop_page_cache_ignores_missing_paths(tmp_path):
    real = tmp_path / "a.wav"
    real.write_bytes(b"0" * 4096)
    stt.drop_page_cache(real, tmp_path / "없다.wav")      # 없는 파일에 안 터진다


def _wait(job_id: str, timeout: float = 60) -> dict:
    for _ in range(int(timeout * 10)):
        j = jobs.get_job(job_id)
        if j and j["status"] in ("done", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError(f"타임아웃: {jobs.get_job(job_id)}")


def _failed_job_with_wav(monkeypatch) -> str:
    """전사 단계에서 넘어진 잡 하나 — 녹음 wav 는 남는다(실제 사고와 같은 상태)."""
    monkeypatch.setattr(jobs.stt, "transcribe",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ASR 서버가 죽었다")))
    src = jobs.config.DATA / "up.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=1", "-ac", "1", "-c:a", "aac", str(src)],
                   check=True)
    job_id = jobs.create_recording_job(src)
    assert _wait(job_id)["status"] == "failed"
    return job_id


def test_retry_reruns_the_surviving_recording(monkeypatch):
    job_id = _failed_job_with_wav(monkeypatch)
    assert Path(jobs.get_job(job_id)["wav_path"]).exists()    # 녹음은 살아 있다

    monkeypatch.setattr(jobs.stt, "transcribe", lambda wav, log, progress=None: {
        "segments": [{"start": 0.0, "end": 1.0, "text": "다시 돌린 발화"}], "text": "다시 돌린 발화"})
    monkeypatch.setattr(jobs.summarize, "summarize", lambda text, log: "## 한 줄 요약\n재처리")
    monkeypatch.setattr(jobs.summarize, "make_title", lambda *a, **k: "재처리 회의")

    assert jobs.retry_job(job_id) is True
    j = _wait(job_id)
    assert j["status"] == "done"
    assert j["transcript"].endswith("다시 돌린 발화")
    assert j["reason"] is None                # 옛 실패 사유가 화면에 남지 않는다


def test_retry_refuses_when_there_is_nothing_to_rerun(monkeypatch):
    job_id = _failed_job_with_wav(monkeypatch)
    Path(jobs.get_job(job_id)["wav_path"]).unlink()
    assert jobs.retry_job(job_id) is False    # 녹음이 없으면 되돌릴 것도 없다
    assert jobs.retry_job("없는잡") is False
