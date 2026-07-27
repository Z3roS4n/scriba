#!/usr/bin/env node
/**
 * Crea la cartella .claude/project/design/ (design system, decisioni, gap
 * funzionali) e .claude/project/roadmap-frontend.md per un redesign/nuovo
 * design UI. Idempotente: NON sovrascrive file esistenti senza --force.
 *
 * Uso:
 *   node new-design-setup.mjs [--name "Nome Progetto"] [--dir .] [--force]
 */

import { mkdir, writeFile, access, readFile } from "node:fs/promises";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TPL = resolve(__dirname, "..", "assets");

const args = process.argv.slice(2);
function flag(name, def = undefined) {
  const i = args.indexOf(`--${name}`);
  if (i === -1) return def;
  const v = args[i + 1];
  return v && !v.startsWith("--") ? v : true;
}
const FORCE = args.includes("--force");
const ROOT = resolve(process.cwd(), String(flag("dir", ".")));
const NAME = flag("name", ROOT.split(/[\\/]/).filter(Boolean).pop() || "Project");
const TODAY = new Date().toISOString().slice(0, 10);
const vars = { NAME, TODAY };

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

async function main() {
  console.log(`\n🎨 design-setup → ${NAME}`);
  console.log(`   dir: ${ROOT}\n`);

  await putTemplate("design-readme-template.md", ".claude/project/design/README.md");
  await putTemplate("design-system-template.md", ".claude/project/design/design-system.md");
  await putTemplate("design-decisions-template.md", ".claude/project/design/decisions.md");
  await putTemplate("design-da-implementare-template.md", ".claude/project/design/da-implementare.md");
  await putTemplate("roadmap-frontend-template.md", ".claude/project/roadmap-frontend.md");

  console.log(`\n✅ Fatto — ${created} creati, ${skipped} saltati.`);
  if (skipped && !FORCE) {
    console.log(`   (usa --force per sovrascrivere i file esistenti)`);
  }
  console.log(`\nProssimi passi:`);
  console.log(`  1. Compila design-system.md con palette/tipografia/icone/pattern reali del design ricevuto.`);
  console.log(`  2. Registra scope e processo in decisions.md (D-UI-01, D-UI-02, ...).`);
  console.log(`  3. Procedi sezione per sezione: aggiorna roadmap-frontend.md e segna i gap in da-implementare.md.\n`);
}

main().catch((e) => { console.error("❌", e); process.exit(1); });
