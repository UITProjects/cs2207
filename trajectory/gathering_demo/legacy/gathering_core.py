"""Gathering pattern on a fake concert dataset: data + pipeline, no Streamlit.

K. Zheng, Y. Zheng, N. J. Yuan, S. Shang, "On Discovery of Gathering Patterns from
Trajectories", ICDE 2013 (PDF in the Gathering folder).
  Def. 1  snapshot cluster: DBSCAN(eps, MinPts) on the positions at one timestamp.
  Def. 2  crowd: clusters at consecutive timestamps, lifetime >= k_c, every cluster
          >= m_c objects, Hausdorff d_H(c_ti, c_ti+1) <= delta. Closed = no super-crowd.
  Def. 3  participator: object in >= k_p clusters of the crowd (not necessarily consecutive).
  Def. 4  gathering: crowd whose every cluster has >= m_p participators.
  Alg. 1  closed crowds by a sweep over time (Lemma 1: closed iff no cluster can be appended).
  Alg. 2  Test-and-Divide (TAD): test the crowd, cut invalid clusters, recurse on parts
          >= k_c, participators recomputed on each part (Example 3). Bit vectors as in TAD*.
The demo runs brute force over the definitions (400 points), not the paper's grid/R-tree index.
The dataset is fake, generated with a fixed seed; check_core.py asserts the intended result.
"""
import functools
import math
import random

# ===== dataset =====
# A concert from 19:00 to 20:30: timestamps t1..t10, 10 minutes apart. Venue 100 x 80 m.
# 400 points, 40 per step. Three groups tour the venue along one route
# Cổng chính -> Trung tâm -> Khu ẩm thực -> Sân khấu -> Photo booth -> Cổng phụ:
# A does all of it, B only the stage half early, C only the gate half late. Three full tours at
# the same time cannot be kept apart: A sweeps the whole venue at ~19 m per step, so any other
# group present all evening comes within ~20 m of A at some pair of steps and Algorithm 1 would
# link them. Object ids come in blocks per group, ordered so each group keeps its rank k.
T = 10
STEP_MIN = 10
START = (19, 0)
VENUE = (100, 80)
PER_STEP = 40
ZONES = {  # name: (x0, y0, x1, y1)
    'Cổng chính': (0, 32, 4, 48),
    'Trung tâm': (40, 34, 56, 46),
    'Khu ẩm thực': (40, 4, 62, 14),
    'Sân khấu': (86, 20, 100, 52),
    'Photo booth': (86, 58, 100, 72),
    'Cổng phụ': (44, 76, 60, 80),
    'Quầy merch': (4, 0, 22, 8),
}
SEED = 2207


def _formation(rng, n):
    """n offsets in a small disc, at least 1.4 m apart, density-connected at eps = 2.4
    (room for the +-0.2 m wobble below, so the cluster still holds at eps = 3)."""
    R = 1.15 * math.sqrt(n)
    while True:
        pts = []
        while len(pts) < n:
            a, r = rng.uniform(0, 2 * math.pi), R * math.sqrt(rng.random())
            p = (r * math.cos(a), r * math.sin(a))
            if all(dist(p, q) >= 1.4 for q in pts):
                pts.append(p)
        cs = dbscan({f'o{i}': p for i, p in enumerate(pts)}, 2.4, 3)
        if len(cs) == 1 and len(cs[0]) == n:
            return pts


def _place(rng, pos, members, center, shape, t):
    for o, (dx, dy) in zip(members, shape):
        wx, wy = rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2)
        pos.setdefault(o, {})[t] = (round(center[0] + dx + wx, 2), round(center[1] + dy + wy, 2))


@functools.lru_cache(maxsize=1)
def make_dataset():
    """Return rows (oid, t, x, y) with t = 0..T-1, and a role per object."""
    rng = random.Random(SEED)
    pos, role = {}, {}
    ids = lambda a, b: [f'o{i}' for i in range(a, b + 1)]

    # A (o1-o9): 8 friends do the whole route t1-t10, about 19 m per step at most.
    # o9 walks with them at t1-t2 only, then goes off alone.
    shape = _formation(rng, 9)
    a_c = [(10, 40), (28, 40), (46, 40), (50, 22), (52, 20), (66, 28), (78, 42), (82, 60), (68, 70), (52, 75)]
    for t, c in enumerate(a_c):
        _place(rng, pos, ids(1, 8) + (['o9'] if t < 2 else []), c, shape, t)
    pos['o9'][2] = (30.0, 58.0)
    role.update({o: 'nhóm A' for o in ids(1, 9)})

    # B (o10-o18): the stage half early, t1-t4, then out through Cổng phụ. At t1 only o10, o11 of
    # the 6 friends are there, standing with 3 strangers (o16-o18); o12-o15 join at t2.
    shape = _formation(rng, 6)
    b_c = [(78, 40), (84, 58), (70, 70), (54, 75)]
    for t, c in enumerate(b_c):
        _place(rng, pos, ['o10', 'o11', 'o16', 'o17', 'o18'] if t == 0 else ids(10, 15), c, shape, t)
    role.update({o: 'nhóm B' for o in ids(10, 15)})
    role.update({o: 'người lạ' for o in ids(16, 18)})

    # Decoy (o19-o23): a queue at Quầy merch, t3-t4 only (2 steps < k_c).
    shape = _formation(rng, 5)
    for t in (2, 3):
        _place(rng, pos, ids(19, 23), (12, 12), shape, t)
    role.update({o: 'xếp hàng merch' for o in ids(19, 23)})

    # C (o24-o35): the gate half late, t6-t10: a flow of people on the walkway, 4 at every step,
    # 2 join and 2 turn off each step (nobody walks with it more than 2 steps).
    shape = _formation(rng, 4)
    c_c = [(10, 40), (22, 40), (34, 40), (46, 40), (50, 22)]
    for j, c in enumerate(c_c):
        _place(rng, pos, [f'o{24 + i}' for i in range(2 * j, 2 * j + 4)], c, shape, 5 + j)
    role.update({o: 'dòng người' for o in ids(24, 35)})

    # Walkers (o36+): a couple all evening, then people alone, until each step has PER_STEP points.
    # Every walker stays >= 8 m from everybody else at every step.
    W, H = VENUE
    need = [PER_STEP - sum(1 for ts in pos.values() if t in ts) for t in range(T)]
    nxt, first = 36, True
    while any(need):
        if first:
            span, group = list(range(T)), [f'o{nxt}', f'o{nxt + 1}']
        else:
            t0 = next(t for t in range(T) if need[t])
            span = [t for t in range(t0, min(T, t0 + rng.randint(2, 4))) if need[t]]
            span = span[:next((i for i in range(1, len(span)) if span[i] != span[i - 1] + 1), len(span))]
            group = [f'o{nxt}']
        for _ in range(20000):
            x, y = rng.uniform(5, W - 5), rng.uniform(5, H - 5)
            a, s = rng.uniform(0, 2 * math.pi), rng.uniform(4, 10)
            tr = {}
            for t in span:
                tr[t] = (round(x, 2), round(y, 2))
                x, y = x + s * math.cos(a), y + s * math.sin(a)
            trs = [tr] + [{t: (round(p[0] + 1.5, 2), round(p[1] + 0.6, 2)) for t, p in tr.items()}] * (len(group) - 1)
            if all(4 <= p[0] <= W - 4 and 4 <= p[1] <= H - 4 for tr_ in trs for p in tr_.values()) and all(
                    dist(p, ts[t]) >= 8 for tr_ in trs for t, p in tr_.items() for ts in pos.values() if t in ts):
                break
        else:
            raise RuntimeError(f'cannot place walker {group}')
        for o, tr_ in zip(group, trs):
            pos[o] = tr_
            role[o] = 'cặp đôi' if first else 'đi lẻ'
        for t in span:
            need[t] -= len(group)
        nxt += len(group)
        first = False

    rows = [(o, t, p[0], p[1]) for o in sorted(pos, key=lambda s: int(s[1:])) for t, p in sorted(pos[o].items())]
    return rows, role


DEFAULTS = dict(eps=5.0, min_pts=3, m_c=3, k_c=3, delta=25.0, k_p=3, m_p=3)


def time_label(t):
    m = START[0] * 60 + START[1] + t * STEP_MIN
    return f'{m // 60:02d}:{m % 60:02d}'


# ===== pipeline =====
def dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def dbscan(pts, eps, min_pts):
    """pts: {oid: (x, y)} -> list of clusters (sorted lists of oids). Noise is left out."""
    ids = list(pts)
    nb = {o: [q for q in ids if dist(pts[o], pts[q]) <= eps] for o in ids}  # includes o itself
    label, clusters = {}, []
    for o in ids:
        if o in label or len(nb[o]) < min_pts:
            continue
        cid = len(clusters)
        clusters.append([])
        queue = [o]
        while queue:
            p = queue.pop()
            if label.get(p) is not None:
                continue
            label[p] = cid
            clusters[cid].append(p)
            if len(nb[p]) >= min_pts:  # core point: expand
                queue.extend(q for q in nb[p] if label.get(q) is None)
    return [sorted(c, key=lambda s: int(s[1:])) for c in clusters]


def hausdorff(P, Q):
    d1 = max(min(dist(p, q) for q in Q) for p in P)
    d2 = max(min(dist(p, q) for p in P) for q in Q)
    return max(d1, d2)


def snapshot_clusters(rows, eps, min_pts):
    """Cluster c_t^k: k-th cluster at timestamp t, ordered by smallest member id (paper's Def. 2
    writes c_ti; the superscript k is ours, to tell apart clusters of the same timestamp)."""
    out = []
    for t in range(T):
        pts = {o: (x, y) for o, tt, x, y in rows if tt == t}
        cs = dbscan(pts, eps, min_pts)
        cs.sort(key=lambda c: int(c[0][1:]))
        for k, c in enumerate(cs, 1):
            P = [pts[o] for o in c]
            out.append(dict(t=t, k=k, members=c, pts=P,
                            centroid=(sum(p[0] for p in P) / len(P), sum(p[1] for p in P) / len(P))))
    for i, c in enumerate(out):
        c['id'] = i + 1
    return out


def discover_crowds(clusters, m_c, k_c, delta):
    """Algorithm 1 (closed crowds). Returns (crowds as lists of cluster ids, link table)."""
    by_t = [[c for c in clusters if c['t'] == t] for t in range(T)]
    links = []
    for t in range(T - 1):
        for a in by_t[t]:
            for b in by_t[t + 1]:
                d = hausdorff(a['pts'], b['pts'])
                links.append(dict(a=a['id'], b=b['id'], dH=d, close=d <= delta))
    near = {(l['a'], l['b']) for l in links if l['close']}

    closed, V = [], []
    for t in range(T):
        R, nxt = set(), []
        for cr in V:
            last = cr[-1]
            Cp = [c for c in by_t[t] if (last, c['id']) in near]   # RangeSearch(c_ti-1, C_ti, delta)
            R.update(c['id'] for c in Cp)
            ext = [c for c in Cp if len(c['members']) >= m_c]
            if not ext:                                             # cannot be extended
                if len(cr) >= k_c:
                    closed.append(cr)
            else:
                nxt.extend(cr + [c['id']] for c in ext)
        nxt.extend([c['id']] for c in by_t[t] if c['id'] not in R and len(c['members']) >= m_c)
        V = nxt
    closed.extend(cr for cr in V if len(cr) >= k_c)                 # end of data: flush
    closed.sort(key=lambda cr: cr[0])
    return closed, links


def tad(crowd, clusters, k_p, m_p, k_c):
    """Algorithm 2 on one crowd. Returns (trace, gatherings as lists of cluster ids)."""
    cid = {c['id']: c for c in clusters}
    n = len(crowd)
    objs = sorted({o for i in crowd for o in cid[i]['members']}, key=lambda s: int(s[1:]))
    B = {o: [1 if o in cid[i]['members'] else 0 for i in crowd] for o in objs}  # bit vector signature
    trace, out = [], []

    def run(mask, cand):
        par = [o for o in cand if sum(b & m for b, m in zip(B[o], mask)) >= k_p]
        counts = [sum(1 for o in cid[crowd[i]]['members'] if o in par) if mask[i] else None for i in range(n)]
        bad = [i for i in range(n) if counts[i] is not None and counts[i] < m_p]
        trace.append(dict(kind='test', mask=mask, cand=cand, par=par, counts=counts, bad=bad))
        if not bad:
            out.append([crowd[i] for i in range(n) if mask[i]])
            return
        parts, cur = [], None
        for i in range(n):
            if mask[i] and i not in bad:
                if cur is None:
                    cur = [0] * n
                    parts.append(cur)
                cur[i] = 1
            else:
                cur = None
        trace.append(dict(kind='divide', mask=mask, bad=bad,
                          parts=[dict(mask=p, tau=sum(p), ok=sum(p) >= k_c) for p in parts]))
        for p in parts:
            if sum(p) >= k_c:
                run(p, par)   # a non-participator of Cr stays one in every sub-crowd

    run([1] * n, objs)
    return dict(objs=objs, B=B, trace=trace, gatherings=out)


def run(params=None):
    p = dict(DEFAULTS, **(params or {}))
    rows, role = make_dataset()
    clusters = snapshot_clusters(rows, p['eps'], p['min_pts'])
    crowds, links = discover_crowds(clusters, p['m_c'], p['k_c'], p['delta'])
    tads = [tad(cr, clusters, p['k_p'], p['m_p'], p['k_c']) for cr in crowds]
    return dict(params=p, rows=rows, role=role, clusters=clusters, links=links, crowds=crowds, tads=tads)
