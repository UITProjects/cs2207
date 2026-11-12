# Progress log (spec: developmentNote/spec.md, plan: ~/.claude/plans/now-plan-to-actual-breezy-frog.md)

## M0 — Setup & schema (done 2026-11-12 23:50)
- Moved old concert demo → `legacy/` (app.py, gathering_core.py, check_core.py, requirements.txt); `CLAUDE.MD` → `CLAUDE.md`.
- `pyproject.toml` (Python 3.11, uv), `uv.lock`, `.env.example`, `config.yaml`, `.gitignore`.
- `docs/schema.md` + `src/datasource/schema.py` (pydantic, extra=allow, UNVERIFIED markers).
- Map: `pubg/api-assets` `Erangel_Main_High_Res.png` (8192², remastered, LFS via media.githubusercontent.com) → `assets/maps/erangel.jpg` 2048² (840 KB). Full-res `erangel_full.png` gitignored. Decision: JPG instead of PNG (PNG at 2048 would be ~4 MB).
- `assets/erangel_places.yaml`: 26 places + 2 bridges, estimated from the map image (calibrate).
- Test: `uv sync && uv run ruff check . && uv run python -c "import src.datasource.schema"` ✅

## M1 — Mock data source (done 00:05)
- `src/config.py`, `src/datasource/{base,mock,mock_sim}.py`, `src/api/errors.py`, `src/ingest/crawl.py`, `scripts/plot_match.py`.
- Simulator: plane line → 2–4 scripted hot-drop brawls (3–5 squads) + weighted drops; 8 zones (white circle = `poisonGasWarning*`, blue = `safetyZone*`); loot → rotate into next zone, routing over West/East bridge when crossing to/from Sosnovka; cars for long rotations; scripted bridge camp (80% of matches); eliminations follow a target alive curve with victims weighted 1 + 0.3·(enemies within 200 m, max 8); ~3% dropped samples, ±1.5 s jitter; LogMatchEnd rankings. Ground truth spans are measured from simulated positions (≥ 8 scripted players inside the area; bridge ≥ 6).
- `DATASOURCE=mock uv run python -m src.ingest.crawl --max-matches 50` → 50 fetched, 17 filtered (other maps/solo), ~37 s, 20 MB raw. Re-run skips existing.
- Plot of mock-2207-0001 checked: hot drops at Georgopol/Rozhok/School/Pochinki, rotations through West Bridge, final circle on the island. Plausible.

## M2 — Parse & preprocess (done 00:15)
- `src/parse/telemetry.py` → `data/interim/{source}/{id}/` (positions, landings, zones, kills, results, meta.json); accountId → P001…, teamId → T01… ordered by (teamId, accountId), no names kept.
- `src/preprocess/clean.py` → `data/processed/{source}/{id}/`: landing cut, death cut, >60 m/s outlier filter (on foot), Δt=10 grid with interpolation only for gaps ≤ 30 s, phase labels from `warn_r` changes.
- `scripts/inspect_telemetry.py` (event counts, nested keys, Δt distribution). Mock Δt median 10.05 s.
- `tests/test_parse.py`: contract test parametrised over mock + any `tests/fixtures/real/*` (M8), resampler, phases. 
- Commands: `uv run python -m src.parse.telemetry --all && uv run python -m src.preprocess.clean --all` (50 matches ≈ 15 s), `uv run pytest`.
- Note: `data/interim/` added (gitignored) between parse and clean. `scripts/stats.py` is added with M3 because it prints mining stats too.

## M3 — Mining (done 00:38)
- `src/mining/{snapshot,hausdorff,crowd,gathering,pipeline}.py`: sklearn DBSCAN per t; symmetric Hausdorff (scipy) + bbox lower bound pruning (proof in docstring); Alg. 1 port (closed crowds, R set, branching, contained-crowd removal, time gaps close candidates); TAD port with numpy bit vectors, participators recomputed per sub-crowd, closed gatherings; `run_pipeline(tables, params) → MiningResult` (clusters, labels, links with d_H, crowds, TAD traces, gatherings, crowd_df/gathering_df with phase/centroid/radius/teams).
- `tests/test_mining.py`: §8 cases (a)–(d), fast group breaks the crowd, Divide case, closedness, margin checks on eps/δ/m_p. 14 tests pass.
- `scripts/validate_mock.py`: **recall 0.821** (hot_drop 0.75, bridge_camp 0.90, final_circle 0.98), precision 0.71, **0.68 s/match** (max 0.82). Match rule: time IoU ≥ 0.3 and centroid within GT radius + eps.
- Simulator fix (not the metric): bridge camps had too few people left (kill weight too strong, GT used ≥ 6 people < m_c). Now 3–4 fullest squads within 3.5 km, kill weight 1 + 0.12·enemies(≤8), GT ≥ 8 people everywhere.
- `scripts/stats.py` prints §8 stats.
- Open: on mock data almost every crowd is also a gathering at default params (squads stay together). The crowd ≠ gathering difference shows when you raise k_p / m_p. Hot-drop recall 0.75 is the weakest part: brawls lose people quickly.

## M4 — Core app (done 00:05, 13/11)
- `app/common.py` (CSS from legacy q/verdict boxes, sidebar: source picker + MOCK/REAL badge, match picker, §3 sliders with k_p ≤ k_c / m_p ≤ m_c clamps, reset button; cached loaders keyed by folder/match/params), `src/viz/map_plot.py` (map as layout image in meters, reversed y, square; zone circles per frame; convex hulls; ≤300-frame animation; zoom boxes), `src/analytics/gazetteer.py`.
- Pages: `app/Home.py` (pain point, 4 definitions + illustration, graphviz pipeline, provenance, limitations), `1_Data_Explorer.py`, `2_Step_by_step.py` (4 tabs: animation + zones; DBSCAN snapshot with hulls/sizes; crowd list + hull sequence + centroid path + d_H vs δ + size vs m_c; TAD trace, participators per cluster vs m_p, gathering forming→dissolving animation with participators outlined).
- `assets/maps/erangel_1024.jpg` (208 KB) is embedded in the figures, so pages stay light.
- Map alignment checked by rendering through kaleido (dev dep), and trajectories sit on land/bridges.
- `tests/test_app.py` AppTest: every page + param change + reset → pass.
