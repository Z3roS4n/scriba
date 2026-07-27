#!/usr/bin/env node
/**
 * Crea una nota di ricerca in .claude/project/research/
 * Naming: {YYYY-MM-DD}.{slug}.md
 *
 * Uso: node new-research.mjs "argomento ricerca"
 */
import { mkdir, writeFile, access } from "node:fs/promises";
import { join, resolve } from "node:path";

const raw = process.argv.slice(2).join(" ").trim();
if (!raw) { console.error('Uso: new-research.mjs "argomento"'); process.exit(1); }

const slug = raw.toLowerCase()
  .replace(/[àáâä]/g, "a").replace(/[èéêë]/g, "e").replace(/[ìíîï]/g, "i")
  .replace(/[òóôö]/g, "o").replace(/[ùúûü]/g, "u")
  .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

const d = new Date();
const p = (n) => String(n).padStart(2, "0");
const date = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;

const dir = resolve(process.cwd(), ".claude/project/research");
const file = join(dir, `${date}.${slug}.md`);

const body = `# Ricerca — ${raw}

**Data:** ${date}

## Domanda / obiettivo
<cosa si vuole capire e perché>

## Fonti
- <link / doc ufficiale / SDK version>

## Sintesi
<risposta breve e operativa>

## Dettagli
<dati, shape API, vincoli, costi>

## Implicazioni per il progetto
- <decisioni che ne derivano; collega a 02-tradeoffs.md se apri una decisione>

## Aperti / da verificare
- <TODO>
`;

async function exists(f) { try { await access(f); return true; } catch { return false; } }
await mkdir(dir, { recursive: true });
if (await exists(file)) { console.error("Esiste già:", file); process.exit(1); }
await writeFile(file, body, "utf8");
console.log(file);
