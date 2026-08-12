"""잡 저장소 + 워커. URL 하나가 들어오면 입장→녹음→전사→요약까지 끌고 간다."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import audio, chunker, config, live_stt, stt, summarize, zoom_bot

_db_lock = threading.Lock()
_stop_flags: dict[str, bool] = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT,
  status TEXT NOT NULL,          -- scheduled|queued|joining|recording|transcribing|summarizing|done|failed|stopped
  reason TEXT,
  created_at TEXT NOT NULL,
  scheduled_at TEXT,
  ended_at TEXT,
  duration_s REAL DEFAULT 0,
  wav_path TEXT, transcript TEXT, summary TEXT, speakers TEXT, coresight_slug TEXT,
  bot_name TEXT, qa TEXT,
  log TEXT DEFAULT ''
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _db_lock, _conn() as c:
        c.executescript(SCHEMA)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(jobs)")}
        for col in ("scheduled_at", "coresight_slug", "bot_name", "qa"):   # 구버전 DB 마이그레이션
            if col not in cols:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")
    _ensure_scheduler()


def _update(job_id: str, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    with _db_lock, _conn() as c:
        c.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), job_id))


def append_log(job_id: str, line: str) -> None:
    stamped = f"[{datetime.now():%H:%M:%S}] {line}"
    with _db_lock, _conn() as c:
        c.execute("UPDATE jobs SET log = COALESCE(log,'') || ? WHERE id=?",
                  (stamped + "\n", job_id))
    print(f"{job_id[:8]} {stamped}", flush=True)


def create_job(url: str, title: str = "", scheduled_at: str | None = None,
               bot_name: str = "") -> str:
    """scheduled_at 이 미래면 그 시각까지 대기했다가 자동으로 입장한다(ISO 문자열)."""
    init_db()
    job_id = uuid.uuid4().hex
    due = None
    if scheduled_at:
        try:
            due = datetime.fromisoformat(scheduled_at)
        except ValueError:
            due = None
    is_future = bool(due and due > datetime.now())
    with _db_lock, _conn() as c:
        c.execute(
            "INSERT INTO jobs (id,url,title,status,created_at,scheduled_at,bot_name) "
            "VALUES (?,?,?,?,?,?,?)",
            (job_id, url, title or "", "scheduled" if is_future else "queued",
             datetime.now().isoformat(timespec="seconds"),
             due.isoformat(timespec="minutes") if due else None,
             (bot_name or "").strip() or config.BOT_NAME))
    if not is_future:
        threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
    else:
        append_log(job_id, f"예약됨 — {due:%Y-%m-%d %H:%M} 에 입장한다")
    return job_id


_scheduler: threading.Thread | None = None


def _ensure_scheduler() -> None:
    """예약 시각이 된 잡을 띄우는 단일 스레드."""
    global _scheduler
    if _scheduler and _scheduler.is_alive():
        return

    def loop() -> None:
        while True:
            try:
                now = datetime.now().isoformat(timespec="seconds")
                with _db_lock, _conn() as c:
                    rows = c.execute(
                        "SELECT id FROM jobs WHERE status='scheduled' AND scheduled_at<=?",
                        (now,)).fetchall()
                for r in rows:
                    _update(r["id"], status="queued")
                    append_log(r["id"], "예약 시각 도달 — 입장 시작")
                    threading.Thread(target=run_job, args=(r["id"],), daemon=True).start()
            except Exception as e:  # noqa: BLE001
                print(f"[scheduler] {type(e).__name__}: {e}", flush=True)
            time.sleep(20)

    _scheduler = threading.Thread(target=loop, daemon=True)
    _scheduler.start()


def get_job(job_id: str) -> dict | None:
    with _db_lock, _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit: int = 50) -> list[dict]:
    init_db()
    with _db_lock, _conn() as c:
        rows = c.execute(
            "SELECT id,url,title,status,reason,created_at,scheduled_at,ended_at,duration_s "
            "FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def ask_job(job_id: str, question: str) -> dict:
    """회의 원문을 근거로 로컬 LLM 에게 묻는다. 이력은 jobs.qa 에 쌓인다."""
    job = get_job(job_id)
    if not job:
        raise ValueError("없는 기록")
    if not (job.get("transcript") or "").strip():
        raise ValueError("아직 전사된 원문이 없다")
    question = (question or "").strip()
    if not question:
        raise ValueError("질문이 비었다")

    answer = summarize.ask(job["transcript"], question,
                           lambda m: append_log(job_id, m))
    history = json.loads(job.get("qa") or "[]")
    history.append({"q": question, "a": answer,
                    "at": datetime.now().isoformat(timespec="seconds")})
    _update(job_id, qa=json.dumps(history, ensure_ascii=False))
    return {"question": question, "answer": answer}


def publish_to_coresight(job_id: str) -> dict:
    """요약을 ArcAI.ve Coresight 카드로 올린다. 성공하면 slug 를 기록한다."""
    from . import coresight

    job = get_job(job_id)
    if not job:
        raise ValueError("없는 기록")
    res = coresight.publish(job)
    _update(job_id, coresight_slug=res["slug"])
    append_log(job_id, f"Coresight 업로드 완료 — {res['slug']}")
    return res


# 아직 회의에 들어가지 않은 상태들. 여기서 중지하면 남길 게 없으니 기록째 지운다.
PRE_JOIN = ("scheduled", "queued", "joining")


def stop_job(job_id: str) -> None:
    """봇을 회의에서 내보낸다. 입장 전에 중지한 회의는 기록을 바로 삭제한다."""
    job = get_job(job_id)
    if not job:
        return
    if job["status"] != "scheduled":      # 예약 대기엔 아직 워커 스레드가 없다
        _stop_flags[job_id] = True
    if job["status"] in PRE_JOIN:
        append_log(job_id, "입장 전 중지 — 기록을 삭제한다")
        delete_job(job_id)
        return
    append_log(job_id, "퇴장 요청 접수 — 회의에서 나간 뒤 전사·요약을 이어서 진행한다")


def set_title(job_id: str, title: str) -> bool:
    """제목 변경. 빈 값이면 목록에 '제목 없음' 으로 표시된다."""
    if not get_job(job_id):
        return False
    _update(job_id, title=(title or "").strip()[:80])
    return True


def autotitle(job_id: str, summary: str, log) -> str:
    """제목이 비어 있으면 요약에서 만들어 채운다. 붙인 제목이 이미 있으면 손대지 않는다.

    요약은 이미 저장된 뒤에 불린다 — LLM 이 죽어 있어도 요약·기록은 그대로 남아야 하므로
    여기서 나는 예외는 로그만 남기고 삼킨다.
    """
    job = get_job(job_id)          # 회의 중에 사용자가 제목을 붙였을 수 있으니 다시 읽는다
    if not job or (job.get("title") or "").strip():
        return ""
    try:
        title = summarize.make_title(summary, log)
    except Exception as e:  # noqa: BLE001
        log(f"제목 자동 생성 실패(요약은 정상): {type(e).__name__}: {e}")
        return ""
    if title:
        set_title(job_id, title)
        log(f"제목 자동 생성: {title}")
    return title


def _purge_files(job_id: str, wav: str | Path | None) -> None:
    for p in (wav, config.DATA / "transcripts" / f"{job_id}.txt"):
        if p:
            Path(p).unlink(missing_ok=True)


def delete_job(job_id: str) -> bool:
    """기록·녹음·전사를 완전히 지운다. 되돌릴 수 없다."""
    job = get_job(job_id)
    if not job:
        return False
    with _db_lock, _conn() as c:
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    _purge_files(job_id, job.get("wav_path"))
    print(f"{job_id[:8]} 기록 삭제됨", flush=True)
    return True


def _tail_dbfs(wav: Path, seconds: float) -> float:
    """wav 의 마지막 N초 평균 음량. 회의 종료(무음 지속) 판정에 쓴다."""
    total = chunker.duration_s(wav)
    if total <= seconds:
        return 0.0
    tmp = wav.with_suffix(".tail.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                    "-ss", f"{total - seconds:.2f}", str(tmp)], check=False)
    try:
        return chunker.mean_dbfs(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def run_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    log = lambda m: append_log(job_id, m)  # noqa: E731
    wav = config.DATA / "audio" / f"{job_id}.wav"
    live: live_stt.LiveTranscriber | None = None
    _update(job_id, status="joining", wav_path=str(wav))

    try:
        with audio.SinkRecorder(job_id, wav) as rec:
            quiet_since: float | None = None

            def on_tick(elapsed: float) -> str | None:
                nonlocal quiet_since
                if job["status"] != "recording":
                    _update(job_id, status="recording")
                if not config.SILENCE_END_S or elapsed < 120:
                    return None
                if int(elapsed) % 60 >= 3:      # 1분에 한 번만 검사
                    return None
                if _tail_dbfs(wav, 60) < config.ASR_MIN_DBFS:
                    quiet_since = quiet_since or elapsed
                    if elapsed - quiet_since > config.SILENCE_END_S:
                        return "무음 지속으로 회의 종료 판정"
                else:
                    quiet_since = None
                return None

            # 회의가 도는 동안 60초 단위로 계속 전사한다(종료 후 대기 시간을 없앤다).
            live = live_stt.LiveTranscriber(
                wav, log,
                on_progress=lambda segs: _update(
                    job_id, transcript=stt.format_transcript({"segments": segs})))
            live.start()

            log("회의 참가 시도")
            result = zoom_bot.join_and_wait(
                job["url"], rec.browser_env(), log,
                should_stop=lambda: _stop_flags.get(job_id, False),
                on_tick=on_tick, bot_name=job.get("bot_name") or config.BOT_NAME)
            log(f"회의 종료: {result.reason} ({result.duration_s:.0f}초)")

        _update(job_id, duration_s=result.duration_s, reason=result.reason,
                speakers=json.dumps(result.speakers, ensure_ascii=False))
        if not result.joined:
            live.cancel()          # 실시간 전사 워커가 남지 않게 한다
            _update(job_id, status="failed",
                    ended_at=datetime.now().isoformat(timespec="seconds"))
            return

        log("남은 구간 전사 마무리")
        segments = live.finish()
        if not segments:   # 실시간 전사가 아무것도 못 건졌으면 통째로 다시 돌린다(안전망)
            log("실시간 전사 결과 없음 — 전체 파일로 재시도")
        _wrap_up(job_id, wav, log, segments)

    except Exception as e:  # noqa: BLE001
        log(f"실패: {type(e).__name__}: {e}")
        _update(job_id, status="failed", reason=f"{type(e).__name__}: {e}",
                ended_at=datetime.now().isoformat(timespec="seconds"))
    finally:
        _stop_flags.pop(job_id, None)
        if live is not None:       # 어떤 경로로 끝나든 워커를 남기지 않는다
            live.cancel()
        if not get_job(job_id):    # 중지로 기록이 삭제됐으면 그 뒤 남은 파일도 남기지 않는다
            _purge_files(job_id, wav)


def _wrap_up(job_id: str, wav: Path, log, segments: list[dict] | None = None) -> None:
    """전사 → 요약 → 제목. 회의 봇과 직접 녹음이 함께 쓰는 뒷단.

    segments 가 있으면(회의 중 실시간 전사분) 그대로 쓰고, 없으면 wav 를 통째로 돌린다.
    """
    _update(job_id, status="transcribing")
    res = ({"segments": segments,
            "text": "\n".join(s["text"] for s in segments if s["text"])}
           if segments else stt.transcribe(wav, log))
    transcript = stt.format_transcript(res)
    (config.DATA / "transcripts" / f"{job_id}.txt").write_text(transcript, encoding="utf-8")
    _update(job_id, transcript=transcript)
    log(f"전사 완료: {len(res['segments'])}개 구간 / {len(transcript):,}자")

    _update(job_id, status="summarizing")
    summary = summarize.summarize(res["text"], log)
    _update(job_id, summary=summary, status="done",
            ended_at=datetime.now().isoformat(timespec="seconds"))
    log("완료")
    autotitle(job_id, summary, log)   # 요약을 먼저 확정한 뒤에 건드린다


def create_recording_job(src: Path, title: str = "") -> str:
    """폰·브라우저에서 올라온 녹음 파일 하나를 전사→요약까지 돌린다(회의 URL 이 없다)."""
    init_db()
    job_id = uuid.uuid4().hex
    wav = config.DATA / "audio" / f"{job_id}.wav"
    with _db_lock, _conn() as c:
        c.execute("INSERT INTO jobs (id,url,title,status,created_at,wav_path) "
                  "VALUES (?,?,?,?,?,?)",
                  (job_id, "", (title or "").strip()[:80], "transcribing",
                   datetime.now().isoformat(timespec="seconds"), str(wav)))
    threading.Thread(target=_run_recording, args=(job_id, src, wav), daemon=True).start()
    return job_id


def _run_recording(job_id: str, src: Path, wav: Path) -> None:
    log = lambda m: append_log(job_id, m)  # noqa: E731
    try:
        log(f"녹음 파일 접수 — {src.stat().st_size / 1e6:.1f}MB")
        # 폰은 m4a, 브라우저는 webm/opus 로 올린다 → ASR 규격(16k 모노 wav)으로 맞춘다.
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                        "-ar", "16000", "-ac", "1", str(wav)], check=True)
        src.unlink(missing_ok=True)
        _update(job_id, duration_s=chunker.duration_s(wav))
        _wrap_up(job_id, wav, log)
    except Exception as e:  # noqa: BLE001
        log(f"실패: {type(e).__name__}: {e}")
        _update(job_id, status="failed", reason=f"{type(e).__name__}: {e}",
                ended_at=datetime.now().isoformat(timespec="seconds"))
    finally:
        src.unlink(missing_ok=True)
        if not get_job(job_id):    # 처리 중에 삭제됐으면 뒤늦게 쓴 파일도 남기지 않는다
            _purge_files(job_id, wav)


def create_media_job(url: str, title: str = "") -> str:
    """영상 또는 라이브 링크를 녹음하면서 전사하고, 끝나면 요약한다."""
    init_db()
    job_id = uuid.uuid4().hex
    wav = config.DATA / "audio" / f"{job_id}.wav"
    with _db_lock, _conn() as c:
        c.execute("INSERT INTO jobs (id,url,title,status,created_at,wav_path) "
                  "VALUES (?,?,?,?,?,?)",
                  (job_id, url, (title or "").strip()[:80], "downloading",
                   datetime.now().isoformat(timespec="seconds"), str(wav)))
    threading.Thread(target=_run_media, args=(job_id, url, wav), daemon=True).start()
    return job_id


def _download_media(job_id: str, url: str, log) -> Path:
    """yt-dlp 로 오디오를 내려받는다(유튜브·대부분의 영상 사이트·mp4 직링크).

    제목을 안 넣은 잡은 영상 제목을 그대로 물려받는다 — LLM 추측보다 낫다.
    """
    import yt_dlp

    tmpl = config.DATA / "audio" / f"dl_{job_id}"
    opts = {"format": "bestaudio/best", "outtmpl": f"{tmpl}.%(ext)s",
            "noplaylist": True, "quiet": True, "no_warnings": True,
            "noprogress": True}   # quiet 만으로는 진행바가 stdout(서비스 로그)에 찍힌다

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info.get("is_live"):
            raise ValueError("현재 라이브 중인 영상이다")
        dur = info.get("duration") or 0
        if dur > config.MAX_MEETING_S:
            raise ValueError(f"영상이 {dur / 3600:.1f}시간 — "
                             f"한도 {config.MAX_MEETING_S // 3600}시간을 넘는다")
        job = get_job(job_id)
        if job and not (job.get("title") or "").strip() and info.get("title"):
            set_title(job_id, info["title"])
        log(f"내려받기 시작 — {info.get('title') or url}"
            + (f" ({int(dur) // 60}분)" if dur else ""))
        ydl.download([url])
    files = sorted((config.DATA / "audio").glob(f"dl_{job_id}.*"))
    if not files:
        raise RuntimeError("내려받은 파일이 없다")
    return files[0]


def _live_info(url: str) -> dict:
    """라이브 오디오 원본 URL을 구한다. 방송 전이면 yt-dlp가 예외를 낸다."""
    import yt_dlp

    opts = {"format": "bestaudio/best", "noplaylist": True, "quiet": True,
            "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _record_live(job_id: str, url: str, wav: Path, log) -> bool:
    """방송 시작을 기다렸다가 ffmpeg로 저장하며 실시간 전사한다.

    라이브가 아니면 False를 돌려 일반 영상 다운로드 경로로 넘긴다.
    """
    deadline = time.time() + config.WAIT_START_S
    announced = False
    info: dict | None = None
    while time.time() < deadline:
        if not get_job(job_id):
            return True
        if _stop_flags.get(job_id):
            raise RuntimeError("사용자 중단")
        try:
            info = _live_info(url)
            if not info.get("is_live"):
                return False
            break
        except Exception as e:  # yt-dlp: "This live event will begin in N minutes"
            msg = str(e).lower()
            if not any(x in msg for x in ("live event will begin", "premieres in",
                                           "not currently live", "scheduled for")):
                raise
            if not announced:
                _update(job_id, status="scheduled")
                log("라이브 시작 대기 중 — 방송이 열리면 자동으로 녹음한다")
                announced = True
            time.sleep(15)
    if not info:
        raise TimeoutError("라이브 시작 대기 시간이 지났다")

    if not (get_job(job_id) or {}).get("title") and info.get("title"):
        set_title(job_id, info["title"])
    stream_url = info.get("url")
    if not stream_url:
        raise RuntimeError("라이브 오디오 주소를 얻지 못했다")

    headers = info.get("http_headers") or {}
    header_text = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    cmd = ["ffmpeg", "-y", "-loglevel", "warning", "-reconnect", "1",
           "-reconnect_streamed", "1", "-reconnect_delay_max", "10"]
    if header_text:
        cmd += ["-headers", header_text]
    cmd += ["-i", stream_url, "-vn", "-ar", "16000", "-ac", "1", str(wav)]
    # 라이브 HLS는 끊긴 조각마다 경고를 많이 낸다. PIPE를 읽지 않으면 약 64KB 뒤
    # ffmpeg 자체가 멈추므로, 진행 로그에 필요한 종료 코드만 남기고 출력을 버린다.
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            text=True, env=dict(os.environ))
    live = live_stt.LiveTranscriber(
        wav, log,
        on_progress=lambda segs: _update(
            job_id, transcript=stt.format_transcript({"segments": segs})))
    live.start()
    _update(job_id, status="recording")
    log(f"라이브 녹음 시작 — {info.get('title') or url}")
    reason = "방송 종료"
    try:
        started = time.time()
        while proc.poll() is None:
            if not get_job(job_id):
                reason = "사용자 중단"
                proc.terminate()
                break
            if _stop_flags.get(job_id):
                reason = "사용자 중단"
                proc.terminate()
                break
            if time.time() - started > config.MAX_MEETING_S:
                reason = "최대 시간 초과"
                proc.terminate()
                break
            time.sleep(2)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        if proc.returncode not in (0, 255, -15):
            raise RuntimeError(f"라이브 녹음기가 비정상 종료했습니다 ({proc.returncode})")
        segments = live.finish()
        duration = chunker.duration_s(wav)
        _update(job_id, duration_s=duration, reason=reason)
        log(f"라이브 녹음 종료: {reason} ({duration / 60:.1f}분)")
        _wrap_up(job_id, wav, log, segments or None)
        return True
    finally:
        live.cancel()
        if proc.poll() is None:
            proc.terminate()
        _stop_flags.pop(job_id, None)


def _run_media(job_id: str, url: str, wav: Path) -> None:
    log = lambda m: append_log(job_id, m)  # noqa: E731
    try:
        if _record_live(job_id, url, wav, log):
            return
        src = _download_media(job_id, url, log)
        log(f"내려받기 완료 — {src.stat().st_size / 1e6:.1f}MB")
        # 직링크 mp4 처럼 영상이 섞여 와도 -vn 으로 소리만 ASR 규격(16k 모노)으로 뽑는다.
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                        "-vn", "-ar", "16000", "-ac", "1", str(wav)], check=True)
        _update(job_id, duration_s=chunker.duration_s(wav))
        _wrap_up(job_id, wav, log)
    except Exception as e:  # noqa: BLE001
        log(f"실패: {type(e).__name__}: {e}")
        _update(job_id, status="failed", reason=f"{type(e).__name__}: {e}",
                ended_at=datetime.now().isoformat(timespec="seconds"))
    finally:
        for p in (config.DATA / "audio").glob(f"dl_{job_id}.*"):
            p.unlink(missing_ok=True)
        if not get_job(job_id):    # 처리 중에 삭제됐으면 뒤늦게 쓴 파일도 남기지 않는다
            _purge_files(job_id, wav)


if __name__ == "__main__":   # CLI: python3 -m app.jobs <회의URL>
    import sys

    jid = create_job(sys.argv[1])
    print("job:", jid)
    while True:
        j = get_job(jid)
        if j and j["status"] in ("done", "failed", "stopped"):
            print(j["status"], j["reason"])
            break
        time.sleep(5)
