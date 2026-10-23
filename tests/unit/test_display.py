from __future__ import annotations

from types import SimpleNamespace

from mmc.display import answers_cost_estimated


def test_answers_cost_estimated_ignores_run_total_flag() -> None:
    estimated_answer = SimpleNamespace(cost=SimpleNamespace(status="estimated"))
    known_answer = SimpleNamespace(cost=SimpleNamespace(status="known"))
    record = SimpleNamespace(
        answers=[estimated_answer, known_answer],
        total=SimpleNamespace(estimated=True),
    )
    assert answers_cost_estimated(record) is True

    judge_only_estimated = SimpleNamespace(
        answers=[known_answer],
        total=SimpleNamespace(estimated=True),
    )
    assert answers_cost_estimated(judge_only_estimated) is False
