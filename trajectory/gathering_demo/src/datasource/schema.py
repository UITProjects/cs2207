"""Typed models of the PUBG match JSON:API response and the telemetry events we use.

Both the mock simulator and the parser rely on these shapes (see docs/schema.md).
`extra="allow"` everywhere so real fields we do not model never break parsing.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _M(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Location(_M):
    x: float
    y: float
    z: float = 0.0


class Character(_M):
    name: str = ""
    teamId: int
    health: float = 100.0
    location: Location
    ranking: int = 0
    accountId: str
    isInBlueZone: bool = False
    isInRedZone: bool = False
    zone: list[str] = Field(default_factory=list)


class Vehicle(_M):
    vehicleType: str = ""
    vehicleId: str = ""
    healthPercent: float = 0.0
    feulPercent: float = 0.0


class GameState(_M):
    elapsedTime: float
    numAliveTeams: int = 0
    numAlivePlayers: int = 0
    safetyZonePosition: Location
    safetyZoneRadius: float
    poisonGasWarningPosition: Location
    poisonGasWarningRadius: float
    redZonePosition: Location | None = None
    redZoneRadius: float = 0.0


class Event(_M):
    D: str = Field(alias="_D")
    T: str = Field(alias="_T")


class LogMatchStart(Event):
    mapName: str = ""
    characters: list[dict[str, Any]] = Field(default_factory=list)
    teamSize: int = 4


class LogPlayerPosition(Event):
    character: Character
    vehicle: Vehicle | None = None
    elapsedTime: float = 0.0
    numAlivePlayers: int = 0


class LogParachuteLanding(Event):
    character: Character
    distance: float = 0.0


class LogGameStatePeriodic(Event):
    gameState: GameState


class LogPlayerKillV2(Event):
    victim: Character
    killer: Character | None = None
    finisher: Character | None = None
    isSuicide: bool = False


class LogMatchEnd(Event):
    characters: list[dict[str, Any]] = Field(default_factory=list)


EVENT_MODELS: dict[str, type[Event]] = {
    "LogMatchStart": LogMatchStart,
    "LogPlayerPosition": LogPlayerPosition,
    "LogParachuteLanding": LogParachuteLanding,
    "LogGameStatePeriodic": LogGameStatePeriodic,
    "LogPlayerKillV2": LogPlayerKillV2,
    "LogMatchEnd": LogMatchEnd,
}


def unwrap_character(item: dict[str, Any]) -> dict[str, Any]:
    """LogMatchStart/LogMatchEnd `characters[]` items may be a Character or {character: Character}."""
    return item["character"] if isinstance(item, dict) and "character" in item else item


class MatchAttributes(_M):
    createdAt: str
    duration: int = 0
    gameMode: str
    mapName: str
    matchType: str = ""
    shardId: str = "steam"


class MatchData(_M):
    type: str = "match"
    id: str
    attributes: MatchAttributes


class MatchResponse(_M):
    data: MatchData
    included: list[dict[str, Any]] = Field(default_factory=list)

    def telemetry_url(self) -> str | None:
        for inc in self.included:
            if inc.get("type") == "asset" and inc.get("attributes", {}).get("name") == "telemetry":
                return inc["attributes"].get("URL")
        return None
