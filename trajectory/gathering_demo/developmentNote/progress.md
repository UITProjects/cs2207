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
