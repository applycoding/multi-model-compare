from __future__ import annotations

import random
import re
from collections.abc import Mapping, Sequence


def assign_labels(model_keys: Sequence[str], seed: int) -> dict[str, str]:
    keys = list(model_keys)
    rng = random.Random(seed)
    rng.shuffle(keys)
    labels = [chr(ord("A") + i) for i in range(len(keys))]
    return {label: key for label, key in zip(labels, keys, strict=True)}


def redact_identity(text: str, terms: Sequence[str], model_ids: Sequence[str]) -> str:
    result = text
    patterns: list[str] = []
    for term in terms:
        patterns.append(rf"\b{re.escape(term)}\b")
    for mid in model_ids:
        patterns.append(rf"\b{re.escape(mid)}\b")
    for pat in patterns:
        result = re.sub(pat, "[MODEL]", result, flags=re.IGNORECASE)
    return result


def labelled_answers(label_map: Mapping[str, str], answers: Mapping[str, str]) -> dict[str, str]:
    return {label: answers[key] for label, key in label_map.items()}
