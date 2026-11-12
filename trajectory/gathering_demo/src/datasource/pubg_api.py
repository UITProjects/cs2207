"""PubgApiDataSource: real matches via the PUBG API (needs PUBG_API_KEY; see README)."""
from __future__ import annotations

import datetime as dt

from src.api.client import PubgClient, telemetry_url


class PubgApiDataSource:
    name = "pubg"

    def __init__(self, shard: str = "steam", client: PubgClient | None = None, days: int | None = None):
        self.client = client or PubgClient(shard=shard)
        self.days = days

    def list_match_ids(self, limit: int) -> list[str]:
        after = None
        if self.days:
            t = dt.datetime.now(dt.UTC) - dt.timedelta(days=self.days)
            after = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.client.samples(after)[:limit]

    def get_match(self, match_id: str) -> dict:
        return self.client.match(match_id)

    def get_telemetry(self, match: dict) -> list[dict]:
        return self.client.telemetry(telemetry_url(match))
