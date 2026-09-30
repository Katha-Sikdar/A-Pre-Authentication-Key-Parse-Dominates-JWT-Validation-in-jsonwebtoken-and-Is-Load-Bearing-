#!/usr/bin/env python3
"""make_sheet.py -- blinded rating sheets for a second rater (reviewer M6).

Writes, with a fixed seed so the subset can be re-drawn:
  sheet_callsites.csv     a stratified random subset of the 327 classified call
                          sites: every call site in buckets smaller than 10, and
                          a random draw from each larger bucket, at least 100 rows
  sheet_adjudicated.csv   all call sites adjudicated by hand in the counter-search

The automatic bucket and the first adjudicator's verdict are NOT in the sheets.
They stay in survey/data/ and are joined back only by kappa.py.
"""
import csv, random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / 'data'
SEED = 20261001
TARGET = 110

manifest = {(r['repo'], r['path']): r['repo_head_commit_at_manifest_time']
            for r in csv.DictReader((DATA / 'corpus_manifest.csv').open())}
url = lambda repo, path: f"https://github.com/{repo}/blob/{manifest.get((repo, path)) or 'HEAD'}/{path}"

rows = list(csv.DictReader((DATA / 'callsites.csv').open()))
for i, r in enumerate(rows):
    r['id'] = f'C{i + 1:03d}'
by = defaultdict(list)
for r in rows:
    by[r['bucket']].append(r)
rng = random.Random(SEED)
small = [r for b, v in by.items() if len(v) < 10 for r in v]
large = {b: v for b, v in by.items() if len(v) >= 10}
remaining = TARGET - len(small)
total_large = sum(len(v) for v in large.values())
chosen = list(small)
for b, v in sorted(large.items()):
    k = max(1, round(remaining * len(v) / total_large))
    chosen += rng.sample(v, min(k, len(v)))
rng.shuffle(chosen)
with (HERE / 'sheet_callsites.csv').open('w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['id', 'repo', 'path', 'url', 'rater_1', 'notes_1', 'rater_2', 'notes_2', 'resolved', 'resolution_reason'])
    for r in chosen:
        w.writerow([r['id'], r['repo'], r['path'], url(r['repo'], r['path']), '', '', '', '', '', ''])

adj = [r for r in csv.DictReader((DATA / 'hand_adjudication.csv').open()) if r['round'].startswith('counter_search')]
with (HERE / 'sheet_adjudicated.csv').open('w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['id', 'repo', 'argument_at_call_site', 'rater_2', 'notes_2'])
    for i, r in enumerate(adj):
        w.writerow([f'A{i + 1:02d}', r['repo'], r['arg2_at_matched_callsite'], '', ''])
print(f'sheet_callsites.csv: {len(chosen)} rows (seed {SEED}); sheet_adjudicated.csv: {len(adj)} rows')
