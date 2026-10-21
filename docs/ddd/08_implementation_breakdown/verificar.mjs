// Verifica docs/ddd/08_implementation_breakdown contra docs/ddd/07_user_stories.
// Uso: node verificar.mjs <ruta-repo> [--json salida.json]
import fs from "node:fs";
import path from "node:path";

const repo = process.argv[2] ?? "C:/Users/PC/Proyectos/Apex";
const jsonOut = process.argv.indexOf("--json") > 0 ? process.argv[process.argv.indexOf("--json") + 1] : null;
const US = path.join(repo, "docs/ddd/07_user_stories");
const BD = path.join(repo, "docs/ddd/08_implementation_breakdown");
const STATES = ["READY", "NEEDS_REFINEMENT", "ARCHITECTURAL_GAP_DETECTED"];
const errors = [];
const stories = [];
const epics = [];
const endpoints = new Map();
const archTests = new Map();

const epicDirs = fs.readdirSync(US).filter((d) => /^EP-\d\d-/.test(d)).sort();
for (const ep of epicDirs) {
  const num = Number(ep.slice(3, 5));
  const v01 = num <= 13;
  const files = fs.readdirSync(path.join(US, ep)).filter((f) => /^US-\d{3}-.*\.md$/.test(f)).sort();
  const epic = { epic: ep, v01, stories: files.length, hours: 0, states: {} };
  if (v01) {
    for (const f of files) {
      const id = f.slice(0, 6);
      const p = path.join(BD, ep, f);
      if (!fs.existsSync(p)) { errors.push(`FALTA archivo ${ep}/${f}`); continue; }
      const t = fs.readFileSync(p, "utf8");
      const sec = t.split(/^## Estado de preparación\s*$/m)[1];
      const m = sec && sec.match(/^\*\*(READY|NEEDS_REFINEMENT|ARCHITECTURAL_GAP_DETECTED)\*\*\s*$/m);
      if (!m) errors.push(`SIN estado válido ${ep}/${f}`);
      if (!/^## Definición de hecho\s*$/m.test(t)) errors.push(`SIN Definición de hecho ${ep}/${f}`);
      const tot = t.match(/^\s*-?\s*\*\*Total: (\d+) h\*\*\s*$/m);
      if (!tot) errors.push(`SIN Total ${ep}/${f}`);
      if (/^\s*\|.*\|\s*$/m.test(t)) errors.push(`TIENE tabla ${ep}/${f}`);
      for (const req of ["## Tareas", "## Orden de ejecución", "## Dependencias técnicas", "## Riesgos", "## Estimación", "## Endpoints"]) {
        if (!t.includes(req)) errors.push(`SIN sección "${req}" ${ep}/${f}`);
      }
      const state = m ? m[1] : "?";
      const hours = tot ? Number(tot[1]) : 0;
      epic.hours += hours;
      epic.states[state] = (epic.states[state] ?? 0) + 1;
      // Endpoints
      const epSec = (t.split(/^## Endpoints\s*$/m)[1] ?? "").split(/^## /m)[0];
      for (const line of epSec.split(/\r?\n/)) {
        const e = line.match(/^- `(GET|POST|PATCH|PUT|DELETE) (\/[^`]+)` — roles?: (.+)$/);
        if (e) {
          const key = `${e[1]} ${e[2]}`;
          if (!endpoints.has(key)) endpoints.set(key, { roles: e[3].trim(), stories: [] });
          endpoints.get(key).stories.push(id);
        }
      }
      for (const a of t.matchAll(/tests\/architecture\/(test_[a-z0-9_]+\.py)/g)) {
        if (!archTests.has(a[1])) archTests.set(a[1], new Set());
        archTests.get(a[1]).add(id);
      }
      const title = (t.match(/^# (US-\d{3}) · (.+?) — desglose técnico/m) ?? [])[2] ?? "";
      const qsec = (t.split(/^## Preguntas abiertas\s*$/m)[1] ?? "").split(/^## /m)[0].trim();
      stories.push({ id, epic: ep, file: `${ep}/${f}`, title, state, hours, questions: state === "READY" ? "" : qsec });
    }
  } else {
    const p = path.join(BD, ep, "BREAKDOWN.md");
    if (!fs.existsSync(p)) { errors.push(`FALTA ${ep}/BREAKDOWN.md`); epics.push(epic); continue; }
    const t = fs.readFileSync(p, "utf8");
    if (/^\s*\|.*\|\s*$/m.test(t)) errors.push(`TIENE tabla ${ep}/BREAKDOWN.md`);
    const tot = t.match(/\*\*Total: (\d+) h\*\*/);
    if (!tot) errors.push(`SIN Total ${ep}/BREAKDOWN.md`);
    epic.hours = tot ? Number(tot[1]) : 0;
    for (const f of files) {
      const id = f.slice(0, 6);
      const re = new RegExp(`^- ${id} · (.+?) — \\*\\*(READY|NEEDS_REFINEMENT|ARCHITECTURAL_GAP_DETECTED)\\*\\* — (\\d+) h — (.*)$`, "m");
      const m = t.match(re);
      if (!m) { errors.push(`SIN línea de estado ${id} en ${ep}/BREAKDOWN.md`); continue; }
      epic.states[m[2]] = (epic.states[m[2]] ?? 0) + 1;
      stories.push({ id, epic: ep, file: `${ep}/BREAKDOWN.md`, title: m[1], state: m[2], hours: Number(m[3]), questions: m[2] === "READY" ? "" : m[4] });
    }
    const sum = stories.filter((s) => s.epic === ep).reduce((a, s) => a + s.hours, 0);
    if (tot && sum !== epic.hours) errors.push(`Total de ${ep} (${epic.hours}) distinto de la suma por historia (${sum})`);
  }
  epics.push(epic);
}

const count = (v) => {
  const c = {};
  for (const s of stories.filter((s) => (v === null ? true : (Number(s.epic.slice(3, 5)) <= 13) === v))) c[s.state] = (c[s.state] ?? 0) + 1;
  return c;
};
console.log("Historias v0.1 en 07:", epics.filter((e) => e.v01).reduce((a, e) => a + e.stories, 0));
console.log("Historias v0.2+ en 07:", epics.filter((e) => !e.v01).reduce((a, e) => a + e.stories, 0));
console.log("Estados v0.1:", JSON.stringify(count(true)));
console.log("Estados v0.2+:", JSON.stringify(count(false)));
for (const e of epics) console.log(`${e.epic}: ${e.stories} historias, ${e.hours} h, ${JSON.stringify(e.states)}`);
console.log("Horas v0.1:", epics.filter((e) => e.v01).reduce((a, e) => a + e.hours, 0));
console.log("Horas v0.2+:", epics.filter((e) => !e.v01).reduce((a, e) => a + e.hours, 0));
console.log("Endpoints v0.1 distintos:", endpoints.size);
console.log("Tests de arquitectura:", [...archTests.keys()].sort().join(", "));
if (errors.length) { console.log(`ERRORES (${errors.length}):`); for (const e of errors) console.log(" - " + e); }
else console.log("OK: sin errores");
if (jsonOut) {
  fs.writeFileSync(jsonOut, JSON.stringify({ epics, stories, endpoints: [...endpoints].map(([k, v]) => ({ endpoint: k, ...v })), archTests: [...archTests].map(([k, v]) => ({ test: k, stories: [...v].sort() })), errors }, null, 2));
}
process.exitCode = errors.length ? 1 : 0;
