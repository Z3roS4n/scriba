/**
 * Porta in `dist/renderer/` quello che esbuild non tocca: le tre pagine, i tre
 * fogli di stile, e la cartella del font.
 *
 * Prima era un `node -e` di una riga dentro package.json, con l'elenco dei
 * file scritto a mano. Copiava **file per nome**, quindi una cartella non
 * sarebbe mai entrata — e nessuno se ne sarebbe accorto: `electron-builder`
 * impacchetta `dist/renderer/**`, quindi un font mancante non produce un
 * errore, produce un'applicazione che parte nel carattere di ripiego e sembra
 * a posto (#81).
 *
 * Da qui la seconda metà di questo script: dopo aver copiato, **controlla che
 * ogni url() dei CSS punti a un file che esiste davvero**. È il difetto di
 * classe, non il caso particolare: chiunque aggiunga un font o un'immagine e
 * si dimentichi di copiarla trova la build ferma, invece di scoprirlo mesi
 * dopo guardando una schermata che non è come dovrebbe.
 */

import { cpSync, existsSync, mkdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, posix } from 'node:path'

const DA = 'renderer'
const A = 'dist/renderer'

const FILE = ['index.html', 'overlay.html', 'impostazioni.html', 'tokens.css', 'app.css', 'shell.css']
/** Cartelle intere. Il font sta qui, con la sua licenza: la SIL OFL 1.1 chiede
 *  che il testo accompagni il font, quindi OFL.txt viaggia nel pacchetto. */
const CARTELLE = ['font']

mkdirSync(A, { recursive: true })
for (const f of FILE) cpSync(join(DA, f), join(A, f))
for (const c of CARTELLE) {
  if (!existsSync(join(DA, c))) {
    console.error(`Manca ${DA}/${c}: è elencata fra le cartelle da copiare ma non c'è.`)
    process.exit(1)
  }
  cpSync(join(DA, c), join(A, c), { recursive: true })
}

// --------------------------------------------------- ogni url() deve esistere

/** Gli url() di un CSS, saltando `data:` e gli indirizzi di rete — quelli non
 *  sono file da copiare, e uno di rete nel prodotto sarebbe un problema
 *  diverso (il CSP lo rifiuterebbe comunque). */
function riferimenti(css) {
  const trovati = []
  for (const m of css.matchAll(/url\(\s*['"]?([^'")]+)['"]?\s*\)/g)) {
    const u = m[1].trim()
    if (u.startsWith('data:') || /^[a-z]+:\/\//i.test(u)) continue
    trovati.push(u.split('?')[0].split('#')[0])
  }
  return trovati
}

const mancanti = []
for (const f of FILE.filter((f) => f.endsWith('.css'))) {
  const percorso = join(A, f)
  for (const rif of riferimenti(readFileSync(percorso, 'utf8'))) {
    const atteso = join(dirname(percorso), ...rif.split(posix.sep))
    if (!existsSync(atteso) || statSync(atteso).size === 0) {
      mancanti.push(`${f} chiede ${rif} → ${atteso} non c'è (o è vuoto)`)
    }
  }
}

if (mancanti.length > 0) {
  console.error('Risorse dichiarate nei CSS e non presenti nel pacchetto:')
  for (const m of mancanti) console.error(`  ${m}`)
  console.error('')
  console.error("Senza il file l'applicazione non dà errore: ripiega e sembra funzionare.")
  console.error('Aggiungi la cartella a CARTELLE qui sopra, oppure correggi il percorso nel CSS.')
  process.exit(1)
}
