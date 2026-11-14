"""Real matches via the PUBG API (needs PUBG_API_KEY; see README): public samples or one tournament."""
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


class TournamentDataSource:
    """Matches of one esports tournament: /tournaments/{id} (rate limited, 1 call) + the `tournament` shard.
    Tournament lobbies are pro players only (no bots); gameMode is e.g. `esports-squad`, matchType is empty."""

    kind = "tournament"

    def __init__(self, tournament_id: str, client: PubgClient | None = None, name: str | None = None):
        self.tournament_id = tournament_id
        self.client = client or PubgClient(shard="tournament")
        self.name = name or tournament_id
        self.created: dict[str, str] = {}

    def tournament(self) -> dict:
        return self.client._request(f"{self.client.base}/tournaments/{self.tournament_id}", limited=True).json()

    def list_match_ids(self, limit: int) -> list[str]:
        doc = self.tournament()
        for inc in doc.get("included", []):
            if inc.get("type") == "match":
                self.created[inc["id"]] = inc.get("attributes", {}).get("createdAt", "")
        ids = [m["id"] for m in doc["data"]["relationships"]["matches"]["data"]]
        ids.sort(key=lambda i: self.created.get(i, ""), reverse=True)  # newest first
        return ids[:limit]

    def get_match(self, match_id: str) -> dict:
        return self.client._request(f"{self.client.base}/shards/tournament/matches/{match_id}").json()

    def get_telemetry(self, match: dict) -> list[dict]:
        return self.client.telemetry(telemetry_url(match))
