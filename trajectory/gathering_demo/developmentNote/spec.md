# Implementation Spec: PUBG Gathering Pattern Demo (from `CLAUDE.MD`)

> Original implementation spec (milestones M0–M8). The shipped scope evolved afterwards: the app is trajectory-only, it
> has two pages (algorithm, result), and it uses real tournament datasets. The multi-match / coach pages were removed.
> See `progress.md` and the README for the current state.

## Context
The current demo in `trajectory/gathering_demo/` mines Crowd/Gathering patterns (Zheng et al., ICDE 2013) on a **fake concert dataset**. It has a good workflow (tune params → inspect each algorithm step) but fake data and a vague use case. The spec replaces it with **real PUBG trajectories** (100 players/match), a mock-first pipeline, multi-match analytics and a coach-facing application, served by a multipage Streamlit app that runs fully offline from a committed sample.

Design decisions:
- **Replace in place**: project root = `trajectory/gathering_demo/` (call it `ROOT`). Old concert demo (`app.py`, `gathering_core.py`, `check_core.py`) moves to `ROOT/legacy/` as reference. The existing Dockerfile, k8s manifests (`deploy/manifest/*`), Argo app and `.github/workflows/gathering-demo.yml` are kept and updated so the existing `/trajectory/gathering` route serves the new app.
- **UI language: Vietnamese** (algorithm terms Crowd / Gathering / Participator / DBSCAN stay English), matching the old demo's style (`.streamlit/config.toml` theme, "q"/"verdict" boxes in `legacy/app.py`).

Delivery: M0–M7 are built end to end on mock data, each milestone recorded in `progress.md`. M8 (real data) needs a PUBG API key.

## Cross-cutting choices
- **Python 3.11 via uv** (`uv python install 3.11`, `pyproject.toml` + `uv.lock`), ruff + pytest. Commands run from `ROOT` as `uv run python -m src....`.
- **Rename `CLAUDE.MD` → `CLAUDE.md`** (Linux is case-sensitive; Claude Code only auto-loads `CLAUDE.md`).
- **Reuse** the proven algorithm logic in `legacy/gathering_core.py`: `discover_crowds()` (Alg. 1 sweep, closed crowds, "R" set for new candidates) and `tad()` (Test-and-Divide with participators recomputed per sub-crowd, bit vectors). Port them to numpy/scipy (sklearn DBSCAN, `scipy.spatial.distance.directed_hausdorff`) instead of rewriting from scratch. Also reuse `legacy/check_core.py`'s idea of a margin check (results stable under ±small param changes) in the synthetic tests.
- GitHub Actions workflows must live at the **repo root** `.github/workflows/`, so the crawler is `.github/workflows/pubg-crawl.yml` with `defaults.run.working-directory: trajectory/gathering_demo`. It uploads artifacts only (never commits to `main`), so it does not trigger the deploy workflow.
- Map image: download the remastered Erangel from `pubg/api-assets` (`Assets/Maps/`), downscale to ~2048 px for `assets/maps/erangel.png` (keep the app light); full-res stays gitignored if needed.
- Data size budget: ~180 steps × 100 players ≈ 18k rows/match → `data/sample/mock/` 30 matches ≈ <15 MB Parquet. OK to commit.

## Milestones

### Phase A — Mock data (no key, no PUBG network)

**M0 — Setup & schema exploration**
- `git mv` old demo into `legacy/`; rename CLAUDE.MD.
- Create `pyproject.toml` (deps from spec §7), `.env.example`, `config.yaml` (`datasource: mock`, shard `steam`, filters `Baltic_Main` / `squad,squad-fpp` / `competitive,official`, Δt=10, default params table §3, paths), `ROOT/.gitignore` (`.env`, `data/raw/`, `data/processed/`, keep `data/sample/`).
- Research real response shapes (official docs Telemetry Events/Objects/Matches; `chicken-dinner` / `pubg-python` models; any public sample telemetry) → `docs/schema.md` with `UNVERIFIED` markers; typed models in `src/datasource/schema.py` (pydantic, `extra="allow"` so real fields don't break parsing).
- Download + downscale map → `assets/maps/erangel.png`; draft `assets/erangel_places.yaml` (estimated coords, note "calibrate").
- Test: `uv sync && uv run ruff check . && uv run python -c "import src.datasource.schema"`.

**M1 — Mock data source**
- `src/datasource/base.py` (Protocol + `get_datasource()` from env `DATASOURCE` > `config.yaml`), `mock.py`, `mock_sim.py`.
- Simulator (seeded, vectorised numpy): plane line → 25 squads jump biased to hot drops → ~8 shrinking zones emitted in `LogGameStatePeriodic` → loot then rotate toward next zone, routing through chokepoints (bridges to Military island) when crossing water → occasional vehicles → probabilistic kills, higher in dense areas → positions every ~10 s with jitter and dropped samples → `LogMatchEnd` rankings. **Scripted gatherings** (hot-drop brawls in phase 0–1, bridge camps mid-game, final-circle crowding) recorded in `ground_truth.json` (t-span, center/radius, members).
- `src/ingest/crawl.py`: CLI over any `DataSource`; applies config filters; writes `data/raw/{source}/{match_id}/{match.json, telemetry.json.gz, ground_truth.json}`; idempotent (skips existing); logs fetched/filtered/skipped.
- `scripts/plot_match.py` → quick PNG of one mock match over the map for a visual plausibility check.
- Test: `DATASOURCE=mock uv run python -m src.ingest.crawl --max-matches 50` (< 1 min), then the plot.

### Phase B — End-to-end on mock data

**M2 — Parse & preprocess**
- `scripts/inspect_telemetry.py` (event-type counts, per-type key schema, LogPlayerPosition Δt distribution) — works on any raw file.
- `src/parse/telemetry.py` → raw tables `positions`, `zones`, `kills`, `results`, `match_meta` (cm → m, t = `_D` − LogMatchStart; hash accountId → `P001…`, teams → `T01…`).
- `src/preprocess/clean.py` → landing cut, death cut, outlier-jump filter (>60 m/s on foot), resample to Δt grid (interpolate gaps ≤30 s only), phase labels from `poisonGasWarningRadius` changes → `data/processed/{source}/{match_id}/*.parquet`.
- `scripts/stats.py` prints §8 stats. Tests: `tests/test_parse.py` (on mock output; real fixtures added at M8 = contract test), resampler/phase unit tests.

**M3 — Mining**
- `src/mining/snapshot.py` (DBSCAN per t, alive+landed only), `hausdorff.py` (symmetric + centroid/bbox lower-bound prune), `crowd.py` (port of Alg. 1, closed crowds, drop contained duplicates), `gathering.py` (port of TAD, closed gatherings); single `run_pipeline(match_tables, params)` returning a result object the app consumes (clusters, links with d_H, crowds, TAD traces, gatherings).
- Tests on synthetic data: §8 cases (a)–(d) with known answers, plus margin checks.
- `scripts/validate_mock.py`: precision/recall vs `ground_truth.json` (match = time-span IoU + centroid within area). Target **recall ≥ 0.8** at defaults; if it fails, fix mining or simulator, not the metric.
- Check per-match runtime < ~3 s.

**M4 — Core app** (`app/Home.py`, `app/pages/1_Data_Explorer.py`, `2_Step_by_step.py`)
- Shared `app/common.py`: sidebar (source badge "MOCK DATA"/"REAL PUBG DATA", match picker, §3 sliders with reset, `k_p ≤ k_c`, `m_p ≤ m_c` constraints), `st.cache_data` loaders keyed by (source, match, params).
- `src/viz/map_plot.py`: Plotly map background in meters, reversed y, square; frame animation (≤300 frames), zone circles as shapes, convex hulls, zoom-to-gathering.
- Step-by-step 4 tabs: raw animation + zones; snapshot clusters at t; crowds list + hull sequence + d_H vs δ chart; gatherings with participators highlighted, per-cluster participator bar vs `m_p`, forming→dissolving animation. Each tab has a Vietnamese explanation box.
- Home: pain point, definitions with small illustrations, pipeline diagram, data provenance, limitations (§10).
- Test: `uv run streamlit run app/Home.py` + `streamlit.testing.v1.AppTest` smoke test per page.

**M5 — Insights & Coach View**
- `src/analytics/`: `gazetteer.py` (nearest place), `hotspots.py` (200 m grid × phase), `outcomes.py` (elimination ≤120 s after participating vs same-phase baseline, ranking by participations, kills inside vs outside hull, always with n), `zone.py` (edge/center/outside, forced vs chosen; phase ≥6 forced), `team_report.py` (VOD timestamps).
- Pages `3_Insights.py`, `4_Coach_View.py` (route-risk sentence generator + team report CSV export). `scripts/calibrate_places.py`.
- `scripts/build_sample.py --n 30` → `data/sample/mock/` (picks matches with good gathering coverage; precomputes multi-match aggregates at default params so Insights loads instantly).

**M6 — Polish**
- `5_Sensitivity.py` (sweep δ / m_c / … → #crowds, #gatherings, mean participators).
- README (install, crawl, pipeline, run, deploy), app reads `data/sample` when `data/processed` is empty.
- Update `Dockerfile` (python:3.11-slim, copy `app/ src/ assets/ config.yaml data/sample/`, build-time check = run pytest synthetic tests + pipeline on one sample match instead of `check_core.py`, `CMD streamlit run app/Home.py`), `.dockerignore`, and the deploy workflow path filters. k8s manifests stay (base URL path already set). Add Streamlit Community Cloud notes.
- **Demo is fully presentable on mock data here.**

### Phase C — Real API, waiting for the key

**M7 — Real data source (no key)**
- `src/api/client.py`: session with auth/gzip headers, token-bucket limiter (10 req/min for limited endpoints only; `/matches` and telemetry unlimited), 429 retry using `X-RateLimit-Reset`, `NetworkBlockedError` for reset/ConnectionError/timeouts (connect 10 s, read 60 s), ≤3 retries with backoff, never prints the key. Key from env first, then `.env`.
- `src/datasource/pubg_api.py` (`/samples` → match IDs, `/matches/{id}`, telemetry asset URL).
- `scripts/check_connectivity.py` (status + one telemetry CDN URL, single attempt, clear hint when the network blocks PUBG), `.github/workflows/pubg-crawl.yml` (daily cron `17 20 * * *` + dispatch; crawl → parse → preprocess → upload `data/processed/` artifact, 90-day retention), `scripts/pull_cloud_data.py` (`gh run download`).
- Tests with `responses`: success, 429+reset header, connection reset, missing telemetry asset — all pass with no key.
- Hand-off checklist for M8: network access to PUBG (VPN if blocked) → `PUBG_API_KEY=...` in `ROOT/.env` → (optional) repo secret `PUBG_API_KEY`.

**M8 — Go live (after key)**
- `check_connectivity.py` → one `/samples` call → download 1 match → `inspect_telemetry.py` → diff vs `docs/schema.md`, resolve every `UNVERIFIED`, measure real Δt, confirm `Baltic_Main`. Fix schema/parser/simulator so mock and real stay identical in shape; document every deviation.
- Save trimmed real fixtures to `tests/fixtures/real/` (anonymised); contract test passes for mock + real.
- Crawl ~50 real matches, run pipeline, sanity check (early gatherings near Pochinki/School/Military), `build_sample.py` → `data/sample/real/`, switch app default to real (mock still selectable).

## Critical files
- New: `ROOT/pyproject.toml`, `config.yaml`, `src/{datasource,api,ingest,parse,preprocess,mining,analytics,viz}/…`, `app/Home.py`, `app/pages/*`, `scripts/*`, `tests/*`, `docs/schema.md`, `assets/*`, `/.github/workflows/pubg-crawl.yml`.
- Modified: `ROOT/Dockerfile`, `ROOT/.dockerignore`, `/.github/workflows/gathering-demo.yml` (paths), `CLAUDE.MD` → `CLAUDE.md`.
- Moved: `app.py`, `gathering_core.py`, `check_core.py` → `ROOT/legacy/` (algorithm source for the port).

## Verification (end state)
1. `uv run pytest` — synthetic mining tests, parser contract tests (mock + real fixtures), client tests with mocked HTTP.
2. `uv run python scripts/validate_mock.py` — recall ≥ 0.8 vs ground truth at default params.
3. Full CLI chain from §7 (`crawl → parse → clean → build_sample`) on mock, then on real at M8.
4. `uv run streamlit run app/Home.py` with no `.env` and no network: every page loads from `data/sample`, sliders don't crash, animations play; AppTest smoke tests in pytest.
5. `docker build` succeeds (build-time checks pass) and the container serves under `/trajectory/gathering`.
