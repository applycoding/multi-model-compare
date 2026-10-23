from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from mmc.core.request import RequestValidationError, RunRequest, resolve_request
from mmc.core.supervisor import Busy
from mmc.export import to_csv, to_json
from mmc.web.security import get_csrf_token

router = APIRouter()


def _templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    config = request.app.state.config
    settings = request.app.state.settings
    registry = request.app.state.registry
    profile = config.profiles[settings.profile]
    models = []
    for m in config.models:
        ok, reason = registry.availability(m)
        models.append({"spec": m, "available": ok, "skip_reason": reason})
    return _templates(request).TemplateResponse(
        request,
        "index.html",
        {
            "profile": settings.profile,
            "models": models,
            "default_contestants": profile.contestants,
            "default_judge": profile.judge,
            "csrf_token": get_csrf_token(),
        },
    )


@router.post("/runs", response_model=None)
async def create_run(
    request: Request,
    prompt: str = Form(""),
    models: list[str] = Form(default=[]),  # noqa: B008
    judge: str = Form(""),
    temperature: float | None = Form(None),
    max_output_tokens: int | None = Form(None),
    timeout_s: float | None = Form(None),
    allow_self_judging: bool = Form(False),
    seed: int | None = Form(None),
    csrf_token: str = Form(""),
) -> RedirectResponse | HTMLResponse:
    run_req = RunRequest(
        prompt=prompt,
        models=models or None,
        judge=judge or None,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        timeout_s=timeout_s,
        allow_self_judging=allow_self_judging or None,
        seed=seed,
    )
    try:
        resolved = resolve_request(
            run_req,
            request.app.state.config,
            request.app.state.settings,
            request.app.state.redactor,
            request.app.state.registry,
        )
    except RequestValidationError as exc:
        return _templates(request).TemplateResponse(
            request,
            "index.html",
            {"errors": exc.errors, "csrf_token": get_csrf_token()},
            status_code=422,
        )
    supervisor = request.app.state.supervisor
    try:
        record = await supervisor.submit(resolved)
    except Busy:
        return HTMLResponse("busy", status_code=503, headers={"Retry-After": "5"})
    return RedirectResponse(url=f"/runs/{record.id}", status_code=303)


def hmac_compare(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a, b)


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def show_run(request: Request, run_id: str) -> HTMLResponse:
    repo = request.app.state.repo
    record = repo.get(run_id)
    if record is None:
        return HTMLResponse("not found", status_code=404)
    return _templates(request).TemplateResponse(
        request,
        "run.html",
        {"record": record, "csrf_token": get_csrf_token()},
    )


@router.post("/runs/{run_id}/delete")
async def delete_run(request: Request, run_id: str, csrf_token: str = Form("")) -> RedirectResponse:
    if not hmac_compare(csrf_token, get_csrf_token()):
        return RedirectResponse("/", status_code=403)
    request.app.state.repo.delete(run_id)
    return RedirectResponse("/history", status_code=303)


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request, q: str = "", page: int = 1) -> HTMLResponse:
    repo = request.app.state.repo
    limit = 20
    offset = (page - 1) * limit
    rows = repo.list(limit=limit, offset=offset, q=q or None)
    total = repo.count(q=q or None)
    return _templates(request).TemplateResponse(
        request,
        "history.html",
        {
            "runs": rows,
            "q": q,
            "page": page,
            "total_pages": max(1, (total + limit - 1) // limit),
            "csrf_token": get_csrf_token(),
        },
    )


@router.post("/history/clear")
async def clear_history(request: Request, csrf_token: str = Form("")) -> RedirectResponse:
    if not hmac_compare(csrf_token, get_csrf_token()):
        return RedirectResponse("/", status_code=403)
    request.app.state.repo.clear()
    return RedirectResponse("/history", status_code=303)


@router.get("/runs/{run_id}/export.json")
async def export_run_json(run_id: str, request: Request) -> Response:
    record = request.app.state.repo.get(run_id)
    if record is None:
        return Response(status_code=404)
    from datetime import UTC, datetime

    body = to_json([record], datetime.now(UTC))
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'},
    )


@router.get("/runs/{run_id}/export.csv")
async def export_run_csv(run_id: str, request: Request) -> Response:
    record = request.app.state.repo.get(run_id)
    if record is None:
        return Response(status_code=404)
    body = to_csv([record])
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'},
    )


@router.get("/export/runs.json")
async def export_all_json(request: Request) -> Response:
    from datetime import UTC, datetime

    records = list(request.app.state.repo.iter_all())
    body = to_json(records, datetime.now(UTC))
    return Response(content=body, media_type="application/json")


@router.get("/export/runs.csv")
async def export_all_csv(request: Request) -> Response:
    records = list(request.app.state.repo.iter_all())
    return Response(content=to_csv(records), media_type="text/csv")
