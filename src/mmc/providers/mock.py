from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from mmc.config.schemas import MockBehavior
from mmc.judge.parser import parse_verdict
from mmc.judge.schema_builder import verdict_json_schema, verdict_model
from mmc.providers.base import (
    Provider,
    ProviderError,
    ProviderRequest,
    ProviderUsage,
    StreamEnd,
    StreamEvent,
    TextDelta,
)

if TYPE_CHECKING:
    from mmc.config.schemas import Rubric

_VOCAB = [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "zeta",
    "eta",
    "theta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "omicron",
    "pi",
    "rho",
    "sigma",
    "tau",
    "upsilon",
    "phi",
    "chi",
    "psi",
    "omega",
]

# Test injection points
mock_gate_barrier: asyncio.Barrier | None = None
mock_in_flight_counter: list[int] = []


def _mock_request_id(model_id: str, prompt: str) -> str:
    digest = hashlib.sha256(f"{model_id}\x00{prompt}".encode()).hexdigest()
    return f"mock-{digest[:8]}"


def _answer_text(model_id: str, prompt: str, words: int) -> str:
    if words == 0:
        return ""
    seed = hashlib.sha256(f"{model_id}\x00{prompt}".encode()).digest()
    parts: list[str] = []
    for i in range(words):
        parts.append(_VOCAB[(seed[i % len(seed)] + i) % len(_VOCAB)])
    return " ".join(parts)


class MockProvider(Provider):
    id = "mock"

    def __init__(self, rubric: Rubric | None = None) -> None:
        self._rubric = rubric

    async def stream(self, req: ProviderRequest) -> AsyncIterator[StreamEvent]:
        opts = req.spec.mock
        if opts is None:
            raise ProviderError("protocol", "mock model missing mock options")
        behavior: MockBehavior = opts.behavior
        prompt = req.user
        words = opts.output_words

        if behavior == "error":
            raise ProviderError(opts.error_kind, opts.error_message)

        if behavior == "gate":
            global mock_in_flight_counter
            mock_in_flight_counter.append(mock_in_flight_counter[-1] + 1 if mock_in_flight_counter else 1)
            if mock_gate_barrier is not None:
                await mock_gate_barrier.wait()
            mock_in_flight_counter.append(max(0, mock_in_flight_counter[-1] - 1))

        text = _answer_text(req.spec.model_id, prompt, words)
        rid = _mock_request_id(req.spec.model_id, prompt)

        if behavior in ("judge", "judge_bad_json_once", "judge_bad_json_always"):
            async for ev in self._judge_stream(req, behavior, rid):
                yield ev
            return

        if behavior == "empty":
            usage = self._usage(prompt, words, opts)
            yield StreamEnd(
                outcome="ok",
                finish_reason="stop",
                request_id=rid,
                usage=usage,
            )
            return

        if behavior == "reasoning_only":
            usage = ProviderUsage(
                input_tokens=math.ceil(len(prompt) / 4),
                output_tokens=None,
                reasoning_tokens=50,
                total_tokens=None,
                raw={"reasoning_tokens": 50},
            )
            yield StreamEnd(
                outcome="incomplete",
                finish_reason="max_tokens",
                request_id=rid,
                usage=usage,
            )
            return

        deltas_text = text
        if behavior == "usage_only_chunks":
            # Usage metadata arrives before any text; no TextDelta until after.
            async for ev in self._text_deltas(deltas_text, behavior):
                yield ev
            yield StreamEnd(
                outcome="ok",
                finish_reason="stop",
                request_id=rid,
                usage=self._usage(prompt, words, opts),
            )
            return

        if behavior == "stall":
            if text:
                yield TextDelta(text=text.split()[0] if text else "word")
            await asyncio.Event().wait()
            return

        if behavior == "error_midstream":
            async for ev in self._text_deltas(deltas_text, behavior, max_deltas=2):
                yield ev
            raise ProviderError(opts.error_kind, opts.error_message)

        if behavior == "missing_terminal":
            async for ev in self._text_deltas(deltas_text, behavior, max_deltas=2):
                yield ev
            return

        async for ev in self._text_deltas(deltas_text, behavior):
            yield ev

        outcome = "ok"
        if behavior == "refused":
            outcome = "refused"
        elif behavior == "blocked":
            outcome = "blocked"
        elif behavior == "incomplete":
            outcome = "incomplete"

        end_usage: ProviderUsage | None = None if behavior == "no_usage" else self._usage(prompt, words, opts)
        yield StreamEnd(
            outcome=outcome,
            finish_reason="stop" if outcome == "ok" else behavior,
            request_id=rid,
            usage=end_usage,
        )

    async def _text_deltas(
        self, text: str, behavior: MockBehavior, max_deltas: int | None = None
    ) -> AsyncIterator[TextDelta]:
        if not text:
            return
        words = text.split()
        chunks = 3 if max_deltas is None else min(3, max_deltas)
        if chunks <= 0:
            return
        size = max(1, len(words) // chunks)
        emitted = 0
        for i in range(0, len(words), size):
            if max_deltas is not None and emitted >= max_deltas:
                break
            part = " ".join(words[i : i + size])
            if part:
                yield TextDelta(text=part + (" " if i + size < len(words) else ""))
                emitted += 1

    def _usage(self, prompt: str, words: int, opts: object) -> ProviderUsage:
        from mmc.config.schemas import MockOptions

        assert isinstance(opts, MockOptions)
        if opts.fixed_usage:
            inp, out = opts.fixed_usage
            return ProviderUsage(
                input_tokens=inp,
                output_tokens=out,
                reasoning_tokens=None,
                total_tokens=inp + out,
                raw={"input_tokens": inp, "output_tokens": out},
            )
        inp = math.ceil(len(prompt) / 4)
        return ProviderUsage(
            input_tokens=inp,
            output_tokens=words,
            reasoning_tokens=None,
            total_tokens=inp + words,
            raw={"input_tokens": inp, "output_tokens": words},
        )

    async def _judge_stream(self, req: ProviderRequest, behavior: MockBehavior, rid: str) -> AsyncIterator[StreamEvent]:
        if behavior == "judge_bad_json_once" and req.request_tag.endswith("/judge/1"):
            yield TextDelta(text="This is not JSON at all.")
            yield StreamEnd(outcome="ok", finish_reason="stop", request_id=rid, usage=None)
            return
        if behavior == "judge_bad_json_always":
            yield TextDelta(text="prose output")
            yield StreamEnd(outcome="ok", finish_reason="stop", request_id=rid, usage=None)
            return

        payload = json.loads(req.user)
        labels = sorted(payload.get("answers", {}).keys())
        criteria = [c["key"] for c in payload.get("rubric", {}).get("criteria", [])]
        if not criteria and self._rubric:
            criteria = [c.key for c in self._rubric.criteria]
        verdict_json_schema(labels, criteria)
        verdict_model(labels, criteria, 600)
        verdicts = []
        for label in labels:
            scores = []
            answer = payload["answers"][label]
            for crit in criteria:
                h = hashlib.sha256(f"{label}\x00{crit}\x00{answer}".encode()).hexdigest()
                score = int(h[:8], 16) % 5 + 1
                scores.append({"criterion": crit, "score": score, "rationale": f"score {score}"})
            verdicts.append({"label": label, "scores": scores})
        raw = json.dumps({"verdicts": verdicts}, ensure_ascii=False, sort_keys=True)
        parse_verdict(raw, set(labels), criteria, 600)
        opts = req.spec.mock
        usage = self._usage(req.user, 0, opts) if opts else None
        yield TextDelta(text=raw)
        yield StreamEnd(outcome="ok", finish_reason="stop", request_id=rid, usage=usage)
