#!/usr/bin/env python3
"""Zusammenführen der installierten TOML-Konfiguration mit WebGUI-Overrides."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

RUNTIME_CONFIG_PATH = Path(os.environ.get("POWERGATEWAY_RUNTIME_CONFIG", "/var/lib/powergateway/application_config.json"))


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_runtime(path: Path = RUNTIME_CONFIG_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def merged_config(base: dict[str, Any], path: Path = RUNTIME_CONFIG_PATH) -> dict[str, Any]:
    return deep_merge(base, load_runtime(path))
