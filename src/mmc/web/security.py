from __future__ import annotations

import hmac
import secrets
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from starlette.responses import JSONResponse, Response

from mmc.config.schemas import AppConfig
from mmc.settings import Settings

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)

_csrf_token = secrets.token_urlsafe(32)


def get_csrf_token() -> str:
    return _csrf_token


def security_headers(response: Response) -> None:
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"


def register_security_middleware(app: FastAPI, settings: Settings, config: AppConfig) -> None:
    max_body = config.limits.max_body_bytes

    @app.middleware("http")
    async def security_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        host = request.headers.get("host", "").split(":")[0]
        if host not in settings.allowed_hosts:
            return JSONResponse({"detail": "invalid host"}, status_code=400)
        if request.method in ("POST", "DELETE"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > max_body:
                return JSONResponse({"detail": "body too large"}, status_code=413)
            origin = request.headers.get("origin")
            if origin:
                parsed = urlparse(origin)
                if parsed.scheme != "http" or parsed.hostname not in settings.allowed_hosts:
                    return JSONResponse({"detail": "invalid origin"}, status_code=403)
            fetch_site = request.headers.get("sec-fetch-site")
            if fetch_site and fetch_site not in ("same-origin", "none"):
                return JSONResponse({"detail": "cross-site"}, status_code=403)
            token = request.headers.get("x-csrf-token")
            if not token or not hmac.compare_digest(str(token), _csrf_token):
                return JSONResponse({"detail": "csrf"}, status_code=403)
        response = await call_next(request)
        security_headers(response)
        return response
