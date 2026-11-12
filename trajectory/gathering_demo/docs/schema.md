# PUBG API response shapes used by this project

Sources: official docs (documentation.pubg.com — Matches, Telemetry Events, Telemetry Objects),
`pubg-python` / `chicken-dinner` models, community sample telemetry. Items marked **UNVERIFIED**
must be checked against a real file at M8 (`scripts/inspect_telemetry.py`).
Typed models: `src/datasource/schema.py` (pydantic, `extra="allow"`). The mock simulator
(`src/datasource/mock_sim.py`) emits exactly these shapes.

## Match — `GET /shards/steam/matches/{id}` (JSON:API)
```json
{"data": {"type": "match", "id": "<uuid>",
          "attributes": {"createdAt": "2026-11-01T12:00:00Z", "duration": 1750, "gameMode": "squad-fpp",
                         "mapName": "Baltic_Main", "matchType": "official", "isCustomMatch": false,
                         "seasonState": "progress", "shardId": "steam", "titleId": "bluehole-pubg"},
          "relationships": {"rosters": {"data": [{"type": "roster", "id": "..."}]},
                            "assets": {"data": [{"type": "asset", "id": "..."}]}}},
 "included": [
   {"type": "participant", "id": "...", "attributes": {"stats": {"name": "...", "playerId": "account.<hex>",
      "winPlace": 3, "kills": 2, "timeSurvived": 1500.5, "DBNOs": 1, "damageDealt": 230.1}}},
   {"type": "roster", "id": "...", "attributes": {"stats": {"rank": 3, "teamId": 7}, "won": "false"},
    "relationships": {"participants": {"data": [{"type": "participant", "id": "..."}]}}},
   {"type": "asset", "id": "...", "attributes": {"name": "telemetry", "URL": "https://telemetry-cdn.pubg.com/...json",
                                                  "createdAt": "..."}}],
 "links": {"self": "..."}}
```
- `/samples` → `data.relationships.matches.data[].id`.
- Telemetry URL is a gzipped JSON array (served with gzip content-encoding).

## Telemetry — JSON array of events, each with `_D` (ISO-8601 UTC) and `_T` (type)
Coordinates `location.{x,y,z}` in **centimeters**, origin top-left, Erangel 0–816 000.

`Character` = `{name, teamId, health, location{x,y,z}, ranking, accountId, isInBlueZone, isInRedZone, zone[]}`

| `_T` | Fields used | Notes |
|---|---|---|
| `LogMatchStart` | `_D`, `mapName`, `characters[]`, `teamSize` | `characters[]` items are **UNVERIFIED**: either `Character` or wrapper `{character: Character, ...}` — parser accepts both |
| `LogPlayerPosition` | `character`, `vehicle`, `elapsedTime`, `numAlivePlayers` | frequency ~10 s (**UNVERIFIED**, measure). `vehicle` is `null` or `{vehicleType, vehicleId, healthPercent, feulPercent}` on foot (**UNVERIFIED**: may be an object with empty `vehicleId`) |
| `LogParachuteLanding` | `character`, `distance` | one per player (**UNVERIFIED**: can be missing for disconnects → fallback z-stabilisation) |
| `LogGameStatePeriodic` | `gameState{elapsedTime, numAliveTeams, numAlivePlayers, safetyZonePosition{x,y,z}, safetyZoneRadius, poisonGasWarningPosition, poisonGasWarningRadius, redZonePosition, redZoneRadius}` | `safetyZone*` = current blue circle, `poisonGasWarning*` = next (white) circle — **UNVERIFIED** semantics; radii in cm |
| `LogPlayerKillV2` | `victim`, `killer` (nullable for zone deaths), `finisher`, `killerDamageInfo{damageTypeCategory, damageCauserName, distance}`, `isSuicide` | |
| `LogMatchEnd` | `characters[]` (wrapper `{character: Character}` **UNVERIFIED**) | `character.ranking` = final team placement |
