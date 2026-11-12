"""Project config (config.yaml) + paths. Env vars override: DATASOURCE."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf8") as f:
        return yaml.safe_load(f)


def path(key: str) -> Path:
    return ROOT / load_config()["paths"][key]


def default_params() -> dict:
    return dict(load_config()["params"])


def datasource_name() -> str:
    return os.environ.get("DATASOURCE") or load_config().get("datasource", "mock")
