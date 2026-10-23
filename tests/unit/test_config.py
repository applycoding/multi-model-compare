from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mmc.config.loader import load_app_config
from mmc.config.yaml_loader import ConfigError, read_yaml


def test_load_defaults() -> None:
    config = load_app_config(None)
    assert config.profiles["mock"].judge == "mock:mock-judge"
    assert config.profiles["live"].judge == "google:gemini-4-argon"


def test_duplicate_key_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("a: 1\na: 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate key"):
        read_yaml(path)


def test_temp_model_in_temp_dir(tmp_path: Path) -> None:
    import shutil
    from importlib.resources import files

    defaults = files("mmc.defaults")
    for name in ("models.yaml", "pricing.yaml", "rubric.yaml"):
        shutil.copy(defaults.joinpath(name), tmp_path / name)
    models = yaml.safe_load((tmp_path / "models.yaml").read_text())
    models["models"].append(
        {
            "key": "mock:custom",
            "provider": "mock",
            "vendor": "openai",
            "model_id": "custom",
            "display_name": "Custom",
            "supports_temperature": True,
            "mock": {"behavior": "ok", "output_words": 5},
        }
    )
    (tmp_path / "models.yaml").write_text(yaml.dump(models), encoding="utf-8")
    pricing = yaml.safe_load((tmp_path / "pricing.yaml").read_text())
    pricing["entries"].append(
        {
            "model_key": "mock:custom",
            "input_per_mtok": "1.00",
            "output_per_mtok": "2.00",
            "basis": "exact",
            "effective_from": "2026-01-01",
            "source_url": "https://github.com/applycoding/multi-model-compare",
            "retrieved_on": "2026-10-23",
        }
    )
    (tmp_path / "pricing.yaml").write_text(yaml.dump(pricing), encoding="utf-8")
    config = load_app_config(tmp_path)
    assert any(m.key == "mock:custom" for m in config.models)
    entry = config.pricing.lookup("mock:custom", __import__("datetime").date(2026, 10, 23))
    assert entry is not None
