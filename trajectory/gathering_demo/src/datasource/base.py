"""DataSource protocol + factory. Mock and real sources return the same raw JSON shapes."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.config import datasource_name, load_config


@runtime_checkable
class DataSource(Protocol):
    name: str  # "mock" | "pubg"

    def list_match_ids(self, limit: int) -> list[str]: ...  # like /samples

    def get_match(self, match_id: str) -> dict: ...  # raw JSON:API match response

    def get_telemetry(self, match: dict) -> list[dict]: ...  # raw telemetry event list


def get_datasource(name: str | None = None) -> DataSource:
    """Pick the source: argument > env DATASOURCE > config.yaml `datasource` (default mock)."""
    name = name or datasource_name()
    cfg = load_config()
    if name == "mock":
        from src.datasource.mock import MockDataSource

        m = cfg.get("mock", {})
        return MockDataSource(seed=m.get("seed", 2207), n_players=m.get("n_players", 100),
                              squad_size=m.get("squad_size", 4), sample_dt=m.get("sample_interval_s", 10))
    if name == "pubg":
        from src.datasource.pubg_api import PubgApiDataSource

        return PubgApiDataSource(shard=cfg["api"]["shard"])
    raise ValueError(f"unknown datasource {name!r} (expected mock | pubg)")
