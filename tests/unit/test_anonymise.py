from __future__ import annotations

from mmc.judge.anonymise import assign_labels, redact_identity


def test_assign_labels_seeded() -> None:
    a = assign_labels(["m1", "m2", "m3", "m4"], 20261023)
    b = assign_labels(["m1", "m2", "m3", "m4"], 20261023)
    assert a == b
    assert set(a.keys()) == {"A", "B", "C", "D"}


def test_redact_identity_e40() -> None:
    text = "As Claude would say, GPT is fine."
    out = redact_identity(text, ["Claude", "GPT"], ["mock-claude"])
    assert "[MODEL]" in out
    assert "Claude" not in out
