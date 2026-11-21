// Compila Tailwind CSS v4 -> sismoscan/static/css/app.css
// Uso normal (con Node): npm i -D tailwindcss && node tools/build_css.mjs
// Equivalente con la CLI oficial: npx @tailwindcss/cli -i sismoscan/static/css/input.css -o sismoscan/static/css/app.css --minify
import { readFileSync, writeFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const INPUT = join(ROOT, 'sismoscan/static/css/input.css');
const OUTPUT = join(ROOT, 'sismoscan/static/css/app.css');
const SCAN = ['sismoscan/templates', 'sismoscan/static/js'];

// Localiza el paquete tailwindcss (local, o la ruta indicada en TAILWIND_DIR)
const candidates = [process.env.TAILWIND_DIR, join(ROOT, 'node_modules/tailwindcss'), '/opt/npm-tools/node_modules/tailwindcss'].filter(Boolean);
const TW = candidates.find(p => existsSync(join(p, 'package.json')));
if (!TW) { console.error('No se encontró el paquete "tailwindcss". Ejecuta: npm i -D tailwindcss'); process.exit(1); }
const { compile } = await import(pathToFileURL(join(TW, 'dist/lib.mjs')).href);

function walk(dir, out = []) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f); const s = statSync(p);
    if (s.isDirectory()) walk(p, out); else if (/\.(html|js|jinja|svg)$/.test(f)) out.push(p);
  }
  return out;
}
const candidatesSet = new Set();
for (const d of SCAN) for (const f of walk(join(ROOT, d)))
  for (const t of readFileSync(f, 'utf8').split(/[\s"'`<>=(){};,]+/)) if (t) candidatesSet.add(t);

const css = readFileSync(INPUT, 'utf8');
const compiler = await compile(css, {
  base: dirname(INPUT),
  async loadStylesheet(id, base) {
    let p;
    if (id === 'tailwindcss') p = join(TW, 'index.css');
    else if (id.startsWith('tailwindcss/')) p = join(TW, id.slice('tailwindcss/'.length) + (id.endsWith('.css') ? '' : '.css'));
    else p = resolve(base, id);
    return { path: p, base: dirname(p), content: readFileSync(p, 'utf8') };
  },
});
let out = compiler.build([...candidatesSet]);
// minificación simple y segura (sin tocar contenido de cadenas largas)
out = out.replace(/\/\*[^*]*\*+([^/*][^*]*\*+)*\//g, '').replace(/\s*\n\s*/g, '\n').replace(/\n(?=[^{}]*[;,]\n)/g, ' ').replace(/\s{2,}/g, ' ');
writeFileSync(OUTPUT, out);
console.log(`app.css generado: ${(out.length / 1024).toFixed(1)} KB, ${candidatesSet.size} candidatos escaneados`);
