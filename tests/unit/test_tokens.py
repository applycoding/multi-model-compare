from __future__ import annotations

from mmc.config.loader import load_app_config
from mmc.core.tokens import TokenEstimator, resolve_usage
from mmc.providers.base import ProviderRequest, StreamEnd


def test_missing_usage_estimated(estimator: TokenEstimator) -> None:
    config = load_app_config(None)
    spec = config.model("mock:mock-gpt")
    req = ProviderRequest(
        spec=spec,
        system=None,
        user="12345678",
        max_output_tokens=100,
        temperature=0.2,
        timeout_s=60,
        request_tag="t",
    )
    end = StreamEnd(outcome="ok", finish_reason="stop", request_id="x", usage=None)
    usage = resolve_usage(end, req, "abcd", estimator)
    assert usage.input_source == "estimated"
    assert usage.output_source == "estimated"
    assert usage.estimator == "chars/4"


def test_chars_mode_forced(estimator: TokenEstimator) -> None:
    assert estimator._estimator_name == "chars/4"


def test_xai_billing_flag() -> None:
    config = load_app_config(None)
    assert config.providers["xai"].reasoning_tokens_additive is False
