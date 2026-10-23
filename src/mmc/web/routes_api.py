from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from mmc.core.request import RequestValidationError, RunRequest, resolve_request
from mmc.core.supervisor import Busy
from mmc.web.security import get_csrf_token

router = APIRouter(prefix="/api")


@router.get("/csrf")
async def csrf() -> dict[str, str]:
    return {"csrf_token": get_csrf_token()}


@router.post("/runs")
async def api_create_run(request: Request, body: RunRequest) -> JSONResponse:
    try:
        resolved = resolve_request(
            body,
            request.app.state.config,
            request.app.state.settings,
            request.app.state.redactor,
            request.app.state.registry,
        )
    except RequestValidationError as exc:
        return JSONResponse({"errors": exc.errors}, status_code=422)
    try:
        record = await request.app.state.supervisor.submit(resolved)
    except Busy:
        return JSONResponse({"detail": "busy"}, status_code=503, headers={"Retry-After": "5"})
    return JSONResponse(record.model_dump(mode="json"), status_code=201)


@router.get("/runs")
async def api_list_runs(
    request: Request, limit: int = 50, offset: int = 0, q: str | None = None
) -> list[dict[str, object]]:
    rows = request.app.state.repo.list(limit=limit, offset=offset, q=q)
    return [r.model_dump(mode="json") for r in rows]


@router.get("/runs/{run_id}")
async def api_get_run(request: Request, run_id: str) -> JSONResponse:
    record = request.app.state.repo.get(run_id)
    if record is None:
        return JSONResponse({"detail": "not found"}, status_code=404)
    return JSONResponse(record.model_dump(mode="json"))


@router.delete("/runs/{run_id}")
async def api_delete_run(run_id: str, request: Request) -> Response:
    if not request.app.state.repo.delete(run_id):
        return Response(status_code=404)
    return Response(status_code=204)


@router.get("/providers")
async def api_providers(request: Request) -> list[dict[str, object]]:
    service = request.app.state.service
    out = []
    for spec, available, reason in service.models_with_availability():
        out.append(
            {
                "key": spec.key,
                "vendor": spec.vendor,
                "available": available,
                "skip_reason": reason,
            }
        )
    return out
