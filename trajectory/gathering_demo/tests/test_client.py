"""PUBG API client with mocked HTTP (responses) — passes with no key and no network."""
from __future__ import annotations

import gzip
import json

import pytest
import requests
import responses

from src.api.client import PubgClient, TokenBucket, telemetry_url
from src.api.errors import MissingTelemetryError, NetworkBlockedError, PubgApiError
from src.datasource.pubg_api import PubgApiDataSource

BASE = "https://api.pubg.com"
KEY = "test-key-should-never-leak"
MATCH = {"data": {"type": "match", "id": "m1", "attributes": {"mapName": "Baltic_Main", "gameMode": "squad-fpp",
                                                              "matchType": "official", "createdAt": "2026-11-01T00:00:00Z"}},
         "included": [{"type": "asset", "id": "a1", "attributes": {"name": "telemetry",
                                                                    "URL": "https://telemetry-cdn.pubg.com/x/m1-telemetry.json"}}]}
SAMPLES = {"data": {"type": "sample", "id": "s", "relationships": {"matches": {"data": [
    {"type": "match", "id": "m1"}, {"type": "match", "id": "m2"}]}}}}
TEL = [{"_D": "2026-11-01T00:00:00.000Z", "_T": "LogMatchStart", "mapName": "Baltic_Main", "characters": []}]


class Clock:
    def __init__(self):
        self.t, self.slept = 1000.0, []

    def sleep(self, s):
        self.slept.append(s)
        self.t += s

    def mono(self):
        return self.t


def client(clock=None):
    c = clock or Clock()
    return PubgClient(api_key=KEY, shard="steam", sleep=c.sleep, clock=c.mono, now=lambda: c.t), c


@responses.activate
def test_success_flow_samples_match_telemetry_gz():
    responses.get(f"{BASE}/shards/steam/samples", json=SAMPLES)
    responses.get(f"{BASE}/shards/steam/matches/m1", json=MATCH)
    responses.get("https://telemetry-cdn.pubg.com/x/m1-telemetry.json", body=gzip.compress(json.dumps(TEL).encode()))
    ds = PubgApiDataSource(client=client()[0])
    assert ds.list_match_ids(5) == ["m1", "m2"]
    m = ds.get_match("m1")
    assert ds.get_telemetry(m) == TEL
    calls = responses.calls
    assert calls[0].request.headers["Authorization"] == f"Bearer {KEY}"
    assert calls[0].request.headers["Accept"] == "application/vnd.api+json"
    assert "gzip" in calls[0].request.headers["Accept-Encoding"]
    assert "Authorization" not in calls[2].request.headers  # CDN gets no key


@responses.activate
def test_429_waits_for_reset_header_then_succeeds():
    c = Clock()
    responses.get(f"{BASE}/shards/steam/samples", status=429, headers={"X-RateLimit-Reset": str(int(c.t + 7))})
    responses.get(f"{BASE}/shards/steam/samples", json=SAMPLES)
    cl, _ = client(c)
    assert cl.samples() == ["m1", "m2"]
    assert any(6 <= s <= 8 for s in c.slept)


@responses.activate
def test_connection_reset_raises_network_blocked_after_3_retries():
    responses.get(f"{BASE}/shards/steam/matches/m1", body=requests.ConnectionError("Connection reset by peer"))
    cl, c = client()
    with pytest.raises(NetworkBlockedError) as e:
        cl.match("m1")
    assert "WARP" in str(e.value) and KEY not in str(e.value)
    assert len(responses.calls) == 4 and c.slept == [1, 2, 4]


@responses.activate
def test_timeout_is_network_blocked():
    responses.get(f"{BASE}/status", body=requests.Timeout("read timed out"))
    with pytest.raises(NetworkBlockedError):
        client()[0].status()


def test_missing_telemetry_asset():
    m = {"data": {"id": "m9"}, "included": [{"type": "roster", "id": "r"}]}
    with pytest.raises(MissingTelemetryError):
        telemetry_url(m)
    assert telemetry_url(MATCH).endswith("m1-telemetry.json")


@responses.activate
def test_401_and_no_key():
    responses.get(f"{BASE}/shards/steam/matches/m1", status=401)
    with pytest.raises(PubgApiError, match="401"):
        client()[0].match("m1")
    with pytest.raises(PubgApiError, match="not set"):
        PubgClient(api_key="").match("m1")


def test_key_never_in_repr():
    cl, _ = client()
    assert KEY not in repr(cl) and "set" in repr(cl)


def test_token_bucket_limits_to_rate_per_minute():
    c = Clock()
    b = TokenBucket(10, 60.0, clock=c.mono, sleep=c.sleep)
    for _ in range(25):
        b.acquire()
    assert c.t - 1000.0 == pytest.approx(90.0, abs=0.5)  # 10 free, then 6 s per request


@responses.activate
def test_only_limited_endpoints_are_throttled():
    responses.get(f"{BASE}/shards/steam/matches/m1", json=MATCH)
    cl, c = client()
    for _ in range(30):
        cl.match("m1")
    assert c.slept == []
