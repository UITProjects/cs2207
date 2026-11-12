"""MockDataSource: deterministic, seeded, no network. Same raw JSON shapes as the PUBG API."""
from __future__ import annotations

from src.datasource import mock_sim


class MockDataSource:
    name = "mock"

    def __init__(self, seed: int = 2207, n_players: int = 100, squad_size: int = 4, sample_dt: float = 10.0):
        self.seed, self.squad_size, self.sample_dt = seed, squad_size, sample_dt
        self.n_squads = n_players // squad_size
        self._cache: dict[str, tuple[dict, list[dict], dict]] = {}

    def _index(self, match_id: str) -> int:
        return int(match_id.rsplit("-", 1)[1])

    def list_match_ids(self, limit: int) -> list[str]:
        return [f"mock-{self.seed}-{i:04d}" for i in range(limit)]

    def _sim(self, match_id: str):
        if match_id not in self._cache:
            self._cache.clear()  # keep memory flat: crawl asks match -> telemetry -> ground truth in order
            self._cache[match_id] = mock_sim.simulate(match_id, self.seed, self._index(match_id), self.n_squads,
                                                      self.squad_size, self.sample_dt)
        return self._cache[match_id]

    def get_match(self, match_id: str) -> dict:
        meta = mock_sim.match_meta(match_id, self.seed, self._index(match_id))
        if meta["mapName"] != "Baltic_Main" or not meta["gameMode"].startswith("squad"):
            # filtered out by the crawler anyway: no need to simulate telemetry
            return mock_sim.build_match_doc(meta, [1], ["account.x"], ["x"], {}, [float("inf")], [], 0)
        return self._sim(match_id)[0]

    def get_telemetry(self, match: dict) -> list[dict]:
        return self._sim(match["data"]["id"])[1]

    def get_ground_truth(self, match_id: str) -> dict:
        return self._sim(match_id)[2]
