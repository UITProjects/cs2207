"""PUBG API client: auth/gzip headers, token-bucket limiter (limited endpoints only), 429 retry with
X-RateLimit-Reset, NetworkBlockedError for connection resets / timeouts, ≤ 3 retries with backoff.

The key is read from the environment first, then from ROOT/.env, and is never printed or logged.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any

import requests
from dotenv import dotenv_values

from src.api.errors import MissingTelemetryError, NetworkBlockedError, PubgApiError  # noqa: F401
from src.config import ROOT, load_config

log = logging.getLogger("pubg.client")
LIMITED = ("/samples", "/players", "/seasons", "/leaderboards", "/clans", "/tournaments")
CONNECT_TIMEOUT, READ_TIMEOUT = 10, 60
MAX_RETRIES = 3


def load_api_key() -> str | None:
    key = os.environ.get("PUBG_API_KEY")
    if not key and (ROOT / ".env").exists():
        key = dotenv_values(ROOT / ".env").get("PUBG_API_KEY")
    return key or None


class TokenBucket:
    """`rate` tokens per `per` seconds, burst = rate. `clock`/`sleep` injectable for tests."""

    def __init__(self, rate: int, per: float = 60.0, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.rate, self.per, self.clock, self.sleep = rate, per, clock, sleep
        self.tokens, self.last = float(rate), clock()

    def acquire(self) -> None:
        while True:
            now = self.clock()
            self.tokens = min(self.rate, self.tokens + (now - self.last) * self.rate / self.per)
            self.last = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
            self.sleep((1 - self.tokens) * self.per / self.rate)


class PubgClient:
    def __init__(self, api_key: str | None = None, shard: str | None = None, base_url: str | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], float] = time.time):
        cfg = load_config()["api"]
        self.shard = shard or cfg["shard"]
        self.base = (base_url or cfg["base_url"]).rstrip("/")
        self._key = api_key if api_key is not None else load_api_key()
        self.sleep, self.now = sleep, now
        self.bucket = TokenBucket(int(cfg.get("limited_rpm", 10)), 60.0, clock, sleep)
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.api+json", "Accept-Encoding": "gzip"})

    def __repr__(self) -> str:  # never leak the key
        return f"PubgClient(shard={self.shard!r}, key={'set' if self._key else 'missing'})"

    @property
    def has_key(self) -> bool:
        return bool(self._key)

    # ---------------- low level ----------------
    def _request(self, url: str, *, auth: bool = True, params: dict | None = None, limited: bool = False,
                 read_timeout: float = READ_TIMEOUT) -> requests.Response:
        headers = {}
        if auth:
            if not self._key:
                raise PubgApiError("PUBG_API_KEY is not set (env or .env)")
            headers["Authorization"] = f"Bearer {self._key}"
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            if limited:
                self.bucket.acquire()
            try:
                r = self.session.get(url, headers=headers, params=params, timeout=(CONNECT_TIMEOUT, read_timeout))
            except (requests.ConnectionError, requests.Timeout, ConnectionResetError) as e:
                last_exc = e
                log.warning("network error on %s (attempt %d/%d): %s", _safe(url), attempt + 1, MAX_RETRIES + 1,
                            type(e).__name__)
                if attempt < MAX_RETRIES:
                    self.sleep(2 ** attempt)
                    continue
                raise NetworkBlockedError(f"{type(e).__name__} on {_safe(url)}") from e
            if r.status_code == 429:
                reset = r.headers.get("X-RateLimit-Reset")
                wait = max(1.0, float(reset) - self.now()) if reset else 2.0 ** (attempt + 2)
                wait = min(wait, 120.0)
                log.warning("429 rate limited, waiting %.0fs (attempt %d)", wait, attempt + 1)
                if attempt < MAX_RETRIES:
                    self.sleep(wait)
                    continue
                raise PubgApiError("still rate limited after retries (429)")
            if r.status_code >= 500 and attempt < MAX_RETRIES:
                self.sleep(2 ** attempt)
                continue
            if r.status_code == 401:
                raise PubgApiError("401 unauthorized: check PUBG_API_KEY")
            if r.status_code == 404:
                raise PubgApiError(f"404 not found: {_safe(url)}")
            if r.status_code >= 400:
                raise PubgApiError(f"HTTP {r.status_code} on {_safe(url)}")
            return r
        raise NetworkBlockedError(str(last_exc))  # pragma: no cover

    def _shard_url(self, path: str) -> str:
        return f"{self.base}/shards/{self.shard}{path}"

    # ---------------- endpoints ----------------
    def status(self) -> dict:
        return self._request(f"{self.base}/status", auth=False).json()

    def samples(self, created_after: str | None = None) -> list[str]:
        params = {"filter[createdAt-start]": created_after} if created_after else None
        r = self._request(self._shard_url("/samples"), params=params, limited=True)
        data = r.json()["data"]
        return [m["id"] for m in data["relationships"]["matches"]["data"]]

    def match(self, match_id: str) -> dict:
        return self._request(self._shard_url(f"/matches/{match_id}")).json()

    def telemetry(self, url: str) -> list[dict[str, Any]]:
        """Telemetry CDN files need no key. Body may be gzip-encoded transparently or a raw .gz file."""
        r = self._request(url, auth=False)
        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return json.loads(raw)


def telemetry_url(match: dict) -> str:
    for inc in match.get("included", []):
        if inc.get("type") == "asset" and inc.get("attributes", {}).get("name", "").lower() == "telemetry":
            url = inc["attributes"].get("URL")
            if url:
                return url
    raise MissingTelemetryError(f"match {match.get('data', {}).get('id')} has no telemetry asset")


def _safe(url: str) -> str:
    return url.split("?")[0]
