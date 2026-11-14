"""API error types (importable without requests)."""

BLOCKED_HINT = ("PUBG blocked on this network — retry through a VPN (e.g. Cloudflare WARP), "
                "or use the GitHub Actions crawler (.github/workflows/pubg-crawl.yml).")


class PubgApiError(RuntimeError):
    """Non-retryable HTTP error from the PUBG API."""


class NetworkBlockedError(PubgApiError):
    """Connection reset / refused / timeout: the network probably blocks PUBG domains."""

    def __init__(self, msg: str = ""):
        super().__init__(f"{msg} — {BLOCKED_HINT}" if msg else BLOCKED_HINT)


class MissingTelemetryError(PubgApiError):
    """The match document has no telemetry asset."""
