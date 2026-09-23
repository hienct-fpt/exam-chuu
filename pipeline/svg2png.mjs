// svgz/svg -> png with @resvg/resvg-js (PyMuPDF ignores the clip paths in min-san SVGs).
// usage: node pipeline/svg2png.mjs <srcDir> <dstDir> [zoom=2.5]
// Dependency lives in web/node_modules (devDependency @resvg/resvg-js).
import { createRequire } from 'node:module';
import { readdirSync, readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join, basename } from 'node:path';
import { gunzipSync } from 'node:zlib';

const require = createRequire(new URL('../web/package.json', import.meta.url));
const { Resvg } = require('@resvg/resvg-js');

const [srcDir, dstDir, zoomArg] = process.argv.slice(2);
const zoom = Number(zoomArg || 2.5);
if (!srcDir || !dstDir) { console.error('usage: node svg2png.mjs <srcDir> <dstDir> [zoom]'); process.exit(2); }
mkdirSync(dstDir, { recursive: true });

const files = readdirSync(srcDir).filter((f) => /\.svgz?$/.test(f));
let done = 0, skipped = 0, failed = 0;
for (const f of files) {
  const out = join(dstDir, basename(f).replace(/\.svgz?$/, '.png'));
  if (existsSync(out)) { skipped++; continue; }
  try {
    let buf = readFileSync(join(srcDir, f));
    if (buf[0] === 0x1f && buf[1] === 0x8b) buf = gunzipSync(buf);
    const r = new Resvg(buf, { fitTo: { mode: 'zoom', value: zoom }, background: 'white' });
    writeFileSync(out, r.render().asPng());
    done++;
    if (done % 100 === 0) console.log(`  png ${done}/${files.length - skipped}`);
  } catch (e) {
    failed++;
    console.error(`  FAIL ${f}: ${e.message}`);
  }
}
console.log(`[svg2png] ${done} rendered, ${skipped} existed, ${failed} failed -> ${dstDir}`);
