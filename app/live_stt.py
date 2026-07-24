"""회의 진행 중 실시간 전사.

녹음이 끝나기를 기다리지 않고, 60초쯤 쌓일 때마다 그만큼을 잘라 STT 를 돌린다.
  * 회의 도중에도 원문이 계속 채워진다(대시보드에서 바로 읽힌다).
  * 회의가 끝나면 남은 꼬리만 처리하면 되므로 요약까지 훨씬 빨리 끝난다.
  * ASR 서버가 계속 따뜻하게 유지돼 매번 재기동하지 않는다.

경계 처리: 창의 끝을 무음 지점에 맞춰 자르고, 남은 꼬리는 다음 회차로 넘긴다.
그래야 단어가 두 동강 나지 않는다.
"""
from __future__ import annotations

import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from . import chunker, config, stt

Log = Callable[[str], None]

POLL_S = 15.0          # 파일 길이를 확인하는 주기
MIN_WINDOW_S = 60.0    # 이만큼 쌓이면 한 번 돌린다
TAIL_MARGIN_S = 2.0    # 아직 쓰이는 중인 끝부분은 건드리지 않는다


class LiveTranscriber:
    """녹음 중인 wav 를 따라가며 전사하는 워커."""

    def __init__(self, wav: Path, log: Log,
                 on_progress: Callable[[list[dict]], None] | None = None):
        self.wav = wav
        self.log = log
        self.on_progress = on_progress
        self.segments: list[dict] = []
        self.cursor = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------- 수명주기
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        """남은 구간 처리 없이 워커만 멈춘다(입장 실패 등으로 조기 종료할 때)."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=20)

    def finish(self, timeout: float = 900) -> list[dict]:
        """녹음 종료 후 호출 — 남은 꼬리까지 마저 전사하고 전체 구간을 돌려준다."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=30)
        self._process(final=True)
        return self.sorted_segments()

    def sorted_segments(self) -> list[dict]:
        with self._lock:
            return sorted(self.segments, key=lambda s: s["start"])

    # ------------------------------------------------------------- 내부
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._process()
            except Exception as e:  # noqa: BLE001
                self.log(f"실시간 전사 오류(계속 진행): {type(e).__name__}: {e}")
            self._stop.wait(POLL_S)

    def _process(self, final: bool = False) -> None:
        total = chunker.duration_s(self.wav)
        end = total if final else max(0.0, total - TAIL_MARGIN_S)
        avail = end - self.cursor
        if avail <= 0 or (not final and avail < MIN_WINDOW_S):
            return

        slice_path = Path(tempfile.mkstemp(prefix="azlive_", suffix=".wav",
                                           dir=str(config.DATA / "audio"))[1])
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{self.cursor:.3f}",
                 "-to", f"{end:.3f}", "-i", str(self.wav),
                 "-ar", "16000", "-ac", "1", str(slice_path)], check=False)
            if not slice_path.exists() or slice_path.stat().st_size < 2000:
                return

            res = stt.transcribe(slice_path, self.log)
            new = [{"start": s["start"] + self.cursor,
                    "end": s["end"] + self.cursor,
                    "text": s["text"]} for s in res["segments"] if s["text"]]

            # 마지막 구간의 끝(무음 경계)까지만 소비하고 꼬리는 다음 회차로 넘긴다.
            if new and not final:
                consumed = max(s["end"] for s in new)
                # 진행이 없으면(전부 한 덩어리) 창 전체를 소비해 교착을 피한다.
                self.cursor = consumed if consumed > self.cursor + 1 else end
            else:
                self.cursor = end

            if new:
                with self._lock:
                    self.segments.extend(new)
                self.log(f"실시간 전사 +{len(new)}구간 (~{self.cursor / 60:.1f}분까지)")
                if self.on_progress:
                    self.on_progress(self.sorted_segments())
        finally:
            slice_path.unlink(missing_ok=True)
