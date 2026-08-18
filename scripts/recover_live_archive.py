"""라이브 종료를 기다린 뒤 유튜브 전체 다시보기를 받아 최종 전사한다."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import jobs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--title", default="라이브 전체 다시보기")
    parser.add_argument("--settle-seconds", type=int, default=120)
    parser.add_argument("--retry-seconds", type=int, default=300)
    args = parser.parse_args()

    while True:
        try:
            info = jobs._live_info(args.url)
            if not info.get("is_live"):
                break
            print("방송 진행 중 — 전체 다시보기 생성 대기", flush=True)
        except Exception as e:  # 방송 종료 직후 처리 중에는 yt-dlp 조회도 잠시 실패할 수 있다.
            print(f"방송 상태 확인 재시도: {type(e).__name__}", flush=True)
        time.sleep(60)

    # 유튜브가 다시보기 파일을 확정할 시간을 준다. 종료 직후에는 메타데이터에
    # 전체 길이가 보여도 실제 오디오는 앞부분만 준비될 수 있으므로 길이 검증에
    # 실패하면 준비가 끝날 때까지 다시 시도한다.
    time.sleep(max(0, args.settle_seconds))
    while True:
        job_id = jobs.create_media_job(args.url, args.title)
        print(f"전체 다시보기 작업 시작: {job_id}", flush=True)
        while True:
            job = jobs.get_job(job_id)
            if not job:
                return 2
            if job["status"] in {"done", "failed", "stopped"}:
                break
            time.sleep(10)
        print(f"전체 다시보기 작업 종료: {job['status']} / {job.get('reason') or ''}",
              flush=True)
        if job["status"] == "done":
            return 0
        reason = job.get("reason") or ""
        if "전체 영상이 아직 준비되지 않았다" not in reason:
            return 1
        print(f"유튜브 전체본 처리 대기 — {args.retry_seconds}초 뒤 재시도", flush=True)
        time.sleep(max(1, args.retry_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
