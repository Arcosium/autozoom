"""FastAPI 서버. 폼 하나로 예약·즉시 입장을 받고, 진행상황·요약을 보여준다."""
from __future__ import annotations

import os

from fastapi import Body, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from . import auth, config, jobs, ui

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
    return HTMLResponse(ui.admin(auth.list_users(), _require_admin(request)))


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
    url = url.strip()
    if "zoom.us" not in url:
        raise HTTPException(400, "Zoom 링크가 아니다")
    jobs.create_job(url, title.strip(), scheduled_at.strip() or None, bot_name)
    return RedirectResponse("/", status_code=303)


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
