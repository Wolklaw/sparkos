// search.js (the widget's copy of the launcher logic) against tests/vectors.json, the same
// cases tests/test_logic.py runs on launcher_logic.py. Plain Node, no Qt needed.
//   node tests/check_js.mjs
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, '../package/contents/code/search.js'), 'utf8')
  .replace(/^\.pragma library.*$/m, '');
const S = {};
vm.runInNewContext(src + '\n;globalThis.S={filterApps,sumFrom,sumCommand,showAnswer};', S);
const V = JSON.parse(readFileSync(join(here, 'vectors.json'), 'utf8'));
let bad = 0, n = 0;
function eq(got, want, what) {
  n++;
  if (JSON.stringify(got) !== JSON.stringify(want)) { bad++; console.log('MISMATCH', what, JSON.stringify(got), '!=', JSON.stringify(want)); }
}
for (const c of V.filter) eq(S.S.filterApps(V.apps, c.q, 8).map(a => a.name), c.names, 'filter ' + c.q);
eq(S.S.filterApps(V.apps, 's', 2).map(a => a.name), V.limit2, 'limit 2');
for (const c of V.sums) eq(S.S.sumFrom(c.text, false), c.sum, 'sum ' + c.text);
for (const c of V.sumsFr) eq(S.S.sumFrom(c.text, true), c.sum, 'sumFr ' + c.text);
for (const c of V.commands) eq(S.S.sumCommand(c.sum), c.cmd, 'cmd ' + c.sum);
for (const c of V.answers) eq(S.S.showAnswer(c.answer, c.fr), c.shown, 'answer ' + c.answer);
console.log(`${n - bad} of ${n} vectors match`);
process.exit(bad ? 1 : 0);
