"""FastAPI 서버. 폼 하나로 예약·즉시 입장을 받고, 진행상황·요약을 보여준다."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from . import auth, bot_login, config, jobs, links, remote_login, ui

app = FastAPI(title="auto_zoom", docs_url=None, redoc_url=None)

PUBLIC_PATHS = {"/login", "/signup", "/health"}


@app.middleware("http")
async def _require_login(request: Request, call_next):
    """로그인 게이트 — 라우트마다 검사하지 않고 여기 한 곳에서 막는다."""
    if request.url.path in PUBLIC_PATHS or request.session.get("user"):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"ok": False, "error": "로그인이 필요하다"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


# 게이트보다 나중에 추가해야 더 바깥에 놓여 request.session 이 게이트에서 이미 채워진다.
app.add_middleware(SessionMiddleware, secret_key=auth.session_secret(),
                   session_cookie="az_session", max_age=14 * 24 * 3600,
                   same_site="lax",
                   # 운영은 https(cloudflared) 뒤 — 평문 http 로컬 테스트에서만 1 로 끈다.
                   https_only=os.getenv("AZ_COOKIE_INSECURE") != "1")


def _me(request: Request) -> str:
    return request.session.get("user") or ""


def _require_admin(request: Request) -> str:
    me = _me(request)
    if not auth.is_admin(me):
        raise HTTPException(403, "관리자만 할 수 있다")
    return me


@app.on_event("startup")
def _startup() -> None:
    jobs.init_db()          # 스케줄러 스레드도 여기서 뜬다
    for leftover in (config.DATA / "audio").glob("up_*"):
        leftover.unlink(missing_ok=True)   # 재시작으로 끊긴 업로드 조각. 살릴 잡이 없다


@app.get("/login", response_class=HTMLResponse)
def login_page() -> HTMLResponse:
    return HTMLResponse(ui.login())


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(""), password: str = Form("")):
    if not auth.check_login(username, password):
        return HTMLResponse(ui.login("아이디·비밀번호가 맞지 않거나 아직 승인되지 않았다."),
                            status_code=401)
    request.session["user"] = username.strip()
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/signup", response_class=HTMLResponse)
def signup_page() -> HTMLResponse:
    return HTMLResponse(ui.signup())


@app.post("/signup", response_class=HTMLResponse)
def signup(username: str = Form(""), password: str = Form("")) -> HTMLResponse:
    ok, msg = auth.create_pending(username, password)
    return HTMLResponse(ui.notice(msg, ok) if ok else ui.signup(msg),
                        status_code=200 if ok else 400)


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request) -> HTMLResponse:
    return HTMLResponse(ui.admin(auth.list_users(), _require_admin(request), bot_login.status()))


@app.post("/admin/zoom-login")
def start_bot_login(request: Request) -> RedirectResponse:
    """Zoom 계정 로그인 창은 관리자만 열 수 있다."""
    _require_admin(request)
    bot_login.start()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/zoom-login/otp")
def submit_bot_login_otp(request: Request, otp: str = Form("")) -> RedirectResponse:
    _require_admin(request)
    try:
        bot_login.submit_otp(otp)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse("/admin", status_code=303)


@app.post("/api/remote-login/start")
def remote_start(request: Request) -> JSONResponse:
    """서버 봇 브라우저를 띄워 관리자가 화면을 보며 직접 로그인한다."""
    _require_admin(request)
    return JSONResponse(remote_login.start())


@app.post("/api/remote-login/stop")
def remote_stop(request: Request) -> JSONResponse:
    _require_admin(request)
    remote_login.stop()
    return JSONResponse({"ok": True})


@app.get("/api/remote-login/status")
def remote_status(request: Request) -> JSONResponse:
    _require_admin(request)
    return JSONResponse(remote_login.status())


@app.get("/api/remote-login/screen.jpg")
def remote_screen(request: Request):
    _require_admin(request)
    from fastapi.responses import Response

    return Response(remote_login.screenshot() or b"", media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.post("/api/remote-login/event")
def remote_event(request: Request, event: dict = Body(...)) -> JSONResponse:
    _require_admin(request)
    try:
        remote_login.send(event)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    return JSONResponse({"ok": True})


@app.post("/admin/{action}")
def admin_act(request: Request, action: str, username: str = Form(...)) -> RedirectResponse:
    me = _require_admin(request)
    fn = {"approve": auth.approve, "reject": auth.reject, "remove": auth.remove}.get(action)
    if not fn:
        raise HTTPException(404, "없는 동작")
    if username == me and action != "approve":
        raise HTTPException(400, "자기 계정은 거절·삭제할 수 없다")
    fn(username)
    return RedirectResponse("/admin", status_code=303)


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    me = _me(request)
    return HTMLResponse(ui.index(jobs.list_jobs(), me, auth.is_admin(me)))


@app.post("/jobs")
def create(url: str = Form(...), scheduled_at: str = Form(""),
           title: str = Form(""), bot_name: str = Form("")) -> RedirectResponse:
    """링크 종류를 확인해 Zoom 봇 또는 영상 전사 작업으로 자동 분기한다."""
    try:
        resolved = links.resolve_url(url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if links.is_zoom_url(resolved):
        jobs.create_job(resolved, title.strip(), scheduled_at.strip() or None, bot_name)
        tab = "zoom"
    else:
        jobs.create_media_job(resolved, title.strip())
        tab = "media"
    return RedirectResponse(f"/#{tab}", status_code=303)


@app.post("/media")
def create_media(url: str = Form(...), title: str = Form("")) -> RedirectResponse:
    """최종 주소가 Zoom이면 봇을 보내고, 나머지는 영상·라이브로 처리한다."""
    try:
        resolved = links.resolve_url(url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if links.is_zoom_url(resolved):
        jobs.create_job(resolved, title.strip())
        tab = "zoom"
    else:
        jobs.create_media_job(resolved, title.strip())
        tab = "media"
    return RedirectResponse(f"/#{tab}", status_code=303)


SUFFIX_OK = re.compile(r"\.(webm|m4a|mp4|ogg|opus|wav|mp3|aac|3gp|"
                       r"mkv|mov|avi|wmv|flv|ts|m4v|mpg|mpeg)$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")


@app.post("/api/record")
async def record(audio: UploadFile = File(...), title: str = Form("")) -> JSONResponse:
    """브라우저 녹음 버튼·앱 위젯이 올린 녹음 파일 하나 → 전사·요약.

    파일은 통째로 메모리에 올리지 않고 흘려 쓴다(회의 두 시간이면 수십 MB 다).
    """
    suffix = Path(audio.filename or "").suffix.lower()
    src = config.DATA / "audio" / f"up_{uuid.uuid4().hex}{suffix if SUFFIX_OK.match(suffix) else '.bin'}"
    size = 0
    with src.open("wb") as f:
        while chunk := await audio.read(1 << 20):
            size += len(chunk)
            f.write(chunk)
    if size < 8000:                      # 사실상 빈 녹음 — 잡을 만들지 않는다
        src.unlink(missing_ok=True)
        return JSONResponse({"ok": False, "error": "녹음이 너무 짧다"}, status_code=400)
    return JSONResponse({"ok": True, "id": jobs.create_recording_job(src, title)})


@app.post("/api/upload")
async def upload(chunk: UploadFile = File(...), upload_id: str = Form(...),
                 filename: str = Form(""), title: str = Form(""),
                 last: str = Form("")) -> JSONResponse:
    """동영상·오디오 파일을 직접 올려 전사·요약한다.

    Cloudflare 프록시가 요청 하나를 100MB 에서 자르므로 브라우저가 조각내 순서대로
    보내고 여기서 이어붙인다. 마지막 조각에서만 잡이 만들어진다.
    """
    if not HEX32.match(upload_id):
        raise HTTPException(400, "잘못된 업로드 식별자")
    suffix = Path(filename).suffix.lower()   # 경로가 섞여 와도 확장자만, 그것도 화이트리스트로
    dst = config.DATA / "audio" / f"up_{upload_id}{suffix if SUFFIX_OK.match(suffix) else '.bin'}"
    with dst.open("ab") as f:
        while part := await chunk.read(1 << 20):
            f.write(part)
    if last != "1":
        return JSONResponse({"ok": True})
    if dst.stat().st_size < 8000:            # 사실상 빈 파일 — 잡을 만들지 않는다
        dst.unlink(missing_ok=True)
        return JSONResponse({"ok": False, "error": "파일이 너무 작다"}, status_code=400)
    return JSONResponse({"ok": True, "id": jobs.create_recording_job(dst, title)})


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def detail(request: Request, job_id: str) -> HTMLResponse:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "없는 기록")
    me = _me(request)
    return HTMLResponse(ui.detail(job, me, auth.is_admin(me)))


@app.post("/jobs/{job_id}/title")
def retitle(job_id: str, title: str = Form("")) -> RedirectResponse:
    if not jobs.set_title(job_id, title):
        raise HTTPException(404, "없는 기록")
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@app.post("/api/jobs/{job_id}/stop")
def stop(job_id: str) -> JSONResponse:
    if not jobs.get_job(job_id):
        raise HTTPException(404, "없는 기록")
    jobs.stop_job(job_id)     # 입장 전이었으면 여기서 기록이 삭제된다
    return JSONResponse({"ok": True, "deleted": jobs.get_job(job_id) is None})


@app.delete("/api/jobs/{job_id}")
def delete(job_id: str) -> JSONResponse:
    """과거 기록 삭제 — 되돌릴 수 없다."""
    if not jobs.delete_job(job_id):
        raise HTTPException(404, "없는 기록")
    return JSONResponse({"ok": True})


@app.post("/api/jobs/{job_id}/ask")
def ask(job_id: str, question: str = Body(..., embed=True)) -> JSONResponse:
    if not jobs.get_job(job_id):
        raise HTTPException(404, "없는 기록")
    try:
        res = jobs.ask_job(job_id, question)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)
    # 화면 렌더는 서버에서 한다(이력과 같은 마크다운 처리를 쓰기 위해).
    return JSONResponse({"ok": True, **res, "answer_html": ui.md_to_html(res["answer"])})


@app.post("/api/jobs/{job_id}/coresight")
def to_coresight(job_id: str) -> JSONResponse:
    if not jobs.get_job(job_id):
        raise HTTPException(404, "없는 기록")
    try:
        res = jobs.publish_to_coresight(job_id)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)
    return JSONResponse({"ok": True, **res})


@app.get("/api/jobs")
def api_list() -> JSONResponse:
    return JSONResponse(jobs.list_jobs())


@app.get("/api/jobs/{job_id}")
def api_detail(job_id: str) -> JSONResponse:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "없는 기록")
    return JSONResponse(job)


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
