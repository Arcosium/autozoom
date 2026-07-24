"""예약 잡을 지켜보다가 '결정적 사건' 이 생기면 종료한다(호출자를 깨우기 위함).

단계
  1) 예약 상태를 벗어날 때까지 대기 (입장 시각 도달)
  2) 입장/실패/무음 여부를 판정
종료 코드와 마지막 출력이 요약이다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8560"
AUDIO = Path("/home/arcosium/projects/autozoom/data/audio")
TERMINAL = {"done", "failed", "stopped"}


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return json.load(r)


def tail_dbfs(wav: Path, seconds: float = 90) -> float:
    """마지막 N초 평균 음량(dBFS). 파일이 짧으면 전체."""
    if not wav.exists():
        return -100.0
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(wav)], capture_output=True, text=True).stdout.strip()
    try:
        total = float(out)
    except ValueError:
        return -100.0
    args = ["ffmpeg", "-i", str(wav)]
    if total > seconds:
        args = ["ffmpeg", "-ss", f"{total - seconds:.1f}", "-i", str(wav)]
    err = subprocess.run(args + ["-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    for line in err.splitlines():
        if "mean_volume" in line:
            try:
                return float(line.split("mean_volume:")[1].split("dB")[0])
            except (IndexError, ValueError):
                return -100.0
    return -100.0


def say(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(job_id: str) -> int:
    say(f"감시 시작 job={job_id[:8]}")

    # 1단계: 예약 해제 대기 (최대 60분)
    deadline = time.time() + 3600
    while time.time() < deadline:
        j = get(f"/api/jobs/{job_id}")
        if j["status"] != "scheduled":
            say(f"입장 시작 — status={j['status']}")
            break
        time.sleep(20)
    else:
        say("예약이 시작되지 않았다(타임아웃)")
        return 3

    # 2단계: 결과 판정 (최대 45분)
    wav = AUDIO / f"{job_id}.wav"
    joined_at = None
    deadline = time.time() + 45 * 60
    while time.time() < deadline:
        j = get(f"/api/jobs/{job_id}")
        st = j["status"]
        if st in TERMINAL:
            say(f"종료 상태 도달: {st} / {j.get('reason')}")
            say((j.get("log") or "")[-600:])
            return 0 if st == "done" else 1
        if st == "recording" and joined_at is None:
            joined_at = time.time()
            say("회의 입장 확인 — 녹음 단계 진입")
        if joined_at:
            db = tail_dbfs(wav)
            if db > -45:
                say(f"오디오 정상 수신 확인 (최근 90초 {db:.1f} dB)")
                say((j.get("log") or "")[-400:])
                return 0
            if time.time() - joined_at > 8 * 60:
                say(f"경고: 입장 8분 경과했는데 계속 무음 ({db:.1f} dB)")
                say((j.get("log") or "")[-600:])
                return 2
        time.sleep(20)
    say("판정 타임아웃")
    return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
