# CLAUDE.md — PUBG Gathering Pattern Demo (Trajectory Data Mining)

> This file instructs Claude Code to build the project **end-to-end**: crawl real data from the PUBG API → parse telemetry → mine **Crowd / Gathering patterns** (Zheng et al., ICDE 2013) → a lively **Streamlit** web demo with a clear application story (player training / decision-making).
>
> Read the whole file before coding. Follow the **milestones** in section 9; after each milestone, stop and give a short report plus how to test it.

---

## 0. Context & goals

- The old demo (reference: `https://cs2207.datrollout.dev/trajectory/gathering/`) has a **good workflow** (pick data → tune parameters → inspect each algorithm step → results) but **fake data and a vague application**.
- The new demo keeps that workflow, but:
  1. **Real data**: player trajectories from PUBG (100 players per match) via the PUBG Developer API.
  2. **Clear application**: answer coach/player questions — *"Which chokepoints tend to become gatherings in which phase? How much does being inside a gathering raise elimination risk? When and which route should a squad rotate?"*
- If screenshots of the old demo exist, they are in `docs/reference/` — look at them and follow their layout and interaction flow.

**Overall Definition of Done:** the full demo works end-to-end on **mock data** first (milestones M0–M6), then the real PUBG source is ready and switched on once the user provides the key (M7–M8). `streamlit run app/Home.py` runs **offline** on a committed sample dataset (no API key needed at demo time), shows trajectory animation on the real Erangel map, supports real-time parameter tuning, and includes a multi-match insights page plus a "Coach View" page.

---

## 1. Working rules

- Python **3.11**, managed with `uv` (fallback: `pip` + `venv`). Format with `ruff`, test with `pytest`.
- **Build order: mock first, real API last.** Everything (parsing, mining, app) is built and finished end-to-end on **mocked data**. The real PUBG API source is built last and left ready, waiting for the user's key (see section 1d and milestones). Do not ask for the API key until milestone M8.
- **Secrets**: the user will provide `PUBG_API_KEY` (at M8). Write it to `.env` (loaded with `python-dotenv`). `.env` must be in `.gitignore`. **Never** print the key in logs, hard-code it, or commit it. Create `.env.example`.
- The Streamlit app **never calls the API at runtime** — it only reads processed data (`data/processed/`). Crawling is a separate script.
- **Don't trust the docs 100%**: the parser is first built against the documented schema (via mock data). At M8, download one real telemetry file, print the event types (`_T`) and the actual schema of `LogPlayerPosition`, `LogGameStatePeriodic`, `LogPlayerKillV2`, `LogParachuteLanding`, `LogMatchEnd`, and fix any mismatch. Save a small real sample into `tests/fixtures/real/`.
- Prefer simple code with type hints and short docstrings. Every algorithm module must have unit tests on **synthetic data** with known expected results.
- Never show real player names in the UI: hash `accountId` → `P001…`, teams → `T01…`. (Exception: tournament matches may show team names.)

---

## 1b. Network constraint (IMPORTANT — user is in Vietnam)

- The user's ISP **resets connections to PUBG domains** (`ERR_CONNECTION_RESET` on `developer.pubg.com`). It works only through **Cloudflare WARP** (1.1.1.1 app). Assume `api.pubg.com` and `telemetry-cdn.pubg.com` may be blocked the same way.
- Before any API work, run `scripts/check_connectivity.py`: it requests `https://api.pubg.com/status`, then one telemetry CDN URL (from a sampled match), and prints a clear verdict. On connection reset/timeout, print: *"PUBG blocked on this network — turn on Cloudflare WARP and retry, or use the GitHub Actions crawler (section 1c)."* Do **not** keep retrying in a loop.
- `src/api/client.py` must treat `ConnectionResetError` / `requests.ConnectionError` / timeouts as a distinct error type (`NetworkBlockedError`) with the same hint, separate from HTTP 429 handling. Use sensible timeouts (connect 10 s, read 60 s for telemetry) and at most 3 retries with backoff.
- Never suggest disabling TLS verification as a workaround.
- Only the **crawl** step needs network access. Parsing, mining and the Streamlit app work fully offline.

## 1c. Cloud crawler (GitHub Actions — recommended backup)

Provide `.github/workflows/crawl.yml` so crawling does not depend on the user's ISP/WARP and keeps collecting before the 14-day expiry:
- Triggers: `schedule` (daily, e.g. `cron: "17 20 * * *"` UTC ≈ 03:17 Vietnam time) + `workflow_dispatch` (manual run).
- Steps: checkout → set up Python 3.11 → install deps → `python -m src.ingest.crawl --days 1 --max-matches 150` → **parse + preprocess** in the same job (raw telemetry is large) → upload `data/processed/` as an **artifact** (retention 90 days) or commit compact Parquet files to a `data` branch. Never commit raw telemetry to `main`.
- `PUBG_API_KEY` comes from **repository secret** `PUBG_API_KEY` (`${{ secrets.PUBG_API_KEY }}`); the code reads env vars first, `.env` second.
- Add `scripts/pull_cloud_data.py` (uses `gh run download`) to fetch the latest artifacts into `data/processed/` locally.
- Document in README: how to add the secret, enable the workflow, trigger a manual run, and download results.

---

## 1d. Data source abstraction (mock vs real)

Everything downstream of the data source must be **identical** for mock and real data. The mock produces the **same raw JSON shapes** as the PUBG API, so the parser never knows which source it came from.

**Interface** (`src/datasource/base.py`):
```python
class DataSource(Protocol):
    name: str                                    # "mock" | "pubg"
    def list_match_ids(self, limit: int) -> list[str]: ...          # like /samples
    def get_match(self, match_id: str) -> dict: ...                 # raw JSON:API match response
    def get_telemetry(self, match: dict) -> list[dict]: ...         # raw telemetry event list
```
- `MockDataSource` (`src/datasource/mock.py`): deterministic, seeded, no network.
- `PubgApiDataSource` (`src/datasource/pubg_api.py`): wraps `src/api/client.py` (rate limiter, 429 retry, `NetworkBlockedError`).
- Factory `get_datasource()` picks the source from env `DATASOURCE` or `config.yaml` (`datasource: mock | pubg`). Default: `mock`.
- Raw and processed data are stored per source: `data/raw/{source}/{match_id}/`, `data/processed/{source}/{match_id}/` — never mix them.
- The app shows a clear badge **"MOCK DATA"** or **"REAL PUBG DATA"** in the sidebar and on every chart caption.

**Step 1 — explore the real response shape before faking it** (no key needed):
- Sources: official docs (Telemetry Events / Telemetry Objects / Matches pages), open-source wrapper models (`chicken-dinner`, `pubg-python`) and any public sample telemetry files they ship or link to.
- Write `docs/schema.md`: the match JSON:API structure (`data.attributes`, `included[]` with rosters/participants/asset), and every telemetry event used (`LogMatchStart`, `LogPlayerPosition`, `LogParachuteLanding`, `LogGameStatePeriodic`, `LogPlayerKillV2`, `LogMatchEnd`) with field names, types, units, and an example. Mark anything uncertain as `UNVERIFIED` — it gets checked at M8.
- Encode the schema as typed models (`pydantic` or `TypedDict`) in `src/datasource/schema.py`; both the mock generator and the parser import them.

**Step 2 — the mock generator** (`src/datasource/mock_sim.py`) must be *plausible*, not random noise, so the demo is meaningful:
- 100 players = 25 squads of 4, Erangel coordinates in **cm** (0–816,000), events with `_D` ISO timestamps and `_T` types.
- Plane: random straight line across the map; squads jump along it, with landings biased toward hot drops from `assets/erangel_places.yaml` (Pochinki, School, Military Base…).
- Zones: ~8 phases shrinking (`safetyZone…`, `poisonGasWarning…` radii/positions, emitted in `LogGameStatePeriodic`), next zone placed randomly inside the current one.
- Movement: squads loot locally, then rotate toward the next zone; paths pass through **chokepoints** (bridges to the Military Base island, etc.) when geometry requires it; vehicles occasionally (faster speed, `vehicle` set).
- Fights/eliminations: when squads come within range, probabilistic kills (`LogPlayerKillV2`); higher kill probability inside dense areas so "gathering ↔ elimination risk" produces a visible but noisy signal.
- Position sampling every ~10 s with small jitter and occasional missing samples (to exercise the resampler).
- `LogMatchEnd` with final rankings.
- **Ground truth**: also write `ground_truth.json` per mock match listing the intentionally created gatherings (time span, area, members) — used to validate the mining (section 8). Ground truth is never read by the app's mining code.
- Config knobs: seed, number of matches, number of players, sampling interval. Generating 50 matches should take < 1 minute.

---

## 2. PUBG API facts (verified — treat as ground truth)

- Base: `https://api.pubg.com/shards/{shard}/...` — use shard `steam`. Headers: `Authorization: Bearer <key>`, `Accept: application/vnd.api+json`, `Accept-Encoding: gzip`.
- **Rate limit**: 10 requests/minute on limited endpoints (players, samples, seasons…). The `/matches/{id}` endpoint and telemetry files are **not** rate limited. → The client needs a rate limiter + retry on HTTP 429 (read the `X-RateLimit-Reset` header).
- **Data is retained for only 14 days** → crawling must run periodically (daily) and keep the raw files.
- Getting match IDs without playing the game:
  - `GET /shards/steam/samples` → a random list of match IDs each day (**primary source**).
  - (optional) `GET /shards/steam/players?filter[playerNames]=...` → up to 32 recent matches per player.
  - (optional) leaderboards / the `tournament` shard for pro matches.
- `GET /shards/steam/matches/{id}` → `data.attributes`: `mapName`, `gameMode`, `matchType`, `duration`, `createdAt`; `included[]` contains a `telemetry` asset with the URL of the (gzipped) JSON file.
- **Default filters**: `mapName == "Baltic_Main"` (current Erangel), `gameMode in {"squad","squad-fpp"}`, `matchType in {"competitive","official"}` (competitive = ranked). Put these in `config.yaml` so they can be changed.
- Telemetry:
  - Coordinates `location.{x,y,z}` are in **centimeters**, origin (0,0) at the **top-left**; Erangel/Miramar range 0–816,000. Convert to meters: divide by 100.
  - `Character`: `name, teamId, health, location, ranking, accountId, isInBlueZone, isInRedZone, zone`.
  - `GameState`: `elapsedTime, numAliveTeams, numAlivePlayers, safetyZonePosition, safetyZoneRadius, poisonGasWarningPosition, poisonGasWarningRadius, redZonePosition, redZoneRadius`.
  - Each event has `_D` (ISO timestamp) and `_T` (type). Use `_D` minus the `LogMatchStart` time as the canonical time `t` (seconds).
  - The docs don't state the `LogPlayerPosition` frequency (community says ~10 s) → **measure it** on real files and print the Δt distribution.
- Official map images: the GitHub repo `pubg/api-assets` (folder `Assets/Maps/`), or `python -m chicken_dinner.assets.maps`. Pick the remastered Erangel image (matching `Baltic_Main`) and save it as `assets/maps/erangel.png`. The image is square → map `[0, 816000]` onto the full image, **no axis flip needed** (y points down).

---

## 3. Algorithm definitions (per the Gathering paper — ICDE 2013)

Notation: data resampled to discrete timestamps `t_1, t_2, …` (default Δt = 10 s).

1. **Snapshot cluster**: at each timestamp `t`, run **DBSCAN** (`eps`, `min_pts`) on positions of players who are **alive and have landed**. Result: cluster set `C_t`.
2. A **Crowd** `Cr = ⟨c_a, c_{a+1}, …, c_b⟩` is a sequence of clusters at **consecutive** timestamps such that:
   - (i) every cluster has `|c| ≥ m_c`;
   - (ii) the **Hausdorff** distance between consecutive clusters `d_H(c_i, c_{i+1}) ≤ δ`;
   - (iii) lifetime `b − a + 1 ≥ k_c`.
   - Symmetric Hausdorff: `max(directed_hausdorff(A,B), directed_hausdorff(B,A))` (use `scipy.spatial.distance.directed_hausdorff`).
   - Output only **closed crowds** (cannot be extended at either end).
3. A **Participator** of crowd `Cr`: an object appearing in **≥ k_p** clusters of `Cr` (not necessarily consecutive).
4. A **Gathering**: a crowd in which **every** cluster contains **≥ m_p** participators.
   - If a crowd fails: split at the violating clusters → consecutive sub-crowds → **recompute participators on each sub-crowd** → repeat until stable; keep sub-crowds with length ≥ k_c. Output **closed gatherings**.

**Crowd discovery algorithm (implement the clear version first, optimize later):**
- Sweep `t` in increasing order, keeping a list of open candidate crowds.
- For each candidate, find clusters at `t` with `d_H ≤ δ` to its last cluster → extend (branching allowed: one candidate may extend into several clusters).
- Clusters at `t` that extend no candidate → start new candidates.
- Candidates not extended at `t` → close; if lifetime ≥ k_c, output.
- Remove duplicate crowds fully contained in another crowd.
- Optional optimization: prefilter with cluster-centroid / bounding-box distance before computing Hausdorff (document it in the docstring as lower-bound pruning).

**Default parameters (meters, Δt = 10 s) — all are sliders in the UI:**

| Parameter | Default | Range | Notes |
|---|---|---|---|
| `eps` (DBSCAN) | 150 m | 50–400 | |
| `min_pts` | 3 | 2–8 | |
| `m_c` (min cluster size) | 8 | 4–30 | ≥ 2 squads, so a single squad moving together is not counted as a gathering |
| `δ` (Hausdorff) | 300 m | 100–800 | |
| `k_c` (crowd lifetime) | 6 steps (60 s) | 3–30 | |
| `k_p` (participator) | 4 steps | 2–k_c | |
| `m_p` (participators per cluster) | 6 | 3–m_c | |

---

## 4. Preprocessing & phase labeling

- Parse `LogPlayerPosition` → table `positions(match_id, player, team, t, x_m, y_m, z_m, health, in_vehicle, num_alive)`.
- **Drop the plane / parachute stage**: keep only points after that player's `LogParachuteLanding` (fallback: after `z` stabilizes).
- **Drop after death**: cut at the `LogPlayerKillV2` event where the player is the victim (or at their last position).
- **Resample** each player to a Δt = 10 s grid: linear interpolation only for gaps ≤ 30 s; leave longer gaps empty (never fabricate points).
- Filter outlier jumps (speed > 60 m/s when not in a vehicle).
- **Phase**: from `LogGameStatePeriodic`, each time `poisonGasWarningRadius` (the next zone) changes → phase += 1. Phase 0 = before the first zone appears. Attach `phase` to every timestamp `t`.
- Table `zones(match_id, t, phase, safe_x, safe_y, safe_r, warn_x, warn_y, warn_r)` (meters).
- Table `kills(match_id, t, killer, victim, killer_team, victim_team, x, y)` and `results(match_id, team, ranking)` from `LogMatchEnd`.
- Store everything as **Parquet** in `data/processed/{match_id}/`.

---

## 5. Analytics layer (insights & application value)

This is what turns "running an algorithm" into "making decisions". Implement in `src/analytics/`.

1. **Place gazetteer**: `assets/erangel_places.yaml` with name + approximate coordinates (m) + radius for key places (Pochinki, School, Military Base, the bridges to the Military Base island, Georgopol, Yasnaya Polyana, Rozhok, Mylta Power…). Note in the file: *coordinates are estimates; calibrate by overlaying on the map image* — write a small notebook/script for visual calibration. Each gathering is assigned the nearest place.
2. **Multi-match hotspots**: normalize onto a grid (e.g. 200 m) → count gatherings per `(cell, phase)`; output top chokepoints per phase.
3. **Gathering ↔ outcomes**:
   - Rate of teams eliminated within ≤ 120 s after being participators of a gathering vs. teams not in any gathering in the same phase (baseline).
   - Distribution of final team `ranking` by number of gathering participations per phase.
   - Kills/deaths inside the gathering area (convex hull) vs. outside.
   - Always show **sample size (n)** and a *correlation ≠ causation* caveat.
4. **Zone control**: attribute for each gathering: distance from the gathering centroid to the zone edge/center (`edge` / `center` / `outside`) → to separate gatherings "forced by the zone" from "chosen" ones (chokepoints). Late game (phase ≥ 6) is labeled *forced*.
5. **Team report (VOD flagging)**: for one match + one team: timeline of the moments the team was inside a gathering, which members were participators, and the outcome (survived / eliminated where) → a list of timestamps for the coach to jump to in the VOD.

---

## 6. Streamlit web app (multipage)

Page structure (`app/Home.py` + `app/pages/`). Shared sidebar: match picker, algorithm parameters (section 3), a *Reset to defaults* button. Use `st.cache_data` for loading/computing; recomputation after a parameter change should take < ~3 s for one match.

1. **🏠 Home — Problem & how it works**: the pain point (coaches need to know dangerous chokepoints & timing), definitions Cluster → Crowd → Participator → Gathering with small illustrations, pipeline diagram, data source (PUBG API, number of matches, crawl date range).
2. **📦 Data Explorer**: table of matches (map, mode, type, date, player count), actual Δt statistics, number of points after processing. Draw all trajectories of one match on the map (one color per team, semi-transparent).
3. **🔬 Step-by-step (main page, mirrors the old demo's workflow)** — 4 tabs in algorithm order:
   - *Tab 1 Raw trajectories*: time animation (slider + Play), current zone & next zone drawn as circles.
   - *Tab 2 Snapshot clusters*: pick a timestamp `t` → points colored by DBSCAN cluster, noise in gray, convex hull per cluster, size labels.
   - *Tab 3 Crowds*: list of crowds (start–end, lifetime, mean size, place); select one → draw the sequence of hulls over time (increasing opacity) and the centroid path; chart of Hausdorff distances between steps vs. the δ threshold.
   - *Tab 4 Gatherings*: which crowds became gatherings, participators highlighted (thick outline), participators per cluster vs. `m_p` (bar chart); animation of a gathering forming → dissolving.
   - Each tab has 1–2 sentences explaining "what you're looking at", in Vietnamese.
4. **🗺️ Multi-match Insights**: gathering heatmap by phase (phase selector), top 10 chokepoints (place, phase, frequency, % of matches), chart of elimination rate inside gatherings vs. baseline per phase.
5. **🎯 Coach View (the application)**:
   - *Route risk*: pick phase + place → probability of a gathering, typical formation time (seconds after the zone appears), elimination risk. Conclusion as a sentence: *"In phase 3, the east bridge has a gathering in 42% of matches, typically forming 70–90 s after the zone appears; squads crossing in this window are eliminated X% earlier (n=…)."*
   - *Team report*: section 5.5, with a button to export the timestamps as CSV.
6. **⚙️ Sensitivity**: sweep one parameter (e.g. `δ` or `m_c`) → how the number of crowds / gatherings / mean participators changes (line chart). Explain how parameters were chosen.

**Map rendering** (`src/viz/map_plot.py`), using **Plotly**:
- Map image as `layout.images` with `x=0, y=0, sizex=816000/100, sizey=816000/100` (meters), `xref/yref` bound to the axes, `yaxis autorange="reversed"`, `scaleanchor` to keep it square; `layer="below"`.
- Animation via `frames` over `t`; only draw timestamps with living players; cap at ~300 frames (skip steps if longer).
- Zones: draw circles via `shapes` per frame. Hulls: `scipy.spatial.ConvexHull` → `go.Scatter(fill="toself")`.
- A button to zoom into the selected gathering's area.

---

## 7. Directory structure

```
pubg-gathering/
├── CLAUDE.md
├── README.md                  # install, crawl, run app, deploy
├── pyproject.toml
├── .env.example               # PUBG_API_KEY=
├── config.yaml                # shard, map/mode/type filters, Δt, default params, paths
├── assets/
│   ├── maps/erangel.png
│   └── erangel_places.yaml
├── data/
│   ├── raw/{source}/{match_id}/match.json, telemetry.json.gz, ground_truth.json (mock only)  # gitignored
│   ├── processed/{source}/{match_id}/*.parquet         # gitignored, except sample
│   └── sample/{mock,real}/    # 20–50 processed matches each, COMMITTED for offline demo
├── src/
│   ├── datasource/
│   │   ├── base.py            # DataSource protocol + get_datasource() factory
│   │   ├── schema.py          # typed models of match JSON + telemetry events
│   │   ├── mock.py            # MockDataSource
│   │   ├── mock_sim.py        # plausible match simulator + ground truth
│   │   └── pubg_api.py        # PubgApiDataSource
│   ├── api/client.py          # rate limiter, 429 retry, NetworkBlockedError
│   ├── ingest/crawl.py        # CLI: pull from any DataSource, filter, save raw, idempotent
│   ├── parse/telemetry.py     # raw → positions/zones/kills/results tables
│   ├── preprocess/clean.py    # landing cut, death cut, resample, phase
│   ├── mining/
│   │   ├── snapshot.py        # DBSCAN per timestamp
│   │   ├── hausdorff.py
│   │   ├── crowd.py
│   │   └── gathering.py
│   ├── analytics/             # gazetteer, hotspots, outcomes, team_report
│   └── viz/map_plot.py
├── app/
│   ├── Home.py
│   └── pages/1_Data_Explorer.py, 2_Step_by_step.py, 3_Insights.py, 4_Coach_View.py, 5_Sensitivity.py
├── .github/workflows/crawl.yml # daily cloud crawl (section 1c)
├── scripts/
│   ├── check_connectivity.py  # is PUBG reachable on this network? (section 1b)
│   ├── pull_cloud_data.py     # download processed data from GitHub Actions artifacts
│   ├── inspect_telemetry.py   # print the real schema of one file
│   ├── build_sample.py        # pick good matches → data/sample
│   └── calibrate_places.py
└── tests/
    ├── fixtures/
    ├── test_hausdorff.py, test_crowd.py, test_gathering.py   # synthetic, known answers
    └── test_parse.py
```

Libraries: `requests, python-dotenv, pyyaml, pydantic, pandas, pyarrow, numpy, scipy, scikit-learn, shapely, plotly, streamlit, tqdm, pytest, responses, ruff`. (Optional: `chicken-dinner`, only for downloading maps / cross-checking.)

Desired CLI (same commands for both sources; switch with `DATASOURCE=mock|pubg`):
```
DATASOURCE=mock python -m src.ingest.crawl --max-matches 50
DATASOURCE=pubg python -m src.ingest.crawl --days 1 --max-matches 200
python -m src.parse.telemetry --all
python -m src.preprocess.clean --all
python scripts/build_sample.py --n 30
streamlit run app/Home.py
```

---

## 8. Testing & validation

- **Synthetic tests**: generate groups of points: (a) a group of 12 standing still for 2 minutes → must yield 1 gathering; (b) a group whose members change constantly (different people each step) → yields a crowd but **no** gathering; (c) 2 groups farther apart than δ → 2 separate crowds; (d) a slowly moving group (< δ per step) → 1 continuous crowd.
- **Mock validation**: run the full pipeline on mock matches and compare detected gatherings with `ground_truth.json` (precision / recall by time-span + area overlap). Print a small report; target recall ≥ 0.8 with default parameters. If it fails, fix the mining or the simulator, not the metric.
- **Contract test**: the same parser test suite runs on (a) mock output and (b) recorded real fixtures (added at M8). Both must pass.
- **Sanity check on real data**: in phases 0–1, gatherings should appear around well-known hot drops (Pochinki, School, Military Base). If not → recheck units (cm/m), the y axis, and the landing cut.
- A script that prints stats: points per match, actual Δt, clusters per timestamp, crowds/gatherings per match per phase.
- App check: every page runs without errors on `data/sample`, changing parameters doesn't crash, animations run smoothly.

---

## 9. Milestones (do them in order, stop and report after each)

**Phase A — Mock data (no key, no network to PUBG needed)**
- **M0 – Setup & schema exploration**: create the structure, `pyproject`, `.env.example`, `config.yaml` (`datasource: mock`), `.gitignore`. Explore the real response shape (section 1d, step 1) → `docs/schema.md` + `src/datasource/schema.py`. Download the official Erangel map image.
- **M1 – Mock data source**: `DataSource` protocol + factory, `MockDataSource`, `mock_sim.py` with ground truth, `crawl.py` working against the abstract source (idempotent, logs fetched / filtered / skipped). Generate 50 mock matches. Show the user a quick plot of one mock match on the map to confirm it looks plausible.

**Phase B — Foundation & end-to-end on mock data**
- **M2 – Parse & preprocess**: `inspect_telemetry.py` (works on any raw file), parser + cleaning + phases. Print the stats from section 8.
- **M3 – Mining**: snapshot/crowd/gathering + green synthetic tests + mock validation report against ground truth.
- **M4 – Core app**: Home + Data Explorer + Step-by-step (4 tabs) for one match, with the "MOCK DATA" badge.
- **M5 – Insights & Coach View**: analytics + the 2 pages; `build_sample.py` (builds `data/sample/mock/`).
- **M6 – Polish**: Sensitivity page, README, offline run from `data/sample`, Dockerfile / Streamlit Community Cloud instructions. **The demo must be fully presentable at this point on mock data.**

**Phase C — Real API, ready and waiting for the key**
- **M7 – Real data source (no key yet)**: `src/api/client.py` (rate limiter, 429 retry, `NetworkBlockedError`), `PubgApiDataSource`, `scripts/check_connectivity.py`, GitHub Actions workflow (section 1c) + `pull_cloud_data.py`. Unit-test the client with **mocked HTTP** (`responses` or `respx`) built from the shapes in `docs/schema.md`: success, 429 + reset header, connection reset, missing telemetry asset. Everything must pass with **no key**. Then **STOP** and tell the user exactly what to do next: (1) turn on Cloudflare WARP, (2) put `PUBG_API_KEY=...` in `.env`, (3) optionally add the repo secret for GitHub Actions, (4) say "key is ready".
- **M8 – Go live (after the user provides the key)**: run `check_connectivity.py` → one `/samples` call → download 1 match → run `inspect_telemetry.py` and **diff the real schema against `docs/schema.md`** (resolve every `UNVERIFIED` item). Fix the schema models, parser and, if needed, the mock simulator so mock and real stay identical in shape. Save recorded real fixtures to `tests/fixtures/real/` and make the contract test pass for both. Crawl ~50 real matches, run the pipeline, build `data/sample/real/`, and switch the app default to real data (mock stays selectable).

At each milestone: list the files created, the commands to test, and open issues. If real data deviates from assumptions (field names, Δt, mapName), **tell the user and update the config/schema** — don't silently work around it.

---

## 10. Limitations to state clearly in the app (Home page or footer)

- Position sampling is sparse (~10 s) → suited to macro behavior (gathering, rotations), not gunfight analysis.
- Zones are random → always compare within the same phase / zone conditions.
- Results are correlations, not causation; always show sample size.
- Public ranked data ≠ pro tournament data; if tournament matches are available, use them for validation.