"""링크 전사(미디어 잡) 경로 최소 검증 — 다운로드·STT·요약은 가짜로 갈아끼운다.

실행: .venv/bin/python -m pytest tests/test_media.py
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
        "segments": [{"start": 0.0, "end": 1.0, "text": "영상 발화"}], "text": "영상 발화"})
    monkeypatch.setattr(jobs.summarize, "summarize", lambda text, log: "## 한 줄 요약\n테스트")
    monkeypatch.setattr(jobs.summarize, "make_title", lambda *a, **k: "LLM 제목")


def _wait(job_id: str, timeout: float = 60) -> dict:
    for _ in range(int(timeout * 10)):
        j = jobs.get_job(job_id)
        if j and j["status"] in ("done", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError(f"타임아웃: {jobs.get_job(job_id)}")


def _fake_download(job_id, url, log):
    """유튜브 대신 1초짜리 m4a 를 만들어 돌려주고, 영상 제목을 물려준다."""
    src = jobs.config.DATA / "audio" / f"dl_{job_id}.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=1", "-ac", "1", "-c:a", "aac",
                    str(src)], check=True)
    job = jobs.get_job(job_id)
    if job and not (job.get("title") or "").strip():
        jobs.set_title(job_id, "영상 제목")
    return src


def test_media_job_transcribes_with_video_title(monkeypatch):
    _fake_brains(monkeypatch)
    monkeypatch.setattr(jobs, "_record_live", lambda *args, **kwargs: False)
    monkeypatch.setattr(jobs, "_download_media", _fake_download)
    j = _wait(jobs.create_media_job("https://www.youtube.com/watch?v=x"))
    assert j["status"] == "done"
    assert j["transcript"].endswith("영상 발화")
    assert j["summary"].startswith("## 한 줄 요약")
    assert j["title"] == "영상 제목"      # 제목을 안 넣으면 LLM 추측보다 영상 제목이 이긴다
    assert j["url"].startswith("https://")
    assert j["duration_s"] > 0
    assert not list((jobs.config.DATA / "audio").glob(f"dl_{j['id']}.*"))  # 원본은 지운다
    assert Path(j["wav_path"]).exists()


def test_media_download_failure_marks_failed(monkeypatch):
    _fake_brains(monkeypatch)
    monkeypatch.setattr(jobs, "_record_live", lambda *args, **kwargs: False)

    def boom(job_id, url, log):
        raise ValueError("영상이 5.0시간 — 한도 4시간을 넘는다")

    monkeypatch.setattr(jobs, "_download_media", boom)
    j = _wait(jobs.create_media_job("https://example.com/v.mp4", "긴 영상"))
    assert j["status"] == "failed" and "한도" in j["reason"]
    assert j["title"] == "긴 영상"        # 사용자가 붙인 제목은 그대로 남는다
