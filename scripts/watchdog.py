"""장시간 회의용 감시견. 이상 징후가 보이면 즉시 종료해 호출자를 깨운다.

깨우는 조건
  1) 잡이 종료 상태(done/failed/stopped)에 도달
  2) 무음이 계속돼 자동 퇴장(15분) 이 임박  ← 미리 손 쓸 시간을 벌기 위함
  3) 녹음 파일이 자라지 않음(레코더 정지)
평상시엔 10분마다 한 줄씩 남기고 조용히 지켜본다.
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
POLL_S = 60
SILENCE_WARN_S = 600      # 자동 퇴장(900초) 전에 미리 깨운다
STALL_POLLS = 3           # 이만큼 연속으로 파일이 안 자라면 이상
QUIET_DBFS = -45.0


def say(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def job(job_id: str) -> dict:
    with urllib.request.urlopen(f"{BASE}/api/jobs/{job_id}", timeout=15) as r:
        return json.load(r)


def duration(wav: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(wav)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def tail_dbfs(wav: Path, seconds: float, total: float) -> float:
    args = ["ffmpeg"]
    if total > seconds:
        args += ["-ss", f"{total - seconds:.1f}"]
    err = subprocess.run(args + ["-i", str(wav), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    for line in err.splitlines():
        if "mean_volume" in line:
            try:
                return float(line.split("mean_volume:")[1].split("dB")[0])
            except (IndexError, ValueError):
                break
    return -100.0


def main(job_id: str) -> int:
    wav = AUDIO / f"{job_id}.wav"
    say(f"감시견 시작 job={job_id[:8]}")
    quiet_since: float | None = None
    last_dur = -1.0
    stalled = 0
    last_beat = 0.0

    while True:
        try:
            j = job(job_id)
        except Exception as e:  # noqa: BLE001
            say(f"상태 조회 실패(계속): {type(e).__name__}")
            time.sleep(POLL_S)
            continue

        st = j["status"]
        if st in TERMINAL:
            say(f"종료 상태: {st} / {j.get('reason')}")
            say(f"원문 {len(j.get('transcript') or '')}자 / 요약 {len(j.get('summary') or '')}자")
            say((j.get("log") or "")[-500:])
            return 0

        dur = duration(wav)
        now = time.time()

        if dur <= last_dur + 0.5:
            stalled += 1
            if stalled >= STALL_POLLS:
                say(f"경고: 녹음이 {stalled}회 연속 자라지 않음 (길이 {dur:.0f}s) — 레코더 정지 의심")
                return 2
        else:
            stalled = 0
        last_dur = dur

        db = tail_dbfs(wav, 300, dur)
        if db > QUIET_DBFS:
            quiet_since = None
        else:
            quiet_since = quiet_since or now
            if now - quiet_since >= SILENCE_WARN_S:
                say(f"경고: {int((now - quiet_since) / 60)}분째 무음 ({db:.0f} dB) — "
                    f"15분 도달 시 봇이 자동 퇴장한다")
                return 3

        if now - last_beat >= 600:
            last_beat = now
            say(f"정상 — {st} / 녹음 {dur / 60:.0f}분 / 최근5분 {db:.0f} dB")
        time.sleep(POLL_S)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
