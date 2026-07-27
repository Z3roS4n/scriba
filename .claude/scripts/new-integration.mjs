#!/usr/bin/env node
/**
 * Crea una scheda integrazione in .claude/integrations/{slug}.md
 * seguendo lo schema obbligatorio del registro.
 *
 * Uso: node new-integration.mjs "Nome Servizio"
 */
import { mkdir, writeFile, access } from "node:fs/promises";
import { join, resolve } from "node:path";

const raw = process.argv.slice(2).join(" ").trim();
if (!raw) { console.error('Uso: new-integration.mjs "Nome Servizio"'); process.exit(1); }

const slug = raw.toLowerCase()
  .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

const dir = resolve(process.cwd(), ".claude/integrations");
const file = join(dir, `${slug}.md`);

const ENV = raw.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_+|_+$/g, "");

const body = `# ${raw}

> <una riga: scopo dell'integrazione>. **Gated**: se \`${ENV}_API_KEY\` non è
> impostata, la funzione è disattivata e non influisce sul resto dell'app.

## Scopo
<cosa fa e perché serve>

## Base URL / SDK e versione
- SDK: \`<pkg@version>\` — oppure REST base URL: \`https://…\`

## Autenticazione
<Bearer token / firma HMAC / OAuth …>

## Variabili d'ambiente
\`\`\`
${ENV}_API_KEY=
${ENV}_BASE_URL=
\`\`\`
Regola: nessun segreto con prefisso \`NEXT_PUBLIC_\`.

## Endpoint / metodi usati
| Metodo | Path | Request | Response |
|---|---|---|---|
| POST | \`/…\` | \`{…}\` | \`{…}\` |

## Webhook (se presente)
- Endpoint nostro: \`POST /api/webhooks/${slug}\`
- Verifica firma: \`${ENV}_WEBHOOK_SECRET\`
- Eventi gestiti e mapping: <…>

## File nel codice
- \`src/server/${slug}/index.ts\` — client lazy/gated (\`is${cap(slug)}Configured\`, \`get${cap(slug)}\`)
- \`src/server/services/…\` — logica
- \`src/app/api/webhooks/${slug}/route.ts\` — endpoint (se webhook)

## Gestione errori e gating
- \`is${cap(slug)}Configured()\`: assenza env → funzione disattivata, app intatta.
- Codici: 200 OK · 400 firma non valida · 401/503 config assente · 500 ritentabile.

## Costi
<a consumo? flat? soglie>

## Note / TODO
- <shape da confermare, limiti, TODO>
`;

function cap(s) { return s.replace(/(^|-)([a-z])/g, (_, __, c) => c.toUpperCase()); }

async function exists(f) { try { await access(f); return true; } catch { return false; } }
await mkdir(dir, { recursive: true });
if (await exists(file)) { console.error("Esiste già:", file); process.exit(1); }
await writeFile(file, body, "utf8");
console.log(file);
console.log("\n⚠️  Ricorda: aggiungi la riga al registro in .claude/integrations/README.md");
