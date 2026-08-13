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


def test_video_upload_strips_picture_and_transcribes(monkeypatch):
    """직접 올린 회의 영상 — 영상 트랙이 붙어 있어도 소리만 떼어 전사한다(-vn)."""
    _fake_brains(monkeypatch)
    src = jobs.config.DATA / "meeting.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src)], check=True)

    j = _wait(jobs.create_recording_job(src, "회의 영상"))
    assert j["status"] == "done", j["log"]
    assert j["transcript"].endswith("테스트 발화")
    assert j["duration_s"] > 0
    assert not src.exists()


def test_chunked_upload_reassembles_and_rejects_bad_id(monkeypatch):
    """브라우저가 조각내 보낸 파일이 하나로 이어붙어 잡이 된다(CF 100MB 우회 경로)."""
    _fake_brains(monkeypatch)
    from fastapi.testclient import TestClient

    from app import auth, server

    auth.add_user("uploader", "pw1234")
    # 세션 쿠키가 Secure 라서 https 로 부른다(운영도 cloudflared 뒤 https).
    client = TestClient(server.app, base_url="https://testserver")
    assert client.post("/login", data={"username": "uploader", "password": "pw1234"},
                       follow_redirects=False).status_code == 303

    src = jobs.config.DATA / "chunky.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=1", "-ac", "1", "-c:a", "aac", str(src)],
                   check=True)
    raw, uid = src.read_bytes(), "a" * 32
    half = len(raw) // 2
    form = {"upload_id": uid, "filename": "회의 영상.mp4"}
    assert client.post("/api/upload", files={"chunk": raw[:half]},
                       data={**form, "last": "0"}).json() == {"ok": True}
    res = client.post("/api/upload", files={"chunk": raw[half:]},
                      data={**form, "title": "쪼갠 영상", "last": "1"}).json()
    assert res["ok"]
    j = _wait(res["id"])
    assert j["status"] == "done" and j["title"] == "쪼갠 영상"
    assert j["duration_s"] > 0                # 조각이 제대로 이어붙어야 ffmpeg 가 읽는다

    # 업로드 식별자는 파일 이름이 된다 — 경로 탈출을 막는다
    assert client.post("/api/upload", files={"chunk": b"x"},
                       data={"upload_id": "../../etc/passwd", "last": "1"}).status_code == 400


def test_broken_upload_fails_without_leftovers(monkeypatch):
    _fake_brains(monkeypatch)
    src = jobs.config.DATA / "junk.m4a"
    src.write_bytes(b"not audio" * 100)
    j = _wait(jobs.create_recording_job(src, "쓰레기"))
    assert j["status"] == "failed" and not src.exists()
