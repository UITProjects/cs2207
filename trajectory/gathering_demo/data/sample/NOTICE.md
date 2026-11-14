# Data notice

The match and telemetry data in `data/raw/` and the processed tables derived from it in `data/sample/` come from
the **PUBG Developer API** (https://developer.pubg.com) and are subject to the
[PUBG API Terms of Service](https://developer.pubg.com/tos).

- They are included **as part of this CS2207 course demo** (non-commercial), so the app and its pipeline can be
  run, tested and edited without an API key. They are **not** offered as a stand-alone dataset and are **not**
  covered by this repository's own license. Do not sell or redistribute them on their own.
- Matches are public esports tournaments (PGS 12 Grand Final, SEA PACP26, SEA PACI26). Player names are the
  in-game names shown in those broadcasts. Contact the repository owner to have any data removed.
- To regenerate or extend them with your own key: `uv run python scripts/fetch_datasets.py` (see README).

PUBG, PLAYERUNKNOWN'S BATTLEGROUNDS and all related logos are trademarks of PUBG Corporation or its affiliates.
This project is not affiliated with or endorsed by PUBG Corporation or KRAFTON.
