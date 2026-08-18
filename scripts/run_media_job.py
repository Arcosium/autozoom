"""미디어 작업을 별도 프로세스에서 실행하고 완료될 때까지 유지한다."""
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
    parser.add_argument("--title", default="")
    args = parser.parse_args()

    job_id = jobs.create_media_job(args.url, args.title)
    print(f"미디어 작업 시작: {job_id}", flush=True)
    while True:
        job = jobs.get_job(job_id)
        if not job:
            return 2
        if job["status"] in {"done", "failed", "stopped"}:
            print(f"미디어 작업 종료: {job['status']} / {job.get('reason') or ''}",
                  flush=True)
            return 0 if job["status"] == "done" else 1
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
