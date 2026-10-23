from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from mmc import __version__
from mmc.clock import Clock
from mmc.config.schemas import AppConfig, PriceEntry
from mmc.core.pricing import sum_costs
from mmc.core.request import ResolvedRun
from mmc.core.results import AnswerResult
from mmc.core.runner import run_contestants
from mmc.core.tokens import TokenEstimator
from mmc.honesty import apply_profile_honesty
from mmc.judge.judge import run_judge
from mmc.judge.schemas import JudgeOutcome
from mmc.providers.registry import ProviderRegistry
from mmc.records import RunRecord, RunStatus
from mmc.redact import Redactor, redact_record
from mmc.settings import Settings
from mmc.storage.repository import RunRepository


class CompareService:
    def __init__(
        self,
        config: AppConfig,
        settings: Settings,
        registry: ProviderRegistry,
        repo: RunRepository,
        clock: Clock,
        redactor: Redactor,
        estimator: TokenEstimator,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self._config = config
        self._settings = settings
        self._registry = registry
        self._repo = repo
        self._clock = clock
        self._redactor = redactor
        self._estimator = estimator
        self._id_factory = id_factory

    def models_with_availability(self) -> list[tuple[object, bool, str | None]]:
        out: list[tuple[object, bool, str | None]] = []
        for model in self._config.models:
            available, reason = self._registry.availability(model)
            out.append((model, available, reason))
        return out

    async def run(self, resolved: ResolvedRun) -> RunRecord:
        run_id = self._id_factory()
        created = self._clock.now()
        deadline = self._clock.perf() + self._config.limits.run_deadline_s
        on = created.date()

        active = [s for s in resolved.contestants if self._registry.availability(s)[0]]
        if not active:
            record = self._build_record(
                run_id,
                created,
                resolved,
                [],
                None,
                "no_contestants",
                [],
            )
            self._repo.save(redact_record(record, self._redactor))
            return redact_record(record, self._redactor)

        try:
            answers = await run_contestants(
                resolved.contestants,
                resolved.requests,
                self._registry,
                self._clock,
                deadline,
                self._estimator,
                on,
                self._config.pricing,
            )
            judge_out: JudgeOutcome | None = None
            if resolved.judge is not None:
                judge_out = await run_judge(
                    resolved.prompt,
                    answers,
                    resolved.judge,
                    resolved.judge_settings,
                    self._config.rubric,
                    resolved.seed,
                    run_id,
                    self._registry,
                    self._clock,
                    deadline,
                    self._estimator,
                    self._config.pricing,
                    on,
                )
            record = self._build_record(
                run_id,
                created,
                resolved,
                answers,
                judge_out,
                "completed",
                self._collect_pricing(answers, judge_out, on),
            )
            red = redact_record(record, self._redactor)
            self._repo.save(red)
            return red
        except asyncio.CancelledError:
            record = self._build_record(
                run_id,
                created,
                resolved,
                [],
                None,
                "cancelled",
                [],
            )
            with contextlib.suppress(Exception):
                self._repo.save(redact_record(record, self._redactor))
            raise

    def _collect_pricing(self, answers: list[AnswerResult], judge: JudgeOutcome | None, on: object) -> list[PriceEntry]:
        from datetime import date

        assert isinstance(on, date)
        used: list[PriceEntry] = []
        seen: set[str] = set()
        for ans in answers:
            if ans.cost and ans.cost.price:
                key = ans.cost.price.entry.model_key
                if key not in seen:
                    seen.add(key)
                    used.append(ans.cost.price.entry)
        if judge:
            for att in judge.attempts:
                if att.cost and att.cost.price:
                    key = att.cost.price.entry.model_key
                    if key not in seen:
                        seen.add(key)
                        used.append(att.cost.price.entry)
        return used

    def _build_record(
        self,
        run_id: str,
        created: datetime,
        resolved: ResolvedRun,
        answers: list[AnswerResult],
        judge: JudgeOutcome | None,
        status: RunStatus,
        pricing_entries: list[PriceEntry],
    ) -> RunRecord:
        costs = [a.cost for a in answers]
        if judge:
            costs.extend(att.cost for att in judge.attempts)
        total = sum_costs(costs)
        record = RunRecord(
            id=run_id,
            created_at=created,
            profile=self._settings.profile,
            app_version=__version__,
            prompt=resolved.prompt,
            status=status,
            seed=resolved.seed,
            vendors_contacted=resolved.vendors_contacted,
            judge_settings=resolved.judge_settings,
            rubric=self._config.rubric,
            pricing_version=self._config.pricing.version,
            pricing_entries_used=pricing_entries,
            answers=answers,
            judge=judge,
            total=total,
        )
        return apply_profile_honesty(record)
