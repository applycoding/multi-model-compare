# Web UI and local security

The FastAPI application exposes HTML forms and JSON endpoints for running comparisons locally, with middleware aimed at loopback-style threat models rather than public multi-tenant hosting.

## What these modules do

`src/mmc/web/app.py` assembles routes from `routes_pages.py` (Jinja templates, history views) and `routes_api.py` (run submission, health checks). `src/mmc/web/security.py` registers middleware enforcing Host allowlists, CSRF tokens on mutating methods, Origin checks, `Sec-Fetch-Site` restrictions, body size limits from config, and strict Content-Security-Policy headers on responses.

`src/mmc/core/supervisor.py` wraps `CompareService` with a semaphore limiting concurrent runs, rejects new work while draining, and tracks in-flight asyncio tasks so shutdown can wait up to `grace_s` for completion.

Settings default `host` to `127.0.0.1`; Docker may bind `0.0.0.0` inside the container while operators publish only on loopback externally. Templates under `src/mmc/web/templates/` render run forms, answer tables, and history pagination; static assets live in `web/static/`. API routes return JSON suitable for the same CSRF-protected fetch calls the browser makes from `app.js`.

## Code excerpt

Security middleware essentials:

```python
# src/mmc/web/security.py
if host not in settings.allowed_hosts:
    return JSONResponse({"detail": "invalid host"}, status_code=400)
if request.method in ("POST", "DELETE"):
    ...
    if not token or not hmac.compare_digest(str(token), _csrf_token):
        return JSONResponse({"detail": "csrf"}, status_code=403)
response = await call_next(request)
security_headers(response)
```

Supervisor backpressure:

```python
# src/mmc/core/supervisor.py
if self._sem.locked():
    raise Busy("too many concurrent runs")
await self._sem.acquire()
task = asyncio.create_task(run_wrapped())
return await asyncio.shield(task)
```

## Why this design matters

Local tools still face CSRF from malicious pages in the browser: requiring a synchronised CSRF header on POST/DELETE blocks simple cross-site form posts to your mmc instance. CSP reduces XSS blast radius if template escaping ever regresses.

The supervisor prevents memory and API-key exhaustion when multiple tabs submit runs simultaneously, and `asyncio.shield` avoids losing partial work on client disconnect in some paths.

## Tests to run

Web routes and templates:

```bash
uv run pytest tests/unit/test_web.py -q
```

Security middleware behavior:

```bash
uv run pytest tests/unit/test_security.py -q
```

Supervisor concurrency and drain:

```bash
uv run pytest tests/unit/test_supervisor.py tests/unit/test_supervisor_lifecycle.py -q
```
