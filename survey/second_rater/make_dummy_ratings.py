#!/usr/bin/env python3
"""make_dummy_ratings.py -- fill COPIES of the rating sheets with random labels
so kappa.py can be exercised end to end. The output is SYNTHETIC and must never
be reported; the real sheets in this directory are left untouched.

  python3 make_dummy_ratings.py --out /tmp/dummy_rating
  python3 kappa.py --sheets /tmp/dummy_rating
"""
import argparse, csv, random, shutil
from pathlib import Path
HERE = Path(__file__).resolve().parent
LABELS = ['keyobject', 'env_string', 'string_literal', 'file_contents', 'buffer', 'unresolvable']
ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--seed', type=int, default=1)
a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
rng = random.Random(a.seed)
rows = list(csv.DictReader((HERE / 'sheet_callsites.csv').open()))
for r in rows:
    r['rater_1'] = rng.choice(LABELS)
    r['rater_2'] = r['rater_1'] if rng.random() < 0.8 else rng.choice(LABELS)
    r['notes_1'] = r['notes_2'] = 'DUMMY'
with (out / 'sheet_callsites.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
adj = list(csv.DictReader((HERE / 'sheet_adjudicated.csv').open()))
for r in adj:
    r['rater_2'] = rng.choice(['keyobject', 'env_string', 'unresolvable']); r['notes_2'] = 'DUMMY'
with (out / 'sheet_adjudicated.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(adj[0])); w.writeheader(); w.writerows(adj)
print(f'dummy sheets written to {out} (SYNTHETIC)')
