/**
 * scan.js -- look for key material resolved by a failing parse used as a type
 * test (reviewer comment M1).
 *
 * For each in-frame package in data/frame_<name>.csv, download the published
 * tarball of the version recorded in the frame, parse every .js/.cjs/.mjs file
 * with acorn, and report each `try { ... } catch { ... }` where:
 *
 *   PARSE    the try block calls a key or certificate parser:
 *            createPublicKey | createPrivateKey | createSecretKey |
 *            X509Certificate | importKey | KeyObject.from
 *   FALLBACK the catch block (or code it reaches directly) calls a DIFFERENT
 *            key constructor or returns/assigns key material instead of
 *            rethrowing -- i.e. the failure selects another interpretation.
 *
 * Shape A ("asymmetric first") is the jsonwebtoken shape: createPublicKey or
 * createPrivateKey in the try, createSecretKey in the catch. Shape B is any
 * other parse-then-fallback on key material. Every hit is written with its
 * file, line and source excerpt so it can be read and adjudicated by hand;
 * the automated pass only nominates candidates.
 *
 *   node survey/libsurvey/scan.js --frame jwt
 *
 * Writes data/scan_<frame>.csv (one row per hit) and data/scan_<frame>_summary.json.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const zlib = require('node:zlib');
const crypto = require('node:crypto');
const acorn = require('acorn');
const walk = require('acorn-walk');

const frameArg = process.argv.indexOf('--frame');
const FRAME = frameArg > 0 ? process.argv[frameArg + 1] : 'jwt';
const HERE = __dirname;
const DATA = path.join(HERE, 'data');

const PARSERS = /^(createPublicKey|createPrivateKey|createSecretKey|X509Certificate|importKey|from)$/;
const ASYM = /^(createPublicKey|createPrivateKey)$/;
const KEYCTOR = /^(createPublicKey|createPrivateKey|createSecretKey|X509Certificate|importKey|from)$/;

function calleeName(node) {
  const c = node.callee || node;
  if (c.type === 'Identifier') return c.name;
  if (c.type === 'MemberExpression' && !c.computed && c.property.type === 'Identifier') {
    if (c.property.name === 'from' && !(c.object.type === 'Identifier' && c.object.name === 'KeyObject')) return null;
    return c.property.name;
  }
  return null;
}

function callsIn(node) {
  const names = [];
  walk.full(node, (n) => {
    if (n.type === 'CallExpression' || n.type === 'NewExpression') {
      const nm = calleeName(n);
      if (nm) names.push(nm);
    }
  });
  return names;
}

function rethrowsOnly(block) {
  if (!block || !block.body) return false;
  return block.body.length > 0 && block.body.every((s) => s.type === 'ThrowStatement');
}

// Minimal tar reader: enough for npm tarballs (ustar, regular files).
function untar(buf) {
  const files = [];
  let off = 0;
  while (off + 512 <= buf.length) {
    const hdr = buf.subarray(off, off + 512);
    if (hdr.every((b) => b === 0)) break;
    const name = hdr.subarray(0, 100).toString('utf8').replace(/\0.*$/s, '');
    const prefix = hdr.subarray(345, 500).toString('utf8').replace(/\0.*$/s, '');
    const size = parseInt(hdr.subarray(124, 136).toString('utf8').replace(/\0.*$/s, '').trim() || '0', 8);
    const type = String.fromCharCode(hdr[156] || 48);
    off += 512;
    if (type === '0' || type === '\0') files.push({ name: prefix ? `${prefix}/${name}` : name, data: buf.subarray(off, off + size) });
    off += Math.ceil(size / 512) * 512;
  }
  return files;
}

async function tarball(name, version) {
  const meta = await (await fetch(`https://registry.npmjs.org/${name.replace('/', '%2f')}/${version}`)).json();
  const url = meta.dist && meta.dist.tarball;
  if (!url) throw new Error('no tarball');
  const buf = Buffer.from(await (await fetch(url)).arrayBuffer());
  return { url, sha512: meta.dist.integrity || null, sha256: crypto.createHash('sha256').update(buf).digest('hex'),
           files: untar(zlib.gunzipSync(buf)) };
}

function scanSource(src) {
  let ast = null;
  for (const sourceType of ['module', 'script']) {
    try { ast = acorn.parse(src, { ecmaVersion: 'latest', sourceType, locations: true, allowHashBang: true,
                                   allowReturnOutsideFunction: true, allowAwaitOutsideFunction: true }); break; }
    catch (_) { /* try the other source type */ }
  }
  if (!ast) return { parsed: false, hits: [] };
  const hits = [];
  walk.full(ast, (n) => {
    if (n.type !== 'TryStatement' || !n.handler) return;
    const tryCalls = callsIn(n.block).filter((c) => PARSERS.test(c));
    if (tryCalls.length === 0) return;
    if (rethrowsOnly(n.handler.body)) return;
    const catchCalls = callsIn(n.handler.body).filter((c) => KEYCTOR.test(c));
    const fallsBackToOtherCtor = catchCalls.some((c) => !tryCalls.includes(c));
    if (!fallsBackToOtherCtor) return;
    const shapeA = tryCalls.some((c) => ASYM.test(c)) && catchCalls.includes('createSecretKey');
    hits.push({ line: n.loc.start.line, shape: shapeA ? 'A' : 'B', try_calls: [...new Set(tryCalls)].join(' '),
                catch_calls: [...new Set(catchCalls)].join(' '),
                excerpt: src.slice(n.start, Math.min(n.end, n.start + 400)).replace(/\s+/g, ' ') });
  });
  return { parsed: true, hits };
}

(async () => {
  const frame = fs.readFileSync(path.join(DATA, `frame_${FRAME}.csv`), 'utf8').trim().split('\n').slice(1)
    .map((l) => { const [name, version, weekly, inFrame] = l.split(','); return { name, version, weekly: Number(weekly), inFrame: inFrame === 'True' }; })
    .filter((r) => r.inFrame);
  const out = ['package,version,weekly_downloads,file,line,shape,try_calls,catch_calls,excerpt'];
  const perPkg = [];
  let jsFiles = 0, unparsed = 0;
  for (const p of frame) {
    let t;
    try { t = await tarball(p.name, p.version); }
    catch (e) { perPkg.push({ package: p.name, version: p.version, error: String(e.message) }); continue; }
    let pkgHits = 0, pkgFiles = 0;
    for (const f of t.files) {
      if (!/\.(c|m)?js$/.test(f.name) || /\.min\.js$/.test(f.name) || /(^|\/)(test|tests|__tests__|spec)\//.test(f.name)) continue;
      pkgFiles += 1; jsFiles += 1;
      const r = scanSource(f.data.toString('utf8'));
      if (!r.parsed) { unparsed += 1; continue; }
      for (const h of r.hits) {
        pkgHits += 1;
        const q = (s) => `"${String(s).replace(/"/g, '""')}"`;
        out.push([p.name, p.version, p.weekly, q(f.name.replace(/^package\//, '')), h.line, h.shape, q(h.try_calls), q(h.catch_calls), q(h.excerpt)].join(','));
      }
    }
    perPkg.push({ package: p.name, version: p.version, weekly_downloads: p.weekly, js_files: pkgFiles, hits: pkgHits, tarball_sha256: t.sha256 });
  }
  fs.writeFileSync(path.join(DATA, `scan_${FRAME}.csv`), out.join('\n') + '\n');
  const summary = {
    frame: FRAME, scanned_at_utc: new Date().toISOString(), node: process.version,
    packages_in_frame: frame.length, packages_scanned: perPkg.filter((p) => !p.error).length,
    packages_failed: perPkg.filter((p) => p.error).length, js_files: jsFiles, js_files_unparsed: unparsed,
    packages_with_shape_A: new Set(out.slice(1).filter((l) => l.split(',')[5] === 'A').map((l) => l.split(',')[0])).size,
    packages_with_any_hit: perPkg.filter((p) => p.hits > 0).length,
    per_package: perPkg,
  };
  fs.writeFileSync(path.join(DATA, `scan_${FRAME}_summary.json`), JSON.stringify(summary, null, 2) + '\n');
  const { per_package, ...brief } = summary;
  console.log(JSON.stringify(brief, null, 2));
})();
