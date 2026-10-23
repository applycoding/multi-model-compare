from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any

from mmc.config.schemas import AppConfig, PricingTable, Rubric, rubric_sha256
from mmc.config.yaml_loader import ConfigError, read_yaml


def _load_yaml_from_dir(config_dir: Path, name: str) -> Any:
    path = config_dir / name
    if not path.is_file():
        raise ConfigError(f"missing config file: {path}")
    return read_yaml(path)


def load_app_config(
    config_dir: Path | None,
    *,
    pricing_file: str = "pricing.yaml",
    rubric_file: str = "rubric.yaml",
) -> AppConfig:
    if config_dir is None:
        defaults = importlib.resources.files("mmc.defaults")

        def read_resource(name: str) -> Any:
            path = defaults.joinpath(name)
            import yaml

            from mmc.config.yaml_loader import DupKeySafeLoader

            loader = DupKeySafeLoader
            loader.name = f"mmc.defaults/{name}"
            with path.open(encoding="utf-8") as fh:
                return yaml.load(fh, Loader=loader)

        models_data = read_resource("models.yaml")
        pricing_data = read_resource(pricing_file)
        rubric_data = read_resource(rubric_file)
    else:
        models_data = _load_yaml_from_dir(config_dir, "models.yaml")
        pricing_data = _load_yaml_from_dir(config_dir, pricing_file)
        rubric_data = _load_yaml_from_dir(config_dir, rubric_file)

    rubric = Rubric.model_validate(rubric_data)
    rubric = rubric.model_copy(update={"sha256": rubric_sha256(rubric)})
    pricing = PricingTable.model_validate(pricing_data)

    merged: dict[str, Any] = dict(models_data)
    merged["rubric"] = rubric
    merged["pricing"] = pricing
    return AppConfig.model_validate(merged)
