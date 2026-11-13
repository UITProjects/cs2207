# Gathering patterns on PUBG trajectories (CS2207 · Nhóm 12)

This demo mines **Crowd / Gathering patterns** (Zheng et al., *On Discovery of Gathering Patterns from Trajectories*, ICDE 2013) from PUBG squad matches on Erangel. It ships as a multipage **Streamlit** app (Vietnamese UI) that runs fully offline from the committed sample in `data/sample/`.

The demo is for the final presentation, so it goes straight to the point. There is **one match** (`mock-2207-0001`) and **two pages** (`app/Home.py`, `st.navigation`), with no terminology recap:

- **🎮 Trận đấu** (`app/views/match.py`): **value first**. A value-chain strip shows the flow: players → points → DBSCAN clusters → crowds → gatherings (mining, blue) → coach takeaways → VOD moments (value, orange). Below it are tabs:
  1. 💡 **Kết luận cho HLV**: 4 cards from `src/analytics/coach.py`. Each card has a headline number, a "👉 HLV" action and the evidence gatherings (opens the encounter in 3D/2D). The cards cover:
     - the cost of hot drops;
     - the winner's route;
     - the chokepoint trap;
     - elimination rate inside vs outside gatherings.
  2. 🎬 **VOD cần xem lại**: per team, the timestamps of every gathering it was in, with teams met, participators and outcome. Selecting a row replays it; CSV export.
  3. 🗺️ Di chuyển: routes, replay with trails and follow camera, 3D x–y–t cube.
  4. 🔄 Xoay bo.
  5. ⚔️ Chạm trán: Gantt + encounter in 3D/2D.
- **🔬 Thuật toán** (`app/views/algorithm.py`): the same match, step by step, with parameter sliders. A **3D x–y–t** view (default, like Fig. 1c of the paper / the old concert demo) or 2D. The steps are:
  1. ① trajectories;
  2. ② snapshot cluster discs;
  3. ③ crowds with dashed d_H links;
  4. ④ TAD, with participators in orange and gathering clusters in blue.

  The 3D views are drawn by `src/viz/cube.py`.

Recap and multi-match pages (intro, Data Explorer, Insights, Coach View, Sensitivity) are kept in `app/archive/` and are still smoke-tested.

- Data comes from a **mock simulator** that emits the exact PUBG API JSON shapes. The **real PUBG API** source is ready and switches on once a key is set (`DATASOURCE=pubg`).

Served at `https://cs2207.datrollout.dev/trajectory/gathering/`. The previous concert demo lives in `legacy/`.

## Install

```bash
cd trajectory/gathering_demo
uv python install 3.11
uv sync                         # runtime + dev deps (pytest, ruff, responses)
uv run streamlit run app/Home.py
```

Without uv: `python3.11 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`.

## Pipeline (same commands for mock and real; switch with `DATASOURCE=mock|pubg`)

```bash
DATASOURCE=mock uv run python -m src.ingest.crawl --max-matches 50     # data/raw/mock/{id}/ (idempotent)
uv run python -m src.parse.telemetry --all --source mock               # data/interim/mock/{id}/*.parquet
uv run python -m src.preprocess.clean --all --source mock              # data/processed/mock/{id}/*.parquet
uv run python scripts/validate_mock.py                                 # recall vs ground truth (target ≥ 0.8)
uv run python scripts/build_sample.py --n 30 --source mock             # data/sample/mock/ (+ _aggregates/)
uv run streamlit run app/Home.py
```

The app reads `data/processed/{source}` when it exists and falls back to the committed `data/sample/{source}` otherwise. It never calls the API. With a single match, the sidebar shows no picker.

**One match only:** the committed sample holds just `mock-2207-0001` (`build_sample.py --match mock-2207-0001`). The local processed/interim folders were trimmed to that same match. To get all 50 mock matches back, run the pipeline above: `data/raw/mock` is kept, and the crawl is deterministic.

Other helper scripts:

| Script | Purpose |
|---|---|
| `scripts/inspect_telemetry.py <telemetry.json.gz>` | event counts, actual keys per event, LogPlayerPosition Δt |
| `scripts/stats.py` | points/match, Δt, clusters per t, crowds/gatherings per phase |
| `scripts/plot_match.py <raw match dir>` | PNG of one raw match (+ mock ground truth) on the map |
| `scripts/calibrate_places.py` | overlay of `assets/erangel_places.yaml` on the map |
| `scripts/check_connectivity.py` | can this network reach PUBG? (WARP hint) |
| `scripts/pull_cloud_data.py` | download processed data from the GitHub Actions crawler |

## Layout

```
config.yaml                 filters (Baltic_Main, squad/squad-fpp, official/competitive), Δt, default params, paths
src/datasource/             DataSource protocol + factory, schema (pydantic), mock simulator, PUBG API source
src/api/client.py           rate limiter (10 rpm on limited endpoints), 429 retry, NetworkBlockedError
src/ingest/crawl.py         crawl CLI      src/parse/telemetry.py   raw → tables (cm→m, anonymised P001/T01)
src/preprocess/clean.py     landing/death cut, outlier filter, Δt resampling (gaps ≤ 30 s), phases
src/mining/                 snapshot (DBSCAN), hausdorff (+bbox lower bound), crowd (Alg. 1), gathering (TAD), pipeline
src/analytics/              gazetteer, hotspots, outcomes, zone, team_report, aggregate
src/viz/map_plot.py         Plotly map (meters, reversed y), animations, hulls, zone circles
src/viz/cube.py             3D space-time cube (x, y, t): textured map floor, disc meshes, team/algorithm cubes
src/analytics/movement.py   team tracks (squad centre), rotation summary, distance to the zone edge
app/Home.py                 router: app/views/{match,algorithm}.py; app/archive/* = recap + multi-match pages
docs/schema.md              PUBG response shapes (UNVERIFIED items get checked at M8)
```

## Tests

```bash
uv run ruff check .
uv run pytest            # synthetic mining cases, parser contract (mock + tests/fixtures/real), API client (mocked HTTP), app smoke
```

## Real PUBG data

1. The ISP may reset connections to PUBG domains. Turn on **Cloudflare WARP** first, then run `uv run python scripts/check_connectivity.py`.
2. Put `PUBG_API_KEY=...` in `trajectory/gathering_demo/.env` (gitignored; see `.env.example`). The key is read from the environment first, then from `.env`, and is never printed.
3. Run `DATASOURCE=pubg uv run python -m src.ingest.crawl --max-matches 50`, then parse, clean and `build_sample.py --source pubg` (writes `data/sample/real/`).

### Cloud crawler (GitHub Actions)

`.github/workflows/pubg-crawl.yml` runs daily at 20:17 UTC (03:17 Vietnam time) and can also be started by hand. It crawls, then parses and cleans in the same job, and uploads `data/processed/` as an artifact kept for 90 days. It never commits to `main`.

- Add the repository secret **`PUBG_API_KEY`** (Settings → Secrets and variables → Actions).
- Start a run by hand from Actions → *pubg-crawl* → *Run workflow*.
- Download the results locally with `uv run python scripts/pull_cloud_data.py` (needs the `gh` CLI, logged in).

PUBG keeps match data for only 14 days, so leave the daily schedule on.

## Deploy

- `Dockerfile` (python:3.11-slim) copies `app/ src/ assets/ config.yaml data/sample/`. At build time it runs the synthetic mining and parser tests plus the full pipeline on one sample match, so a broken algorithm fails the build. The container serves on 8501.
- CI: `.github/workflows/gathering-demo.yml` builds a multi-arch image on pushes to `main`, then bumps the tag in `deploy/manifest/10-deployment.yaml`. Argo CD (`deploy/argo-app.yaml`) syncs it. The manifest sets `STREAMLIT_SERVER_BASE_URL_PATH=trajectory/gathering`.
- Local: `docker build -t gathering-demo . && docker run -p 8501:8501 gathering-demo`.
- `requirements.txt` is generated with `uv export --no-dev --no-hashes --format requirements-txt` plus `pytest` (used for the build-time check).

### Streamlit Community Cloud

Point a new app at this repo with main file `trajectory/gathering_demo/app/Home.py` and Python 3.11. The app adds its project root to `sys.path` and reads `data/sample/`, so no secrets are needed. Copy the theme from `.streamlit/config.toml` into the app's settings if Cloud does not pick it up from the subfolder.

## Limitations (also shown in the app)

- Positions are sampled about every 10 s, so the data suits macro behaviour (gatherings, rotations), not gunfights.
- Zones are random, so compare only within the same phase or zone conditions.
- Results are correlations, not causation, and always come with *n*. Public ranked data is not the same as pro tournament data.
- The mock simulator scripts hot-drop brawls, bridge camps and final-circle crowding. Its numbers show that the pipeline works; they say nothing about real PUBG behaviour.
