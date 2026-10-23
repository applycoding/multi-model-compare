from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from mmc.clock import SystemClock
from mmc.config.loader import load_app_config
from mmc.config.schemas import AppConfig
from mmc.core.request import RequestValidationError, RunRequest, resolve_request
from mmc.core.tokens import TokenEstimator
from mmc.disclosure import cli_run_disclosure
from mmc.export import to_csv, to_json
from mmc.logging_setup import configure_logging
from mmc.providers.registry import ProviderRegistry
from mmc.records import RunRecord
from mmc.redact import Redactor
from mmc.service import CompareService
from mmc.settings import Settings
from mmc.storage.db import init_db
from mmc.storage.repository import RunRepository


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    parser = _build_parser()
    try:
        ns = parser.parse_args(args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2
    settings = Settings.from_env()
    if ns.profile:
        settings = settings.model_copy(update={"profile": ns.profile})
    secrets = [v.get_secret_value() for v in settings.keys.values()]
    redactor = Redactor(secrets)
    configure_logging(settings, redactor)
    config = load_app_config(settings.config_dir)
    engine = init_db(settings.db_path)
    repo = RunRepository(engine)

    if ns.cmd == "run":
        return _cmd_run(ns, config, settings, redactor, repo)
    if ns.cmd == "providers":
        return _cmd_providers(config, settings)
    if ns.cmd == "history":
        return _cmd_history(ns, repo)
    if ns.cmd == "show":
        return _cmd_show(ns, repo)
    if ns.cmd == "export":
        return _cmd_export(ns, repo)
    if ns.cmd == "clear":
        return _cmd_clear(ns, repo)
    if ns.cmd == "serve":
        return _cmd_serve(ns, settings)
    return 2


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mmc")
    p.add_argument("--profile", choices=["mock", "live"])
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("prompt")
    run.add_argument("--models")
    run.add_argument("--judge")
    run.add_argument("--temperature", type=float)
    run.add_argument("--max-tokens", type=int)
    run.add_argument("--timeout", type=float)
    run.add_argument("--allow-self-judging", action="store_true")
    run.add_argument("--seed", type=int)
    run.add_argument("--json", action="store_true")
    sub.add_parser("providers")
    hist = sub.add_parser("history")
    hist.add_argument("--limit", type=int, default=20)
    hist.add_argument("--q")
    hist.add_argument("--json", action="store_true")
    show = sub.add_parser("show")
    show.add_argument("run_id")
    show.add_argument("--json", action="store_true")
    exp = sub.add_parser("export")
    exp.add_argument("--format", choices=["json", "csv"], required=True)
    exp.add_argument("--run-id")
    exp.add_argument("--out", required=True)
    clr = sub.add_parser("clear")
    clr.add_argument("--run-id")
    clr.add_argument("--all", action="store_true")
    clr.add_argument("--yes", action="store_true")
    srv = sub.add_parser("serve")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    return p


def _cmd_run(
    ns: argparse.Namespace,
    config: AppConfig,
    settings: Settings,
    redactor: Redactor,
    repo: RunRepository,
) -> int:
    models = ns.models.split(",") if ns.models else None
    req = RunRequest(
        prompt=ns.prompt,
        models=models,
        judge=ns.judge,
        temperature=ns.temperature,
        max_output_tokens=ns.max_tokens,
        timeout_s=ns.timeout,
        allow_self_judging=ns.allow_self_judging or None,
        seed=ns.seed,
    )
    registry = ProviderRegistry(config, settings)
    try:
        resolved = resolve_request(req, config, settings, redactor, registry)
    except RequestValidationError as exc:
        for field, msg in exc.errors:
            print(f"error: {field}: {msg}", file=sys.stderr)
        return 2
    print(cli_run_disclosure(settings.profile, resolved.vendors_contacted), file=sys.stderr)

    async def _go() -> RunRecord:
        service = CompareService(
            config,
            settings,
            registry,
            repo,
            SystemClock(),
            redactor,
            TokenEstimator(settings.token_estimator),
        )
        return await service.run(resolved)

    try:
        record = asyncio.run(_go())
    finally:
        asyncio.run(registry.aclose())
    if ns.json:
        print(json.dumps(record.model_dump(mode="json"), indent=2))
    else:
        for ans in record.answers:
            ttft = ans.timing.ttft_ms if ans.timing else None
            total_ms = ans.timing.total_ms if ans.timing else None
            cost_usd = ans.cost.total_usd if ans.cost and ans.cost.total_usd is not None else None
            print(
                f"{ans.model.key}\t{ans.status}\t"
                f"ttft_ms={ttft}\ttotal_ms={total_ms}\tcost_usd={cost_usd}\t"
                f"{ans.text[:80]}"
            )
        if record.judge:
            for model_key, scores in sorted(record.judge.scores.items()):
                crit = ",".join(f"{k}={v.score}" for k, v in sorted(scores.criteria.items()))
                print(f"judge_score\t{model_key}\toverall={scores.overall}\t{crit}")
            for excl, reason in sorted(record.judge.excluded.items()):
                print(f"judge_excluded\t{excl}\t{reason}")
    return 0


def _cmd_providers(config: AppConfig, settings: Settings) -> int:
    registry = ProviderRegistry(config, settings)
    for m in config.models:
        ok, reason = registry.availability(m)
        print(f"{m.key}\t{m.vendor}\t{ok}\t{reason or ''}")
    return 0


def _cmd_history(ns: argparse.Namespace, repo: RunRepository) -> int:
    rows = repo.list(limit=ns.limit, q=ns.q)
    if ns.json:
        print(json.dumps([r.model_dump(mode="json") for r in rows], indent=2))
    else:
        for r in rows:
            print(f"{r.id}\t{r.created_at}\t{r.prompt_preview}")
    return 0


def _cmd_show(ns: argparse.Namespace, repo: RunRepository) -> int:
    record = repo.get(ns.run_id)
    if record is None:
        return 2
    if ns.json:
        print(record.model_dump_json(indent=2))
    else:
        print(record.id, record.status)
    return 0


def _cmd_export(ns: argparse.Namespace, repo: RunRepository) -> int:
    from datetime import UTC, datetime

    if ns.run_id:
        record = repo.get(ns.run_id)
        records = [record] if record else []
    else:
        records = list(repo.iter_all())
    out = to_json(records, datetime.now(UTC)) if ns.format == "json" else to_csv(records)
    if ns.out == "-":
        sys.stdout.write(out)
    else:
        Path(ns.out).write_text(out, encoding="utf-8")
    return 0


def _cmd_clear(ns: argparse.Namespace, repo: RunRepository) -> int:
    if not ns.yes:
        return 2
    if ns.all:
        repo.clear()
    elif ns.run_id:
        repo.delete(ns.run_id)
    else:
        return 2
    return 0


def _cmd_serve(ns: argparse.Namespace, settings: Settings) -> int:
    import uvicorn

    settings = settings.model_copy(update={"host": ns.host, "port": ns.port})
    from mmc.web.app import create_app

    app = create_app(settings)
    try:
        uvicorn.run(app, host=ns.host, port=ns.port, log_config=None)
    except KeyboardInterrupt:
        return 130
    return 0
