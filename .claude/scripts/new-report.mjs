#!/usr/bin/env node
/**
 * Crea un report datato in .claude/project/reports/
 * Naming: {YYYY-MM-DD-HH-mm}.report-{slug}.md
 *
 * Uso: node new-report.mjs "nome del task"
 */
import { mkdir, writeFile, access } from "node:fs/promises";
import { join, resolve } from "node:path";

const raw = process.argv.slice(2).join(" ").trim();
if (!raw) { console.error('Uso: new-report.mjs "nome task"'); process.exit(1); }

const slug = raw.toLowerCase()
  .replace(/[àáâä]/g, "a").replace(/[èéêë]/g, "e").replace(/[ìíîï]/g, "i")
  .replace(/[òóôö]/g, "o").replace(/[ùúûü]/g, "u")
  .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

const d = new Date();
const p = (n) => String(n).padStart(2, "0");
const stamp = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}-${p(d.getMinutes())}`;
const dateHuman = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;

const dir = resolve(process.cwd(), ".claude/project/reports");
const file = join(dir, `${stamp}.report-${slug}.md`);

const body = `# Report — ${raw}

**Data:** ${dateHuman}

## Cosa è stato fatto
- <descrivi le modifiche, file per file / componente per componente>

## File toccati
- \`path/to/file\` — <cosa e perché>

## Sicurezza / idempotenza
- <se applicabile: verifica firma, transizioni di stato atomiche, gating>

## Verifiche
- \`tsc\` · test <N/N> · \`lint\` · \`build\` — <esito>

## Rinviato (non buildabile / per design)
- <dipendenze esterne, scelte fuori scope>

## Prossimo
- <passo successivo pianificato>
`;

async function exists(f) { try { await access(f); return true; } catch { return false; } }
await mkdir(dir, { recursive: true });
if (await exists(file)) { console.error("Esiste già:", file); process.exit(1); }
await writeFile(file, body, "utf8");
console.log(file);
