from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    pass


class DupKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: DupKeySafeLoader, node: yaml.MappingNode) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in mapping:
            line = key_node.start_mark.line + 1
            raise ConfigError(f"{loader.name}:{line}: duplicate key '{key}'")
        mapping[key] = loader.construct_object(value_node)
    return mapping


DupKeySafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def read_yaml(path: Path) -> Any:
    loader = DupKeySafeLoader
    loader.name = str(path)
    with path.open(encoding="utf-8") as fh:
        return yaml.load(fh, Loader=loader)
