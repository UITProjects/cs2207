"""Recheck the demo data: expected result with the defaults, and the same result when
eps or delta move by +-2 m (no distance sits close to a threshold)."""
import sys
from collections import Counter

from gathering_core import PER_STEP, T, run

sys.stdout.reconfigure(encoding='utf8')
ids = lambda a, b: [f'o{i}' for i in range(a, b + 1)]


def name(r, i):
    c = r['clusters'][i - 1]
    return f"c_t{c['t'] + 1}^{c['k']}"


def shape(r):
    return ([(c['t'], tuple(c['members'])) for c in r['clusters']], r['crowds'])


base = run()
for c in base['clusters']:
    print(f"{name(base, c['id'])}: {c['members']}")
for l in base['links']:
    if l['close']:
        print(f"d_H({name(base, l['a'])}, {name(base, l['b'])}) = {l['dH']:.2f}")
near = min(abs(l['dH'] - base['params']['delta']) for l in base['links'])
print(f'closest d_H to delta: {near:.2f} m away')
for cr, td in zip(base['crowds'], base['tads']):
    print([name(base, i) for i in cr], '-> gatherings', [[name(base, i) for i in g] for g in td['gatherings']])

assert len(base['rows']) == PER_STEP * T and set(Counter(t for _, t, _, _ in base['rows']).values()) == {PER_STEP}
# 3 touring crowds; each keeps the same k at every step: Cr = <c_ta^k, ..., c_tb^k>
spans = [(range(T), 1), (range(0, 4), 2), (range(5, T), 2)]   # A all evening, B early half, C late half
assert len(base['crowds']) == 3
for cr, (span, k) in zip(base['crowds'], spans):
    cs = [base['clusters'][i - 1] for i in cr]
    assert [c['t'] for c in cs] == list(span) and {c['k'] for c in cs} == {k}
A, B, C = base['tads']
assert A['gatherings'] == [base['crowds'][0]] and A['trace'][0]['par'] == ids(1, 8)       # o9 only 2 steps
assert B['gatherings'] == [base['crowds'][1][1:]] and B['trace'][0]['par'] == ids(10, 15)  # Divide cuts t1
assert C['gatherings'] == [] and C['trace'][0]['par'] == []
decoy = [c['id'] for c in base['clusters'] if c['members'] == ids(19, 23)]
assert len(decoy) == 2 and not any(i in cr for cr in base['crowds'] for i in decoy)        # 2 steps < k_c
assert any(cr == decoy for cr in run({'k_c': 2})['crowds'])

for key, vals in [('eps', [3.0, 7.0]), ('delta', [23.0, 27.0])]:
    for v in vals:
        assert shape(run({key: v})) == shape(base), f'{key} = {v} changes the result'
print('margins ok: same clusters and crowds for eps 3..7 and delta 23..27')
print('ALL CHECKS PASSED')
