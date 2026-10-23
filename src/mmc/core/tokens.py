from __future__ import annotations

import logging
import math
from typing import Literal

from mmc.core.results import TokenUsage, UsageSource
from mmc.providers.base import ProviderRequest, StreamEnd

logger = logging.getLogger(__name__)


class TokenEstimator:
    def __init__(self, mode: Literal["auto", "tiktoken", "chars"]) -> None:
        self._mode = mode
        self._encoding = None
        if mode in ("auto", "tiktoken"):
            try:
                import tiktoken

                self._encoding = tiktoken.get_encoding("o200k_base")
                self._estimator_name = "tiktoken:o200k_base"
            except Exception:
                self._encoding = None
                if mode == "tiktoken":
                    self._estimator_name = "chars/4"
                else:
                    self._estimator_name = "chars/4"
                    logger.info("tiktoken unavailable; falling back to chars/4")
        else:
            self._estimator_name = "chars/4"

    def estimate(self, text: str) -> tuple[int, str]:
        if self._encoding is not None and self._mode != "chars":
            return len(self._encoding.encode(text)), self._estimator_name
        return max(1, math.ceil(len(text) / 4)) if text else 0, "chars/4"


def resolve_usage(
    end: StreamEnd | None,
    req: ProviderRequest,
    text: str,
    estimator: TokenEstimator,
) -> TokenUsage:
    usage = end.usage if end else None
    inp_src: UsageSource = "provider"
    out_src: UsageSource = "provider"
    est_name: str | None = None

    if usage is None or usage.input_tokens is None:
        inp, est_name = estimator.estimate(req.user)
        inp_src = "estimated"
    else:
        inp = usage.input_tokens

    if usage is None or usage.output_tokens is None:
        out, est_name_out = estimator.estimate(text)
        if est_name is None:
            est_name = est_name_out
        out_src = "estimated"
    else:
        out = usage.output_tokens

    raw = usage.raw if usage else {}
    return TokenUsage(
        input_tokens=inp,
        output_tokens=out,
        reasoning_tokens=usage.reasoning_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
        raw=raw,
        input_source=inp_src,
        output_source=out_src,
        estimator=est_name if inp_src == "estimated" or out_src == "estimated" else None,
    )
