#!/usr/bin/env node
/**
 * msworks-project-setup — scaffolder .claude/
 *
 * Genera la struttura documentale `.claude/` (project + integrations)
 * secondo le convenzioni M's, con docs numerati, cartelle reports/ e
 * research/ datate, registro integrazioni e launch.json.
 *
 * Uso:
 *   node setup-claude.mjs [--name "Nome Progetto"] [--slug nome-progetto]
 *                         [--email you@example.com] [--force] [--dir .]
 *
 * Idempotente: NON sovrascrive file esistenti a meno di --force.
 */

import { mkdir, writeFile, access, readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TPL = resolve(__dirname, "..", "assets");

// ---------- args ----------
const args = process.argv.slice(2);
function flag(name, def = undefined) {
  const i = args.indexOf(`--${name}`);
  if (i === -1) return def;
  const v = args[i + 1];
  return v && !v.startsWith("--") ? v : true;
}
const FORCE = args.includes("--force");
// Stack React/Next è il default M's; genera 08-react-next-performance.md.
// Opt-out con --no-react per progetti di stack diverso.
const REACT = !args.includes("--no-react");
const ROOT = resolve(process.cwd(), String(flag("dir", ".")));

// ---------- helpers ----------
const slugify = (s) =>
  s.toLowerCase().trim()
    .replace(/[àáâä]/g, "a").replace(/[èéêë]/g, "e").replace(/[ìíîï]/g, "i")
    .replace(/[òóôö]/g, "o").replace(/[ùúûü]/g, "u")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

let NAME = flag("name");
let SLUG = flag("slug");
if (!NAME && SLUG) NAME = SLUG;
if (!NAME) {
  // fallback: nome cartella corrente
  NAME = ROOT.split(/[\\/]/).filter(Boolean).pop() || "Project";
}
if (!SLUG) SLUG = slugify(NAME);
const EMAIL = flag("email", "you@example.com");
const YEAR = new Date().getFullYear();
const TODAY = new Date().toISOString().slice(0, 10);

const vars = { NAME, SLUG, EMAIL, YEAR: String(YEAR), TODAY };

function render(str) {
  return str.replace(/\{\{(\w+)\}\}/g, (_, k) => (k in vars ? vars[k] : `{{${k}}}`));
}

async function exists(p) {
  try { await access(p); return true; } catch { return false; }
}

let created = 0, skipped = 0;
async function put(relPath, content) {
  const full = join(ROOT, relPath);
  await mkdir(dirname(full), { recursive: true });
  if ((await exists(full)) && !FORCE) {
    console.log(`  ~ skip   ${relPath} (esiste)`);
    skipped++;
    return;
  }
  await writeFile(full, content, "utf8");
  console.log(`  + write  ${relPath}`);
  created++;
}

async function putTemplate(tplName, relPath) {
  const raw = await readFile(join(TPL, tplName), "utf8");
  await put(relPath, render(raw));
}

// ---------- struttura ----------
async function main() {
  console.log(`\n📁 msworks-project-setup → ${NAME} (${SLUG})`);
  console.log(`   dir: ${ROOT}\n`);

  // .claude/project docs
  await putTemplate("project-README.md", ".claude/project/README.md");
  await putTemplate("01-architecture.md", ".claude/project/01-architecture.md");
  await putTemplate("02-tradeoffs.md", ".claude/project/02-tradeoffs.md");
  await putTemplate("03-stack.md", ".claude/project/03-stack.md");
  await putTemplate("04-data-model.md", ".claude/project/04-data-model.md");
  await putTemplate("05-api-endpoints.md", ".claude/project/05-api-endpoints.md");
  await putTemplate("06-code-style.md", ".claude/project/06-code-style.md");
  await putTemplate("07-bad-practices.md", ".claude/project/07-bad-practices.md");
  if (REACT) await putTemplate("08-react-next-performance.md", ".claude/project/08-react-next-performance.md");
  await putTemplate("09-roadmap.md", ".claude/project/09-roadmap.md");

  // gitkeep + guida per reports/ e research/
  await putTemplate("reports-README.md", ".claude/project/reports/README.md");
  await putTemplate("research-README.md", ".claude/project/research/README.md");

  // integrations
  await putTemplate("integrations-README.md", ".claude/integrations/README.md");
  await putTemplate("integration-template.md", ".claude/integrations/_template.md");

  // launch + agents + gitignore hint
  await putTemplate("launch.json", ".claude/launch.json");
  await putTemplate("AGENTS.md", "AGENTS.md");

  console.log(`\n✅ Fatto — ${created} creati, ${skipped} saltati.`);
  if (skipped && !FORCE) {
    console.log(`   (usa --force per sovrascrivere i file esistenti)`);
  }
  console.log(`\nProssimi passi:`);
  console.log(`  1. Compila .claude/project/01..09 con le decisioni reali del progetto.`);
  console.log(`  2. Genera un report:      /report <nome-task>`);
  console.log(`  3. Documenta un'integrazione: /integration <nome-servizio>`);
  console.log(`  4. Salva una ricerca:     /research <argomento>\n`);
}

main().catch((e) => { console.error("❌", e); process.exit(1); });
