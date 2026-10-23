from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from mmc import __version__
from mmc.config.loader import load_app_config
from mmc.core.supervisor import RunSupervisor
from mmc.core.tokens import TokenEstimator
from mmc.display import (
    answers_cost_estimated,
    answers_cost_subtotal,
    format_answer_cost_usd,
    format_local_datetime,
    format_ms_rounded,
    judge_cost_subtotal,
    mock_pricing_label,
)
from mmc.logging_setup import configure_logging
from mmc.providers.registry import ProviderRegistry
from mmc.redact import Redactor
from mmc.service import CompareService
from mmc.settings import Settings
from mmc.storage.db import init_db
from mmc.storage.repository import RunRepository
from mmc.web.routes_api import router as api_router
from mmc.web.routes_pages import router as pages_router
from mmc.web.security import register_security_middleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    config = load_app_config(settings.config_dir)
    secrets = [v.get_secret_value() for v in settings.keys.values()]
    redactor = Redactor(secrets)
    configure_logging(settings, redactor)

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ANN202
        engine = init_db(settings.db_path)
        repo = RunRepository(engine)
        registry = ProviderRegistry(config, settings)
        estimator = TokenEstimator(settings.token_estimator)
        service = CompareService(config, settings, registry, repo, app.state.clock, redactor, estimator)
        supervisor = RunSupervisor(service, config.limits.max_concurrent_runs, config.limits.shutdown_grace_s)
        await supervisor.start()
        app.state.config = config
        app.state.settings = settings
        app.state.registry = registry
        app.state.repo = repo
        app.state.service = service
        app.state.supervisor = supervisor
        app.state.redactor = redactor
        yield
        await supervisor.drain()
        await registry.aclose()

    app = FastAPI(lifespan=lifespan)
    from mmc.clock import SystemClock

    app.state.clock = SystemClock()
    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    templates.env.filters["format_ms"] = format_ms_rounded
    templates.env.filters["format_local_datetime"] = format_local_datetime
    templates.env.globals["answers_cost_subtotal"] = answers_cost_subtotal
    templates.env.globals["answers_cost_estimated"] = answers_cost_estimated
    templates.env.globals["judge_cost_subtotal"] = judge_cost_subtotal
    templates.env.globals["format_answer_cost_usd"] = format_answer_cost_usd
    templates.env.globals["mock_pricing_label"] = mock_pricing_label
    app.state.templates = templates
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    register_security_middleware(app, settings, config)
    app.include_router(pages_router)
    app.include_router(api_router)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        try:
            app.state.repo.count()
            return JSONResponse(
                {
                    "status": "ok",
                    "db": "ok",
                    "profile": settings.profile,
                    "version": __version__,
                }
            )
        except Exception:
            return JSONResponse({"status": "error", "db": "error"}, status_code=503)

    return app
