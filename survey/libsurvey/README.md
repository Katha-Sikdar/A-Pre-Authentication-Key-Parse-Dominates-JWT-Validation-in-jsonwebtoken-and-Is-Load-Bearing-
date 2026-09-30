# Library survey (reviewer comment M1)

Does any popular npm package besides `jsonwebtoken` resolve key material by a
failing parse used as a type test?

1. `collect.py` draws the frame from the npm registry search API: the queries in
   `FRAMES`, the first 1,000 results per query, kept if the API's weekly
   download count is at or above the threshold. Output: `data/frame_<name>.csv`
   (every package returned, with `in_frame`) and `data/frame_<name>.json`
   (queries, threshold, capture time, counts).
2. `scan.js` downloads each in-frame package's published tarball at the version
   recorded in the frame, parses every `.js/.cjs/.mjs` file (tests and minified
   files excluded) with acorn, and flags each `try/catch` whose `try` calls a
   key or certificate parser and whose handler calls a different key
   constructor. Output: `data/scan_<name>.csv` (one row per hit, with excerpt)
   and `data/scan_<name>_summary.json` (with each tarball's SHA-256).
3. Every hit is read by hand and recorded in `data/adjudication_<name>.csv`.

Run on 2026-09-30:

    python3 collect.py --frame jwt    --min-weekly 50000
    python3 collect.py --frame crypto --min-weekly 500000
    npm ci && node scan.js --frame jwt && node scan.js --frame crypto

**Limits.** The detector finds only the syntactic shape above; a type test
written differently (for example, inspecting an error code, or a parser from a
third-party library such as node-forge) is not flagged, so a zero is a lower
bound within the frame. The search API's ranking is undocumented and returns at
most 1,000 results per query. The frame is npm only; see TODO_EXPERIMENTS.md
item 6 for other ecosystems.
