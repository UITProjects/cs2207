"""Plausible PUBG squad match simulator (Erangel, 25 squads x 4) — the MOCK data source.

Emits the same raw JSON shapes as the PUBG API (docs/schema.md): a JSON:API match document and a
telemetry event list (`_D`, `_T`, coordinates in centimeters). It also returns a ground truth of
the gatherings it scripts on purpose, used only by `scripts/validate_mock.py`:

* hot-drop brawls (phase 0-1): 3-5 squads land around one brawl point of a hot drop and loot it
  for 3-5 minutes;
* bridge camps (mid game): 2-3 squads drive to a bridge to the Military Base island and hold it;
* final-circle crowding: the last zones are small, so the survivors are packed together.

Squads are simulated at the squad level (centre + per-member AR(1) offsets) on a 10 s grid, which
keeps it vectorised and fast (< 1 s per match). Eliminations follow a target "alive" curve, and
the victims are drawn with weight growing with the number of enemies nearby, so density and
elimination risk are linked (visible but noisy signal): weight 1 + 0.25·min(enemies within 200 m, 4).
Ground truth spans are measured on the simulated positions (≥ 8 scripted players in the area for
≥ 60 s); scripts that fell apart earlier (people killed / dispersed) are not ground truth.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml
from shapely.geometry import Point, Polygon
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[2]
MAP_M = 8160.0
_PX = MAP_M / 1024  # the polygons below were read off a 1024 px preview of the map

# rough land masses (meters); good enough to route through the bridges
MAINLAND = Polygon([(x * _PX, y * _PX) for x, y in [
    (60, 125), (250, 118), (480, 128), (700, 60), (870, 90), (880, 300), (940, 480), (960, 580),
    (850, 680), (760, 630), (700, 630), (560, 600), (520, 630), (430, 650), (350, 690), (240, 700),
    (230, 790), (160, 780), (80, 700), (110, 350), (60, 140)]])
ISLAND = Polygon([(x * _PX, y * _PX) for x, y in [
    (365, 800), (420, 690), (560, 668), (700, 690), (790, 740), (800, 800), (760, 880), (600, 920),
    (450, 915), (370, 860)]])
_MAIN_P, _ISL_P = prep(MAINLAND), prep(ISLAND)

# zone schedule: (white circle appears at t, radius m); shrink happens in the second half of each gap
ZONE_APPEAR = [90, 420, 690, 900, 1080, 1230, 1350, 1450]
ZONE_RADIUS = [2900, 1800, 1100, 650, 380, 220, 120, 60]
MATCH_END = 1700
FOOT, CAR = 5.0, 14.0  # m/s
DROP_SAMPLE = 0.03  # share of position samples that go missing
MAPS_OTHER = ["Desert_Main", "Savage_Main", "Tiger_Main"]
MIN_GT_STEPS = 6  # a scripted gathering counts as ground truth only if it really lasted ≥ 60 s


@lru_cache(maxsize=1)
def load_places() -> list[dict]:
    with open(ROOT / "assets/erangel_places.yaml", encoding="utf8") as f:
        return yaml.safe_load(f)["places"]


def mass_of(x: float, y: float) -> int:
    """1 = Sosnovka island, 0 = mainland (anything not on the island)."""
    return 1 if _ISL_P.contains(Point(x, y)) else 0


def on_land(x: float, y: float) -> bool:
    p = Point(x, y)
    return _MAIN_P.contains(p) or _ISL_P.contains(p)


def random_land_point(rng: np.random.Generator, cx: float, cy: float, r: float) -> tuple[float, float]:
    for _ in range(200):
        a, d = rng.uniform(0, 2 * np.pi), r * math.sqrt(rng.uniform())
        x, y = cx + d * math.cos(a), cy + d * math.sin(a)
        if 0 < x < MAP_M and 0 < y < MAP_M and on_land(x, y):
            return x, y
    return cx, cy


@dataclass
class Squad:
    team_id: int
    members: list[int]
    drop: tuple[float, float]
    jump_t: float
    land_t: float
    loot_until: float
    pos: np.ndarray = field(default_factory=lambda: np.zeros(2))
    path: list[tuple[float, float]] = field(default_factory=list)
    speed: float = FOOT
    hold_until: float = 0.0
    scripted_until: float = -1.0  # while t < this the squad follows its script only
    anchor: tuple[float, float] | None = None
    spread: float = 20.0


def _iso(base: dt.datetime, t: float) -> str:
    return (base + dt.timedelta(seconds=float(t))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _hex(rng: np.random.Generator, n: int = 32) -> str:
    return "".join(rng.choice(list("0123456789abcdef"), n))


def match_meta(match_id: str, seed: int, index: int) -> dict:
    """Cheap match-level attributes (decided before the telemetry is simulated)."""
    rng = np.random.default_rng([seed, index, 1])
    r = rng.uniform()
    map_name = "Baltic_Main" if r < 0.85 else str(rng.choice(MAPS_OTHER))
    mode = str(rng.choice(["squad-fpp", "squad"], p=[0.7, 0.3])) if rng.uniform() < 0.92 else "solo-fpp"
    mtype = str(rng.choice(["official", "competitive"], p=[0.6, 0.4]))
    created = dt.datetime(2026, 11, 1, tzinfo=dt.UTC) + dt.timedelta(hours=7 * index + float(rng.uniform(0, 5)))
    return dict(id=match_id, mapName=map_name, gameMode=mode, matchType=mtype, createdAt=created)


def simulate(match_id: str, seed: int, index: int, n_squads: int = 25, squad_size: int = 4,
             sample_dt: float = 10.0) -> tuple[dict, list[dict], dict]:
    """Return (match JSON:API document, telemetry events, ground truth)."""
    meta = match_meta(match_id, seed, index)
    rng = np.random.default_rng([seed, index, 2])
    places = load_places()
    hot = [p for p in places if p["kind"] in ("hot", "town")]
    bridges = [p for p in places if p["kind"] == "bridge"]
    n = n_squads * squad_size
    team_of = np.repeat(np.arange(1, n_squads + 1), squad_size)
    accounts = [f"account.{_hex(rng)}" for _ in range(n)]
    names = [f"mock_{_hex(rng, 6)}" for _ in range(n)]
    base = meta["createdAt"]

    # ---- plane line ----
    ang = rng.uniform(0, 2 * np.pi)
    c0 = np.array(random_land_point(rng, MAP_M / 2, MAP_M / 2, 1800))
    u = np.array([math.cos(ang), math.sin(ang)])
    p_start = c0 - u * 6000
    plane_speed = 130.0

    # ---- drops: 2-4 hot drops with 3-5 squads each, the rest spread by weight ----
    gt: list[dict] = []
    hot_w = np.array([p["hot"] for p in hot])
    n_hot = int(rng.integers(2, 5))
    hot_sites = rng.choice([i for i, p in enumerate(hot) if p["kind"] == "hot"], n_hot, replace=False)
    order = list(rng.permutation(n_squads))
    assign: dict[int, int] = {}
    for hs in hot_sites:
        for _ in range(int(rng.integers(3, 6))):
            if order:
                assign[order.pop()] = int(hs)
    rest_w = hot_w.copy()
    rest_w[hot_sites] = 0.02
    for s in order:
        assign[s] = int(rng.choice(len(hot), p=rest_w / rest_w.sum()))

    brawl_pt = {int(h): random_land_point(rng, hot[int(h)]["x"], hot[int(h)]["y"], hot[int(h)]["r"] * 0.3)
                for h in hot_sites}
    squads: list[Squad] = []
    for s in range(n_squads):
        pl = hot[assign[s]]
        brawl = assign[s] in set(int(h) for h in hot_sites)
        if brawl:
            d = random_land_point(rng, *brawl_pt[assign[s]], 90)
        else:
            d = random_land_point(rng, pl["x"], pl["y"], pl["r"] + 600)
        along = float(np.dot(np.array(d) - p_start, u))
        jump = float(np.clip(along / plane_speed, 8, 12000 / plane_speed)) + rng.uniform(-3, 3)
        off = float(np.linalg.norm(np.array(d) - (p_start + u * along)))
        land = jump + 25 + min(off, 2000) / 45 + rng.uniform(0, 8)
        loot = land + (rng.uniform(170, 300) if brawl else rng.uniform(120, 360))
        sq = Squad(team_id=s + 1, members=list(range(s * squad_size, (s + 1) * squad_size)), drop=d,
                   jump_t=jump, land_t=land, loot_until=loot, anchor=d, spread=35.0 if brawl else 20.0)
        sq.pos = np.array(d, dtype=float)
        squads.append(sq)

    for hs in hot_sites:
        pl = hot[int(hs)]
        members = [s for s in range(n_squads) if assign[s] == int(hs)]
        gt.append(dict(kind="hot_drop", place=pl["name"], center=list(brawl_pt[int(hs)]), radius=250,
                       squads=[squads[s].team_id for s in members],
                       _members=[m for s in members for m in squads[s].members]))

    # ---- zones ----
    zones = []  # (appear_t, shrink_start, shrink_end, cx, cy, r)
    cx, cy, r_prev = random_land_point(rng, MAP_M / 2, MAP_M / 2, 2200) + (5800.0,)
    if rng.uniform() < 0.3:  # sometimes pull the circle towards the Military island
        cx, cy = 0.5 * cx + 0.5 * 4600, 0.5 * cy + 0.5 * 6000
    first_c = (MAP_M / 2, MAP_M / 2)
    prev = (first_c[0], first_c[1], 5800.0)
    for i, (ta, rr) in enumerate(zip(ZONE_APPEAR, ZONE_RADIUS, strict=True)):
        if i == 0:
            nc = (cx, cy)
        else:
            nc = random_land_point(rng, prev[0], prev[1], max(prev[2] - rr, 1.0) * 0.9)
        gap = (ZONE_APPEAR[i + 1] if i + 1 < len(ZONE_APPEAR) else MATCH_END - 40) - ta
        zones.append((ta, ta + 0.35 * gap, ta + 0.85 * gap, nc[0], nc[1], float(rr), prev))
        prev = (nc[0], nc[1], float(rr))

    def zone_at(t: float):
        """(safety centre, safety radius, warning centre, warning radius, phase)."""
        safe = (first_c[0], first_c[1], 5800.0)
        warn, phase = safe, 0
        for ta, s0, s1, zx, zy, zr, pv in zones:
            if t < ta:
                break
            phase += 1
            warn = (zx, zy, zr)
            if t >= s1:
                safe = warn
            elif t >= s0:
                f = (t - s0) / (s1 - s0)
                safe = (pv[0] + f * (zx - pv[0]), pv[1] + f * (zy - pv[1]), pv[2] + f * (zr - pv[2]))
            else:
                safe = pv
        return safe, warn, phase

    # ---- bridge camp script (mid game) ----
    camp = None
    if rng.uniform() < 0.8:
        br = bridges[int(rng.integers(len(bridges)))]
        side = int(rng.integers(2))
        cpt = (br["x1"], br["y1"]) if side == 0 else (br["x2"], br["y2"])
        camp = dict(t0=float(rng.uniform(420, 560)), bridge=br, point=cpt, k=4,
                    hold=float(rng.uniform(170, 260)))

    # ---- simulation on the sample grid ----
    times = np.arange(0, MATCH_END + 1e-9, sample_dt)
    alive = np.ones(n, bool)
    death_t = np.full(n, np.inf)
    offs = rng.normal(0, 15, (n, 2))
    pos_hist = np.full((len(times), n, 2), np.nan)
    z_ground = rng.uniform(5, 60, n)  # ground height (m)
    in_car = np.zeros(n, bool)
    kills: list[dict] = []
    team_rank: dict[int, int] = {}
    last_alive_target = 100.0
    debt = 0.0
    camp_squads: list[int] = []
    camp_end = None
    winner_team = None

    def target_alive(t: float) -> float:
        if t < 150:
            return n
        if t < 1450:
            return n * (14 / 100) ** ((t - 150) / 1300)
        return max(squad_size, 14 - (14 - squad_size) * (t - 1450) / (MATCH_END - 60 - 1450))

    def route(sq: Squad, tgt: tuple[float, float]):
        a, b = mass_of(*sq.pos), mass_of(*tgt)
        if a == b:
            sq.path = [tgt]
            return
        br = min(bridges, key=lambda q: math.dist(sq.pos, (q["x1"], q["y1"]) if a == 0 else (q["x2"], q["y2"])))
        e1, e2 = ((br["x1"], br["y1"]), (br["x2"], br["y2"])) if a == 0 else ((br["x2"], br["y2"]), (br["x1"], br["y1"]))
        sq.path = [e1, e2, tgt]

    for k, t in enumerate(times):
        safe, warn, phase = zone_at(t)
        # bridge camp: pick the squads nearest to the bridge end
        if camp and not camp_squads and t >= camp["t0"]:
            cands = [s for s in squads if alive[s.members].sum() >= 3 and t > s.land_t
                     and math.dist(s.pos, camp["point"]) < 3500]
            cands.sort(key=lambda s: (-int(alive[s.members].sum()), math.dist(s.pos, camp["point"])))
            camp_squads = [s.team_id for s in cands[: camp["k"]]]
            for s in cands[: camp["k"]]:
                s.speed = CAR
                route(s, random_land_point(rng, *camp["point"], 60))
                s.scripted_until = np.inf
                s.anchor = None
        if camp_squads and camp_end is None:
            cs = [squads[i - 1] for i in camp_squads if alive[squads[i - 1].members].any()]
            if cs and all(not s.path for s in cs):
                camp_end = t + camp["hold"]
            elif t > camp["t0"] + 400:
                camp_end = t
        if camp_end is not None and t >= camp_end:
            for i in camp_squads:
                squads[i - 1].scripted_until = -1
            camp_end = np.inf  # released

        for sq in squads:
            m = sq.members
            if not alive[m].any():
                continue
            if t < sq.land_t:  # plane / parachute: centre follows plane then glides to the drop
                if t < sq.jump_t:
                    p = p_start + u * plane_speed * t
                else:
                    jp = p_start + u * plane_speed * sq.jump_t
                    f = (t - sq.jump_t) / (sq.land_t - sq.jump_t)
                    p = jp + f * (np.array(sq.drop) - jp)
                sq.pos = p.astype(float)
                continue
            if sq.scripted_until < t:  # free behaviour
                if t < sq.loot_until:
                    pass  # loot around the anchor
                elif not sq.path:
                    wx, wy, wr = warn
                    dist_w = math.dist(sq.pos, (wx, wy))
                    if (dist_w > 0.8 * wr or t >= sq.hold_until) and phase > 0:
                        tgt = random_land_point(rng, wx, wy, 0.65 * wr)
                        route(sq, tgt)
                        sq.speed = CAR if math.dist(sq.pos, tgt) > 1300 and rng.uniform() < 0.5 else FOOT
                        sq.anchor = None
                        sq.hold_until = t + rng.uniform(60, 200)
                    elif phase == 0 and t >= sq.hold_until:
                        tgt = random_land_point(rng, *sq.pos, 700)
                        route(sq, tgt)
                        sq.speed = FOOT
                        sq.hold_until = t + rng.uniform(80, 200)
            # move along the path
            if sq.path:
                step = sq.speed * sample_dt
                while sq.path and step > 0:
                    w = np.array(sq.path[0])
                    d = float(np.linalg.norm(w - sq.pos))
                    if d <= step:
                        sq.pos, step = w, step - d
                        sq.path.pop(0)
                    else:
                        sq.pos = sq.pos + (w - sq.pos) / d * step
                        step = 0
                if not sq.path:
                    sq.anchor = (float(sq.pos[0]), float(sq.pos[1]))
                    sq.speed = FOOT
            elif sq.anchor is not None:
                a = np.array(sq.anchor)
                sq.pos = a + 0.85 * (sq.pos - a) + rng.normal(0, 40 if t < sq.loot_until else 12, 2)
            # zone pressure: anyone outside the shrinking blue circle drifts inward
            d_safe = math.dist(sq.pos, safe[:2])
            if phase >= 1 and d_safe > safe[2] and not sq.path and sq.scripted_until < t:
                sq.pos = sq.pos + (np.array(safe[:2]) - sq.pos) / d_safe * min(FOOT * sample_dt, d_safe - safe[2] + 5)
            in_car[m] = sq.speed == CAR and bool(sq.path)

        # member positions = squad centre + AR(1) offsets
        for sq in squads:
            m = sq.members
            sd = (sq.spread if t < sq.loot_until else 12.0) * 0.6
            offs[m] = 0.8 * offs[m] + rng.normal(0, sd, (len(m), 2))
            if in_car[m].any():
                offs[m] *= 0.1
            pos_hist[k, m] = sq.pos + offs[m]
        pos_hist[k, ~alive] = np.nan

        # eliminations: follow the target alive curve, victims weighted by nearby enemies
        landed = np.array([t >= squads[team_of[i] - 1].land_t for i in range(n)])
        debt += last_alive_target - target_alive(t)
        last_alive_target = target_alive(t)
        cand = np.where(alive & landed)[0]
        while debt >= 1 and len(cand) > squad_size:
            P = pos_hist[k, cand]
            D = np.linalg.norm(P[:, None] - P[None], axis=2)
            enemy = team_of[cand][:, None] != team_of[cand][None]
            near = ((D < 200) & enemy).sum(1)
            if winner_team is None and len(set(team_of[cand])) <= 2 and t > 1450:
                winner_team = int(rng.choice(sorted(set(team_of[cand]))))
            w = 1.0 + 0.25 * np.minimum(near, 4).astype(float)
            if winner_team is not None:
                w[team_of[cand] == winner_team] = 0
            if w.sum() == 0:
                break
            vi = int(rng.choice(len(cand), p=w / w.sum()))
            v = int(cand[vi])
            en = np.where(enemy[vi])[0]
            killer = int(cand[en[np.argmin(D[vi, en])]]) if len(en) else None
            if killer is not None and D[vi, en].min() > 900:
                killer = None  # blue-zone / unknown
            alive[v] = False
            death_t[v] = t + rng.uniform(0, sample_dt * 0.9)
            kills.append(dict(t=float(death_t[v]), victim=v, killer=killer))
            tv = int(team_of[v])
            if not alive[team_of == tv].any():
                team_rank[tv] = len(set(team_of[alive])) + 1
            debt -= 1
            cand = np.where(alive & landed)[0]
        if t >= MATCH_END - 60 and len(set(team_of[alive])) <= 1:
            end_t = t
            break
    else:
        end_t = float(times[-1])
    # whoever is still alive at the end: one winner, the rest ranked by alive count
    rem = sorted(set(team_of[alive]), key=lambda tm: -alive[team_of == tm].sum())
    for i, tm in enumerate(rem):
        team_rank[int(tm)] = i + 1
    k_end = int(np.searchsorted(times, end_t)) + 1
    pos_hist = pos_hist[:k_end]
    times = times[:k_end]

    # ---- ground truth from what actually happened ----
    def span(members: list[int], center, radius, t_lo=0.0, t_hi=np.inf, min_present=8):
        ok = []
        for k2, t2 in enumerate(times):
            if not (t_lo <= t2 <= t_hi):
                ok.append(False)
                continue
            P = pos_hist[k2, members]
            good = ~np.isnan(P[:, 0])
            d = np.linalg.norm(P[good] - np.array(center), axis=1)
            ok.append(int((d <= radius).sum()) >= min_present)
        best, cur, s0 = (None, MIN_GT_STEPS - 1), 0, 0
        for k2, v in enumerate(ok + [False]):
            if v:
                if cur == 0:
                    s0 = k2
                cur += 1
            else:
                if cur > best[1]:
                    best = ((s0, k2 - 1), cur)
                cur = 0
        return best[0]

    out_gt = []
    for g in gt:
        t_land = float(np.median([squads[s - 1].land_t for s in g["squads"]]))
        sp = span(g["_members"], g["center"], g["radius"], t_lo=t_land, t_hi=700)
        if sp:
            out_gt.append(dict({k2: v for k2, v in g.items() if k2 != "_members"},
                               t_start=float(times[sp[0]]), t_end=float(times[sp[1]]),
                               members=[accounts[i] for i in g["_members"]]))
    if camp_squads:
        mem = [m for tid in camp_squads for m in squads[tid - 1].members]
        sp = span(mem, camp["point"], 250, t_lo=camp["t0"], min_present=8)
        if sp:
            out_gt.append(dict(kind="bridge_camp", place=camp["bridge"]["name"], center=list(camp["point"]),
                               radius=250, squads=camp_squads, t_start=float(times[sp[0]]),
                               t_end=float(times[sp[1]]), members=[accounts[i] for i in mem]))
    zfin = zones[-3]  # radius 220 m circle onwards
    fin_alive = [i for i in range(n) if death_t[i] > zfin[2]]
    if len(fin_alive) >= 8:
        sp = span(fin_alive, (zones[-1][3], zones[-1][4]), 350, t_lo=zfin[2], min_present=8)
        if sp:
            out_gt.append(dict(kind="final_circle", place="final circle", center=[zones[-1][3], zones[-1][4]],
                               radius=350, squads=sorted({int(team_of[i]) for i in fin_alive}),
                               t_start=float(times[sp[0]]), t_end=float(times[sp[1]]),
                               members=[accounts[i] for i in fin_alive]))

    # ---- telemetry events ----
    def char(i: int, x: float, y: float, z: float, health: float = 100.0, blue=False) -> dict:
        return {"name": names[i], "teamId": int(team_of[i]), "health": round(health, 1),
                "location": {"x": round(x * 100, 2), "y": round(y * 100, 2), "z": round(z * 100, 2)},
                "ranking": 0, "accountId": accounts[i], "isInBlueZone": bool(blue), "isInRedZone": False,
                "zone": []}

    ev: list[dict] = []
    ev.append({"_D": _iso(base, 0), "_T": "LogMatchStart", "mapName": meta["mapName"], "weatherId": "Clear_02",
               "teamSize": squad_size, "isCustomGame": False, "isEventMode": False,
               "characters": [{"character": char(i, *pos_hist[0, i], 1500.0), "primaryWeaponFirst": "",
                               "primaryWeaponSecond": "", "secondaryWeapon": "", "spawnKitIndex": 0}
                              for i in range(n)]})
    landed_ev = set()
    vid = {}
    for k2, t2 in enumerate(times):
        safe, warn, _ = zone_at(t2)
        n_alive = int((death_t > t2).sum())
        n_teams = len({int(team_of[i]) for i in range(n) if death_t[i] > t2})
        ev.append({"_D": _iso(base, t2 + 0.5), "_T": "LogGameStatePeriodic", "gameState": {
            "elapsedTime": int(t2), "numAliveTeams": n_teams, "numJoinPlayers": n, "numStartPlayers": n,
            "numAlivePlayers": n_alive,
            "safetyZonePosition": {"x": safe[0] * 100, "y": safe[1] * 100, "z": 0}, "safetyZoneRadius": safe[2] * 100,
            "poisonGasWarningPosition": {"x": warn[0] * 100, "y": warn[1] * 100, "z": 0},
            "poisonGasWarningRadius": warn[2] * 100,
            "redZonePosition": {"x": 0, "y": 0, "z": 0}, "redZoneRadius": 0, "blackZonePosition": {"x": 0, "y": 0, "z": 0},
            "blackZoneRadius": 0}})
        for i in range(n):
            x, y = pos_hist[k2, i]
            if np.isnan(x):
                continue
            sq = squads[team_of[i] - 1]
            if i not in landed_ev and t2 >= sq.land_t:
                landed_ev.add(i)
                ev.append({"_D": _iso(base, sq.land_t + rng.uniform(0, 2)), "_T": "LogParachuteLanding",
                           "character": char(i, x, y, z_ground[i]), "distance": 0.0})
            if rng.uniform() < DROP_SAMPLE:
                continue
            if t2 < sq.jump_t:
                z = 1500.0
            elif t2 < sq.land_t:
                z = 1500.0 - (1500.0 - z_ground[i]) * (t2 - sq.jump_t) / (sq.land_t - sq.jump_t)
            else:
                z = z_ground[i] + rng.normal(0, 0.5)
            veh = None
            if in_car[i] and k2 > 0 and not np.isnan(pos_hist[k2 - 1, i, 0]) and \
                    np.linalg.norm(pos_hist[k2, i] - pos_hist[k2 - 1, i]) > 80:
                vid.setdefault(int(team_of[i]), f"vehicle_{_hex(rng, 8)}")
                veh = {"vehicleType": "WheeledVehicle", "vehicleId": "Uaz_A_01_C", "vehicleUniqueId": vid[int(team_of[i])],
                       "healthPercent": 90.0, "feulPercent": 70.0}
            blue = math.dist((x, y), safe[:2]) > safe[2]
            jt = t2 + rng.uniform(-1.5, 1.5) if t2 > 0 else 0.0
            ev.append({"_D": _iso(base, jt), "_T": "LogPlayerPosition",
                       "character": char(i, x, y, z, rng.uniform(40, 100), blue), "vehicle": veh,
                       "elapsedTime": round(jt, 1), "numAlivePlayers": n_alive})
    for kl in kills:
        v, kk = kl["victim"], kl["killer"]
        kv = int(np.searchsorted(times, kl["t"]) - 1)
        kv = max(kv, 0)
        vx, vy = pos_hist[kv, v] if not np.isnan(pos_hist[kv, v, 0]) else pos_hist[max(kv - 1, 0), v]
        kc = None
        if kk is not None:
            kp = pos_hist[kv, kk] if not np.isnan(pos_hist[kv, kk, 0]) else pos_hist[max(kv - 1, 0), kk]
            kc = char(kk, *kp, z_ground[kk])
        ev.append({"_D": _iso(base, kl["t"]), "_T": "LogPlayerKillV2", "attackId": int(rng.integers(1e9)),
                   "victim": char(v, vx, vy, z_ground[v], 0.0), "killer": kc, "finisher": kc,
                   "dBNOMaker": kc, "killerDamageInfo": {
                       "damageTypeCategory": "Damage_Gun" if kc else "Damage_BlueZone",
                       "damageCauserName": "WeapM416_C" if kc else "BluezoneBomb_EffectActor_C",
                       "distance": float(np.linalg.norm(np.array(kc["location"]["x"]) - vx * 100)) if kc else 0.0},
                   "isSuicide": False})
    end_chars = []
    for i in range(n):
        x, y = pos_hist[-1, i] if not np.isnan(pos_hist[-1, i, 0]) else (0.0, 0.0)
        c = char(i, x, y, 0.0)
        c["ranking"] = team_rank.get(int(team_of[i]), 1)
        end_chars.append({"character": c, "primaryWeaponFirst": "", "primaryWeaponSecond": "",
                          "secondaryWeapon": "", "spawnKitIndex": 0})
    ev.append({"_D": _iso(base, end_t + 3), "_T": "LogMatchEnd", "characters": end_chars,
               "gameResultOnFinished": {"results": []}})
    ev.sort(key=lambda e: e["_D"])

    match = build_match_doc(meta, team_of, accounts, names, team_rank, death_t, kills, int(end_t + 3))
    gt_doc = dict(match_id=match_id, source="mock", seed=seed, index=index, gatherings=out_gt,
                  note="Scripted gatherings; spans measured from simulated positions. Never read by mining.")
    return match, ev, gt_doc


def build_match_doc(meta: dict, team_of, accounts, names, team_rank, death_t, kills, duration: int) -> dict:
    mid = meta["id"]
    h = lambda s: hashlib.md5(f"{mid}{s}".encode()).hexdigest()  # noqa: E731
    kc = {}
    for kl in kills:
        if kl["killer"] is not None:
            kc[kl["killer"]] = kc.get(kl["killer"], 0) + 1
    parts, rosters = [], []
    for i in range(len(accounts)):
        parts.append({"type": "participant", "id": h(f"p{i}"), "attributes": {"actor": "", "shardId": "steam", "stats": {
            "name": names[i], "playerId": accounts[i], "winPlace": team_rank.get(int(team_of[i]), 1),
            "kills": kc.get(i, 0), "timeSurvived": float(min(death_t[i], duration)), "DBNOs": 0, "damageDealt": 0.0,
            "deathType": "alive" if np.isinf(death_t[i]) else "byplayer"}}})
    for tm in sorted(set(int(x) for x in team_of)):
        mem = [i for i in range(len(accounts)) if team_of[i] == tm]
        rosters.append({"type": "roster", "id": h(f"r{tm}"), "attributes": {
            "shardId": "steam", "won": "true" if team_rank.get(tm) == 1 else "false",
            "stats": {"rank": team_rank.get(tm, 1), "teamId": tm}},
            "relationships": {"participants": {"data": [{"type": "participant", "id": h(f"p{i}")} for i in mem]},
                              "team": {"data": None}}})
    asset = {"type": "asset", "id": h("asset"), "attributes": {
        "name": "telemetry", "description": "", "createdAt": meta["createdAt"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "URL": f"mock://telemetry/{mid}.json"}}
    return {"data": {"type": "match", "id": mid, "attributes": {
        "createdAt": meta["createdAt"].strftime("%Y-%m-%dT%H:%M:%SZ"), "duration": duration,
        "gameMode": meta["gameMode"], "mapName": meta["mapName"], "matchType": meta["matchType"],
        "isCustomMatch": False, "seasonState": "progress", "shardId": "steam", "titleId": "bluehole-pubg",
        "stats": None, "tags": None},
        "relationships": {"rosters": {"data": [{"type": "roster", "id": r["id"]} for r in rosters]},
                          "assets": {"data": [{"type": "asset", "id": asset["id"]}]}}},
        "included": parts + rosters + [asset], "links": {"self": f"mock://matches/{mid}"}, "meta": {}}
