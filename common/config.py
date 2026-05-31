"""Configuration loader: YAML file + environment variable overrides."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

_CONFIG: dict[str, Any] | None = None
_BASE_DIR = Path(__file__).resolve().parent.parent


def load_config(config_path: str | None = None) -> dict[str, Any]:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    if config_path is None:
        config_path = str(_BASE_DIR / "config" / "settings.yaml")

    if not Path(config_path).exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        _CONFIG = yaml.safe_load(f) or {}

    _merge_env_overrides(_CONFIG)
    return _CONFIG


def _merge_env_overrides(config: dict[str, Any], prefix: str = "") -> None:
    for key, value in config.items():
        full_key = f"{prefix}{key}".upper().replace(".", "_")
        if isinstance(value, dict):
            _merge_env_overrides(value, f"{full_key}_")
        else:
            env_val = os.environ.get(full_key)
            if env_val is not None:
                config[key] = type(value)(env_val) if value is not None else env_val


def get_config() -> dict[str, Any]:
    if _CONFIG is None:
        return load_config()
    return _CONFIG
