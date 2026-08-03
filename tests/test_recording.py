"""직접 녹음(업로드) 경로 최소 검증 — STT·요약 LLM 은 가짜로 갈아끼운다.

실행: .venv/bin/python -m pytest tests/test_recording.py
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["AZ_DATA"] = tempfile.mkdtemp(prefix="az-test-")   # config import 보다 먼저
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import jobs  # noqa: E402


def _fake_brains(monkeypatch):
    monkeypatch.setattr(jobs.stt, "transcribe", lambda wav, log, progress=None: {
        "segments": [{"start": 0.0, "end": 1.0, "text": "테스트 발화"}], "text": "테스트 발화"})
    monkeypatch.setattr(jobs.summarize, "summarize", lambda text, log: "## 한 줄 요약\n테스트")
    monkeypatch.setattr(jobs.summarize, "make_title", lambda *a, **k: "테스트 회의")


def _wait(job_id: str, timeout: float = 60) -> dict:
    for _ in range(int(timeout * 10)):
        j = jobs.get_job(job_id)
        if j and j["status"] in ("done", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError(f"타임아웃: {jobs.get_job(job_id)}")


def test_recording_job_transcribes_and_summarizes(monkeypatch):
    _fake_brains(monkeypatch)
    src = jobs.config.DATA / "up.m4a"      # 폰이 올리는 것과 같은 형식
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=1", "-ac", "1", "-c:a", "aac", str(src)],
                   check=True)

    j = _wait(jobs.create_recording_job(src))
    assert j["status"] == "done"
    assert j["transcript"].endswith("테스트 발화")
    assert j["summary"].startswith("## 한 줄 요약")
    assert j["title"] == "테스트 회의"        # 제목 자동 생성까지 이어진다
    assert j["url"] == ""                     # 회의 URL 이 없는 기록 = 직접 녹음
    assert j["duration_s"] > 0
    assert not src.exists()                   # 원본은 wav 변환 뒤 지운다
    assert Path(j["wav_path"]).exists()
    assert (jobs.config.DATA / "transcripts" / f"{j['id']}.txt").exists()


def test_broken_upload_fails_without_leftovers(monkeypatch):
    _fake_brains(monkeypatch)
    src = jobs.config.DATA / "junk.m4a"
    src.write_bytes(b"not audio" * 100)
    j = _wait(jobs.create_recording_job(src, "쓰레기"))
    assert j["status"] == "failed" and not src.exists()
