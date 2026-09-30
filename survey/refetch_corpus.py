#!/usr/bin/env python3
"""refetch_corpus.py -- rebuild the survey corpus from its manifest (reviewer minor 16).

The third-party source files the survey examined are not redistributed.
survey/data/corpus_manifest.csv pins each one by repository, path, git blob
SHA-1 and SHA-256. This script re-fetches every file from GitHub at the
repository HEAD commit recorded in the manifest, hashes the bytes it receives,
and reports whether they are the bytes that were analysed.

  python3 survey/refetch_corpus.py [--out survey/data/files_refetched] [--limit N]

Writes <out>/<repo>/<path> for every file whose SHA-256 matches, and
<out>/refetch_report.csv with one row per manifest entry:
  match     fetched bytes have the manifest's SHA-256 (the authoritative pin)
  changed   fetched, but the bytes differ (the file changed at that commit
            path, or the recorded HEAD postdates the analysed version)
  missing   the repository, commit or path is no longer available

Only files that `match` reproduce the corpus exactly. The HEAD commit is a
weaker pin than the hash (see make_manifest.py); a `changed` file can still be
located by its git blob SHA-1 in the repository's history.
"""
from __future__ import annotations
import argparse, csv, hashlib, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'survey' / 'data' / 'corpus_manifest.csv'


def fetch(repo: str, commit: str, path: str) -> bytes | None:
    url = f'https://raw.githubusercontent.com/{repo}/{commit}/{urllib.request.quote(path)}'
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(ROOT / 'survey' / 'data' / 'files_refetched'))
    ap.add_argument('--limit', type=int, default=0, help='stop after N manifest rows (0 = all)')
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(MANIFEST.open()))
    if a.limit:
        rows = rows[:a.limit]
    report, counts = [], {'match': 0, 'changed': 0, 'missing': 0}
    for r in rows:
        commit = r['repo_head_commit_at_manifest_time'] or 'HEAD'
        data = fetch(r['repo'], commit, r['path'])
        if data is None:
            status = 'missing'
        else:
            status = 'match' if hashlib.sha256(data).hexdigest() == r['sha256'] else 'changed'
            if status == 'match':
                dst = out / r['repo'] / r['path']
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
        counts[status] += 1
        report.append({'corpus': r['corpus'], 'repo': r['repo'], 'path': r['path'],
                       'commit': commit, 'sha256_expected': r['sha256'], 'status': status})
        time.sleep(0.1)
    with (out / 'refetch_report.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(report[0]))
        w.writeheader()
        w.writerows(report)
    print(f'{len(rows)} manifest rows: ' + ', '.join(f'{k} {v}' for k, v in counts.items()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
