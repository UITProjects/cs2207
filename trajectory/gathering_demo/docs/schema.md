# PUBG API response shapes used by this project

Sources: official docs (documentation.pubg.com — Matches, Telemetry Events, Telemetry Objects),
`pubg-python` / `chicken-dinner` models, community sample telemetry. **Verified on real files at M8
(2026-11-14)** with `scripts/inspect_telemetry.py`: 1 public official Erangel squad match and the PGS 12 Grand
Final / SEA PACP26 / SEA PACI26 tournament matches. A trimmed real match lives in `tests/fixtures/real/`.
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

`Character` = `{name, teamId, health, location{x,y,z}, ranking, individualRanking, accountId, type, isInBlueZone,
isInRedZone, isInVehicle, isDBNO, inSpecialZone, zone[]}`. Verified: `type` is `user` (human), `user_ai` (AI bot,
`accountId` starts with `ai.`) or `monster` (NPC guard). A public official match had **38 humans / 62 bots / 5 NPCs**;
tournament matches are humans only. The parser drops bots and NPCs (`preprocess.drop_bots`).

| `_T` | Fields used | Notes |
|---|---|---|
| `LogMatchStart` | `_D`, `mapName`, `characters[]`, `teamSize` | Verified: `characters[]` items are wrappers `{character: Character, primaryWeaponFirst, …}` (parser accepts both forms) |
| `LogPlayerPosition` | `character`, `vehicle`, `elapsedTime`, `numAlivePlayers` | Verified: every **10.00 s** per player (median 10.00, p10 9.98, p90 10.02). `vehicle` is `null` on foot or an object (`vehicleType`, `vehicleId`, `velocity`, `seatIndex`, …) in a vehicle. Tournament telemetry also has positions **up to ~2 min before `LogMatchStart`** (lobby); the parser drops t < 0 |
| `LogParachuteLanding` | `character`, `distance` | Verified: can occur **more than once per player** (153 events for 105 characters); the parser keeps the first. Missing → fallback z-stabilisation |
| `LogGameStatePeriodic` | `gameState{elapsedTime, numAliveTeams, numAlivePlayers, safetyZonePosition{x,y,z}, safetyZoneRadius, poisonGasWarningPosition, poisonGasWarningRadius, redZonePosition, redZoneRadius, blackZone*}` | Verified: `poisonGasWarning*` = the **next (white)** circle, changes in steps (8 values per match, 0 before the first circle); `safetyZone*` = the **current (blue)** circle, shrinks continuously and is always ≥ the white one. Radii in cm |
| `LogPlayerKillV2` | `victim`, `killer` (nullable for zone deaths), `finisher`, `killerDamageInfo{damageTypeCategory, damageCauserName, distance}`, `isSuicide` | |
| `LogMatchEnd` | `characters[]` (wrapper `{character: Character}`, verified) | `character.ranking` = final team placement |

### Tournaments (verified)
- `GET /tournaments` (rate limited) lists ~1 200 events with `createdAt`; `GET /tournaments/{id}` lists their matches.
- Tournament matches are fetched from the **`tournament` shard**: `/shards/tournament/matches/{id}`. Their
  `gameMode` is `esports-squad` and `matchType` is empty. Telemetry comes from the same CDN.
- Lobbies are 16 teams × 4 pros (some matches 14–16 teams), with no bots. Player names follow `TEAMTAG_Name`
  (e.g. `MiTH_Baren`), so the team name is the most common prefix (`players.parquet`, tournaments only).
- Some listed matches are aborted remakes (one lasted 16 s), so the tournament filter sets `min_duration_s: 600`.
