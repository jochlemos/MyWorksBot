"""Defaults bundled with the app (default_settings.json); merged with user config.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _bundled_defaults_path() -> Path:
    return Path(__file__).resolve().parent / "default_settings.json"


def load_bundled_defaults() -> dict[str, Any]:
    path = _bundled_defaults_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for key, val in override.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(val, dict)
        ):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out
