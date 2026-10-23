FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable
RUN TIKTOKEN_CACHE_DIR=/opt/tiktoken /app/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"

FROM python:3.13-slim
RUN useradd --system --uid 10001 --no-create-home app && install -d -o app -g app -m 0700 /data
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /opt/tiktoken /opt/tiktoken
ENV MMC_PROFILE=mock MMC_DB_PATH=/data/mmc.sqlite3 MMC_HOST=0.0.0.0 \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken OTEL_SDK_DISABLED=true PATH=/app/.venv/bin:$PATH
USER app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3).status==200 else 1)"
CMD ["mmc","serve","--host","0.0.0.0","--port","8000"]
