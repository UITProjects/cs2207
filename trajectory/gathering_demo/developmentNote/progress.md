# Development log

Engineering record of the PUBG Gathering Pattern demo: what was built at each milestone, the decisions behind it,
and how it was verified. The original implementation spec is `developmentNote/spec.md`. The current usage is in the README.

## M0 — Setup and schema
- The previous concert demo moved to `legacy/` (`app.py`, `gathering_core.py`, `check_core.py`) and stays as a reference. `CLAUDE.MD` was renamed `CLAUDE.md`.
- Python 3.11 with uv (`pyproject.toml`, `uv.lock`); ruff + pytest; `config.yaml` holds the filters, Δt, default mining parameters and paths; `.env.example`; `.gitignore`.
- `docs/schema.md` + `src/datasource/schema.py` (pydantic, `extra="allow"`) describe the PUBG match and telemetry shapes. Items that could not be confirmed from the docs were marked UNVERIFIED until real data arrived (M8).
- Map: the remastered Erangel image from `pubg/api-assets` (8192²), downscaled to `assets/maps/erangel.jpg` (2048², JPG to keep it under 1 MB) and `erangel_1024.jpg` (embedded in figures). `assets/erangel_places.yaml`: 26 places + 2 bridges in meters, calibrated visually (`scripts/calibrate_places.py`).

## M1 — Mock data source
- `DataSource` protocol + factory (`src/datasource/base.py`). `MockDataSource` + `mock_sim.py`: a seeded, vectorised simulator that emits the exact API JSON shapes (centimetres, `_D`/`_T`).
  - Plane and drops biased to hot drops; 8 shrinking zones; rotations routed over the bridges; vehicles.
  - Eliminations follow a target survival curve and are weighted by local density.
  - Scripted gatherings (hot-drop brawls, bridge camps, final circle) are written to `ground_truth.json`.
- `src/ingest/crawl.py`: idempotent; logs listed / fetched / filtered / skipped / failed. 50 mock matches take about 40 s.

## M2 — Parse and preprocess
- `src/parse/telemetry.py` produces positions, landings, zones, kills, results and meta. Units are converted cm → m, t is seconds since `LogMatchStart`, and ids are anonymised P###/T##, ordered by (teamId, accountId).
- `src/preprocess/clean.py`:
  - landing and death cuts, plus a speed outlier filter (> 60 m/s on foot);
  - resampling to Δt = 10 s, interpolating only gaps ≤ 30 s;
  - phases labelled from changes of the next-zone radius.
- `scripts/inspect_telemetry.py`: event counts, nested keys, Δt distribution. `scripts/stats.py`: per-match statistics.

## M3 — Mining
- `src/mining/`:
  - DBSCAN snapshot clusters per timestamp;
  - symmetric Hausdorff distance with bounding-box lower-bound pruning;
  - closed-crowd discovery (Algorithm 1: branching, contained-crowd removal);
  - Test-and-Divide with bit vectors, participators recomputed per sub-crowd, closed gatherings.
  
  `run_pipeline` returns a `MiningResult` (clusters, labels, links with d_H, crowds, TAD traces, gathering table).
- `tests/test_mining.py`:
  - synthetic cases with known answers: a stationary group, changing members (a crowd but no gathering), two distant groups, a slowly moving group;
  - plus a Divide case, closedness and parameter margins.
- `scripts/validate_mock.py`: precision / recall against the scripted ground truth (time IoU ≥ 0.3 and centroid within radius + eps). After the simulator was corrected (not the metric) so scripted groups stay physically compact: **recall 0.97, precision 0.79, ~0.6 s per match**.

## M4–M6 — First app, analytics, packaging
- Multipage Streamlit app (Vietnamese UI): step-by-step algorithm view, multi-match insights, a coach view and a sensitivity sweep, built on `src/viz/map_plot.py` (map in meters, reversed y, zone circles, hulls, frame animations).
- Committed offline sample (`data/sample/`), Dockerfile (python:3.11-slim, a build-time test + pipeline check), workflow path filters, README.
- The multi-match and coach pages were later removed (M4f) to keep the demo focused on trajectory mining.

## M7 — Real data source (no key required)
- `src/api/client.py`:
  - token bucket only on rate-limited endpoints (10 req/min); `/matches` and telemetry are unlimited;
  - 429 handling via `X-RateLimit-Reset`; `NetworkBlockedError` for resets and timeouts (3 retries, backoff);
  - the key comes from the environment, then `.env`, and is never logged.
- `PubgApiDataSource`, `scripts/check_connectivity.py`, `scripts/pull_cloud_data.py`, and `.github/workflows/pubg-crawl.yml` (daily cloud crawl to an artifact; it never commits).
- `tests/test_client.py` with mocked HTTP (`responses`): success flow, 429 + reset, connection reset, timeout, missing telemetry asset, missing key, rate limiting.
- The repository-root `.gitignore` ignored `[Ss]cripts`; the project `.gitignore` re-includes `scripts/`.

## M4b–M4f — Presentation-focused redesign
- **One match, movement first:** squad-centre tracks and route summaries (`src/analytics/movement.py`), team routes, a replay with trails and a follow camera, and a gathering timeline.
- **Time dimension:** `src/viz/cube.py` renders the paper's space–time cube (x, y, t) with the Erangel map as a textured floor.
  - The floor uses a brightness-banded colour scale: interpolating palette indices produced noise.
  - The z background is disabled to avoid z-fighting with the floor.
  - Used on the algorithm page (raw trajectories, cluster discs, crowd links with d_H, participators) and on the result page.
- **Team readability:** trajectories coloured per team, a team filter, legend entries per team.
- **Scope:** trajectory mining only. Two pages, algorithm first (🔬 Thuật toán) then result (🎯 Kết quả). Kill, ranking and coach content, multi-match analytics and their modules were removed.

## M8 — Real PUBG data
- **Probe findings** (documented in `docs/schema.md`; every UNVERIFIED item resolved):
  - public "official" matches are mostly AI bots (38 humans / 105 characters in one Erangel squad match), so they are not used;
  - `/tournaments` lists ~1 200 events; tournament matches come from the `tournament` shard (gameMode `esports-squad`, empty matchType, 16 teams × 4 players, no bots);
  - positions every 10.00 s; tournament telemetry starts ~2 min before `LogMatchStart` (pre-match positions are dropped); parachute landings can repeat (the first is kept);
  - the white `poisonGasWarning` circle is the next zone and the blue `safetyZone` circle the current one.
- **Datasets** (`scripts/fetch_datasets.py`): PGS 12 Grand Final (pinned, 5 Erangel matches) and the two newest tournaments with Erangel matches, SEA PACP26 and SEA PACI26 (2 each). An aborted 16 s remake is excluded by `min_duration_s: 600`.
- **Code:**
  - `TournamentDataSource`; crawl options `--tournament / --dataset / --label / --list-limit`; per-kind filters;
  - parse / clean `--dataset`;
  - the parser drops bots and NPCs and writes `players.parquet` (team tag + player name, kept only for tournament datasets);
  - `collapse_branches` merges closed crowds that differ only by the branch taken when a group splits (same span, same people). One final circle produced 64 such variants.
- **App:**
  - dataset and match pickers (★ = showcase match with the best gathering coverage);
  - REAL/MOCK badge; a names toggle (labels only, ids remain the keys);
  - choices persist across pages (shadow key + `on_change`).
- **Tests:** `tests/test_real.py` (names, team tags, bots, lobby positions, tournament filters, mocked tournament source, dataset discovery) and a trimmed real fixture with masked names in `tests/fixtures/real/`. The parser contract test runs on mock and real data.

## M9 — Data distribution, deployment and sizing
- **Data distribution:**
  - tournament raw data (`data/raw/<dataset>/`, ~23 MB) is committed so collaborators can re-parse without an API key;
  - processed data (`data/sample/`, ~1.5 MB) is baked into the image;
  - `NOTICE.md` files and the README state the PUBG API terms (not a stand-alone dataset, not covered by the repository licence), and the required trademark statement appears in the README and the app sidebar.
- **Deployment:** the image is validated under the pod security settings (non-root uid 1000, all capabilities dropped, no privilege escalation, base path `/trajectory/gathering`). Manifests pass `kubectl apply --dry-run=server`.
- **Performance** (profiled; load-tested with concurrent headless browsers):
  1. lazy tabs: only the open tab runs;
  2. read-only data and figures in `st.cache_resource`: one shared copy per pod, instead of a per-session unpickle that re-validated every Plotly trace (~0.3 s per figure) and held ~20 MiB per session;
  3. source file watcher disabled in the image (~70% of server CPU in a profile); disconnected sessions kept 60 s.
  
  Result: CPU per visitor for the full flow went from ~3 s to ~1.05 s; 10 concurrent visitors on one CPU from 54 s to 26 s.
- **Sizing for 40–50 concurrent visitors:**
  - 4 replicas × (request 250m / 256 MiB, limit 1 CPU / 512 MiB), totalling request 1 CPU / 1 GiB and limit 4 CPU / 2 GiB;
  - topology spread, PodDisruptionBudget (min 2), and Traefik sticky-cookie session affinity on the Service;
  - one pod at these limits served 26 sessions (13 concurrent visitors plus 13 switching datasets) with a peak of 384 MiB and no errors.
- **Release:** merge to `main` → CI builds the image and bumps its tag in `deploy/manifest/10-deployment.yaml` → Argo CD syncs. Set `replicas` back to 1 after the event.
