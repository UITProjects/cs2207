"""Can this network reach PUBG? One attempt each, no retry loop.

1. GET https://api.pubg.com/status (no key needed)
2. with a key: one /samples call → one match → HEAD-like GET of its telemetry CDN URL
   without a key: TLS connect to telemetry-cdn.pubg.com

    uv run python scripts/check_connectivity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.api.client import load_api_key, telemetry_url  # noqa: E402
from src.api.errors import BLOCKED_HINT  # noqa: E402

TIMEOUT = (10, 20)


def probe(name: str, url: str, headers: dict | None = None, stream: bool = False) -> requests.Response | None:
    try:
        r = requests.get(url, headers=headers or {}, timeout=TIMEOUT, stream=stream)
        print(f"  ✓ {name}: HTTP {r.status_code}")
        return r
    except (requests.ConnectionError, requests.Timeout) as e:
        print(f"  ✗ {name}: {type(e).__name__}")
        return None


def main() -> int:
    print("PUBG connectivity check")
    ok = probe("api.pubg.com/status", "https://api.pubg.com/status") is not None
    key = load_api_key()
    tel_ok = None
    if ok and key:
        h = {"Authorization": f"Bearer {key}", "Accept": "application/vnd.api+json"}
        r = probe("/shards/steam/samples", "https://api.pubg.com/shards/steam/samples", h)
        if r is not None and r.ok:
            mid = r.json()["data"]["relationships"]["matches"]["data"][0]["id"]
            m = probe(f"/matches/{mid}", f"https://api.pubg.com/shards/steam/matches/{mid}", h)
            if m is not None and m.ok:
                t = probe("telemetry CDN file", telemetry_url(m.json()), stream=True)
                tel_ok = t is not None and t.ok
                if t is not None:
                    t.close()
        elif r is not None and r.status_code == 401:
            print("  ! key rejected (401): check PUBG_API_KEY in .env")
    else:
        if not key:
            print("  (no PUBG_API_KEY: skipping /samples; probing the telemetry CDN host only)")
        t = probe("telemetry-cdn.pubg.com", "https://telemetry-cdn.pubg.com/", stream=True)
        tel_ok = t is not None
    if ok and tel_ok is not False:
        print("VERDICT: PUBG reachable on this network ✓")
        return 0
    print(f"VERDICT: {BLOCKED_HINT}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
