"""FastAPI 서버. 폼 하나로 예약·즉시 입장을 받고, 진행상황·요약을 보여준다."""
from __future__ import annotations

from fastapi import Body, FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import config, jobs, ui

app = FastAPI(title="auto_zoom", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _startup() -> None:
    jobs.init_db()          # 스케줄러 스레드도 여기서 뜬다


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(ui.index(jobs.list_jobs()))


@app.post("/jobs")
def create(url: str = Form(...), scheduled_at: str = Form(""),
           title: str = Form(""), bot_name: str = Form("")) -> RedirectResponse:
    url = url.strip()
    if "zoom.us" not in url:
        raise HTTPException(400, "Zoom 링크가 아니다")
    jobs.create_job(url, title.strip(), scheduled_at.strip() or None, bot_name)
    return RedirectResponse("/", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def detail(job_id: str) -> HTMLResponse:
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "없는 기록")
    return HTMLResponse(ui.detail(job))


@app.post("/api/jobs/{job_id}/stop")
def stop(job_id: str) -> JSONResponse:
    if not jobs.get_job(job_id):
        raise HTTPException(404, "없는 기록")
    jobs.stop_job(job_id)
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
