"""collect.py -- build the sampling frame for the library survey (reviewer M1).

Frame: every npm package returned by the registry search API for the queries
below whose weekly download count, as reported by that API on the capture
date, is at least --min-weekly. The queries, the threshold, the capture time
and the full result (including packages below the threshold) are written out,
so the frame can be re-drawn and audited.

  python3 survey/libsurvey/collect.py --frame jwt   --min-weekly 50000
  python3 survey/libsurvey/collect.py --frame crypto --min-weekly 500000

Writes survey/libsurvey/data/frame_<name>.csv and frame_<name>.json.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import time
import urllib.parse
import urllib.request

FRAMES = {
    # Libraries that verify or handle JSON Web Tokens / JOSE objects.
    'jwt': ['keywords:jwt', 'keywords:jsonwebtoken', 'keywords:jose',
            'keywords:jws', 'keywords:jwk', 'keywords:jwks'],
    # Wider: packages that handle keys or signatures in general.
    'crypto': ['keywords:crypto', 'keywords:cryptography', 'keywords:signature',
               'keywords:oauth', 'keywords:oidc', 'keywords:openid',
               'keywords:authentication', 'keywords:x509', 'keywords:pem'],
}
API = 'https://registry.npmjs.org/-/v1/search'
PAGE = 250
MAX_PER_QUERY = 1000


def search(q):
    out = []
    for start in range(0, MAX_PER_QUERY, PAGE):
        url = f"{API}?{urllib.parse.urlencode({'text': q, 'size': PAGE, 'from': start})}"
        with urllib.request.urlopen(url, timeout=60) as r:
            d = json.load(r)
        objs = d.get('objects', [])
        out.extend(objs)
        if len(objs) < PAGE:
            break
        time.sleep(0.5)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frame', choices=FRAMES, required=True)
    ap.add_argument('--min-weekly', type=int, required=True)
    a = ap.parse_args()
    here = pathlib.Path(__file__).resolve().parent
    (here / 'data').mkdir(exist_ok=True)
    captured = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    seen = {}
    for q in FRAMES[a.frame]:
        for o in search(q):
            p = o['package']
            name = p['name']
            wk = (o.get('downloads') or {}).get('weekly')
            rec = seen.setdefault(name, {'name': name, 'version': p.get('version'),
                                         'weekly_downloads': wk, 'queries': []})
            rec['queries'].append(q)
    rows = sorted(seen.values(), key=lambda r: -(r['weekly_downloads'] or 0))
    for r in rows:
        r['in_frame'] = (r['weekly_downloads'] or 0) >= a.min_weekly
        r['queries'] = ' '.join(r['queries'])
    meta = {'frame': a.frame, 'queries': FRAMES[a.frame], 'api': API,
            'min_weekly_downloads': a.min_weekly, 'captured_at_utc': captured,
            'packages_returned': len(rows), 'packages_in_frame': sum(r['in_frame'] for r in rows)}
    with open(here / 'data' / f'frame_{a.frame}.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['name', 'version', 'weekly_downloads', 'in_frame', 'queries'])
        w.writeheader()
        w.writerows(rows)
    (here / 'data' / f'frame_{a.frame}.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
