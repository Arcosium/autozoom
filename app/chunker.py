"""긴 회의 wav 를 ASR 에 안전한 길이로 자른다.

왜 필요한가 (실측):
  * 60초까지는 Qwen3-ASR 이 37배속·무손실로 처리한다.
  * 5분 통짜를 넣으면 절삭 대신 **반복 환각**이 난다(30문장 → 144문장).
  * 완전 무음은 빈 출력이지만, 미약한 노이즈에는 엉뚱한 외국어를 지어낸다.
따라서 무음 경계에서 자르고, 조용한 청크는 아예 보내지 않는다.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import config

SIL_START = re.compile(r"silence_start:\s*([\d.]+)")
SIL_END = re.compile(r"silence_end:\s*([\d.]+)")
MEAN_VOL = re.compile(r"mean_volume:\s*(-?[\d.]+) dB")


@dataclass
class Chunk:
    path: Path
    start: float
    end: float


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True).stderr


def duration_s(wav: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(wav)],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def mean_dbfs(wav: Path) -> float:
    m = MEAN_VOL.search(_run(["ffmpeg", "-i", str(wav), "-af", "volumedetect", "-f", "null", "-"]))
    return float(m.group(1)) if m else -100.0


def _silence_midpoints(wav: Path) -> list[float]:
    """무음 구간의 중간 지점들 — 여기서 자르면 말이 잘리지 않는다."""
    err = _run(["ffmpeg", "-i", str(wav), "-af", "silencedetect=noise=-35dB:d=0.4",
                "-f", "null", "-"])
    starts = [float(x) for x in SIL_START.findall(err)]
    ends = [float(x) for x in SIL_END.findall(err)]
    return [(s + e) / 2 for s, e in zip(starts, ends)]


def split_on_silence(wav: Path, max_len: float | None = None) -> list[Chunk]:
    """무음 경계 기준으로 max_len 이하 청크로 자른다. 조용한 청크는 버린다."""
    max_len = max_len or config.ASR_CHUNK_S
    total = duration_s(wav)
    if total <= 0:
        return []

    cuts = [c for c in _silence_midpoints(wav) if 0 < c < total]
    bounds: list[float] = [0.0]
    while bounds[-1] < total - 0.5:
        lo = bounds[-1]
        hard = lo + max_len
        if hard >= total:
            bounds.append(total)
            break
        # lo 이후 hard 이전의 마지막 무음 지점에서 자른다(없으면 강제 절단).
        cand = [c for c in cuts if lo + max_len * 0.4 < c <= hard]
        bounds.append(cand[-1] if cand else hard)

    outdir = Path(tempfile.mkdtemp(prefix="azchunk_", dir=str(config.DATA / "audio")))
    chunks: list[Chunk] = []
    for i, (s, e) in enumerate(zip(bounds, bounds[1:])):
        if e - s < 0.6:
            continue
        p = outdir / f"c{i:05d}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
             "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
             "-ar", "16000", "-ac", "1", str(p)],
            check=False)
        if not p.exists():
            continue
        if mean_dbfs(p) < config.ASR_MIN_DBFS:   # 사실상 무음 → 환각 방지를 위해 스킵
            p.unlink(missing_ok=True)
            continue
        chunks.append(Chunk(p, s, e))
    return chunks
