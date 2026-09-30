#!/usr/bin/env python3
"""kappa.py -- inter-rater agreement for the survey (reviewer M6).

Run only after BOTH rater columns of sheet_callsites.csv are filled in
independently (see CODEBOOK.md). Reports:
  * Cohen's kappa between rater_1 and rater_2 (independent labels, before
    resolution), with raw agreement and the confusion table;
  * agreement of each rater, and of the resolved label, with the automatic
    classifier (survey/data/callsites.csv 'bucket'), mapping the classifier's
    'unknown' to the raters' 'unresolvable';
  * for sheet_adjudicated.csv, agreement of rater_2 with the first
    adjudicator's verdict (genuine = keyobject).
Refuses to run while any rater cell is empty.
"""
import csv, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / 'data'
# --sheets DIR reads the two rating sheets from DIR instead (used for the
# dry run on dummy ratings: make_dummy_ratings.py).
if '--sheets' in sys.argv:
    HERE = Path(sys.argv[sys.argv.index('--sheets') + 1]).resolve()


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0, po


rows = list(csv.DictReader((HERE / 'sheet_callsites.csv').open()))
empty = [r['id'] for r in rows if not r['rater_1'].strip() or not r['rater_2'].strip()]
if empty:
    sys.exit(f'{len(empty)} rows still unrated (e.g. {", ".join(empty[:5])}); rate all rows first.')
a = [r['rater_1'].strip() for r in rows]
b = [r['rater_2'].strip() for r in rows]
k, po = kappa(a, b)
print(f'call sites: n={len(rows)}  raw agreement={po:.3f}  Cohen kappa={k:.3f}')
labels = sorted(set(a) | set(b))
print('confusion (rows rater_1, columns rater_2):')
print('  ' + ' '.join(f'{l[:10]:>10}' for l in labels))
for x in labels:
    print(f'{x[:10]:>10} ' + ' '.join(f'{sum(1 for p, q in zip(a, b) if p == x and q == y):>10}' for y in labels))

auto = {}
for i, r in enumerate(csv.DictReader((DATA / 'callsites.csv').open())):
    auto[f'C{i + 1:03d}'] = 'unresolvable' if r['bucket'] == 'unknown' else r['bucket']
c = [auto[r['id']] for r in rows]
for name, lab in (('rater_1', a), ('rater_2', b)):
    kk, pp = kappa(lab, c)
    print(f'{name} vs classifier: agreement={pp:.3f} kappa={kk:.3f}')
res = [r['resolved'].strip() or r['rater_1'].strip() for r in rows]
kk, pp = kappa(res, c)
print(f'resolved vs classifier: agreement={pp:.3f} kappa={kk:.3f}')
print(f'resolved keyobject count: {sum(1 for x in res if x == "keyobject")} of {len(rows)}')

adj_sheet = list(csv.DictReader((HERE / 'sheet_adjudicated.csv').open()))
if all(r['rater_2'].strip() for r in adj_sheet):
    first = [r['verdict'] for r in csv.DictReader((DATA / 'hand_adjudication.csv').open())
             if r['round'].startswith('counter_search')]
    first = ['keyobject' if v == 'genuine' else ('unresolvable' if v == 'unresolved' else 'not_keyobject') for v in first]
    second = [('keyobject' if r['rater_2'].strip() == 'keyobject' else
               'unresolvable' if r['rater_2'].strip() == 'unresolvable' else 'not_keyobject') for r in adj_sheet]
    kk, pp = kappa(first, second)
    print(f'counter-search adjudication: n={len(first)} agreement={pp:.3f} kappa={kk:.3f}')
else:
    print('sheet_adjudicated.csv not yet rated; skipped.')
