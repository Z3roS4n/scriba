/**
 * Il punto cieco dell'altro contatore: le stringhe dentro le espressioni.
 *
 *   node scripts/stringhe-nascoste.mjs
 *
 * `stringhe-da-tradurre.mjs` guarda il testo fra tag e quattro attributi, e
 * dichiara di non vedere il resto. Il resto però l'utente lo legge:
 *
 *     {t.stato === 'confirmed' ? 'confermata' : 'scartata'}
 *     const CAMPI = [{ etichetta: 'Responsabile' }]
 *     setErrore('Il nome non può essere vuoto.')
 *
 * Arrivare a zero sul primo metro e fermarsi lì vuol dire consegnare
 * un'interfaccia che in inglese dice ancora «non detto» e «già presente» —
 * proprio nei posti che si leggono quando qualcosa va storto, che sono i posti
 * in cui non si ha voglia di indovinare.
 *
 * Qui si guardano i letterali di stringa. Riconoscerli come italiani senza un
 * dizionario non si può, quindi c'è una lista corta di parole-spia: articoli,
 * negazioni, e le parole del prodotto. Sbaglia in eccesso — un `'la'` dentro
 * un identificatore lo fa passare — ed è il verso giusto: le tre righe di
 * troppo si vedono leggendo, quelle di meno no.
 *
 * Non è un cancello: non fallisce mai. È un metro, come l'altro.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

const RADICE = 'renderer'
const TUTTE = !process.argv.includes('--conta')

function file(dir) {
  const fuori = []
  for (const nome of readdirSync(dir)) {
    const p = join(dir, nome)
    if (statSync(p).isDirectory()) fuori.push(...file(p))
    else if (nome.endsWith('.tsx') || nome.endsWith('.ts')) fuori.push(p)
  }
  return fuori
}

function senzaCommenti(t) {
  return t
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|\s)\/\/[^\n]*/g, '$1 ')
}

/** Parole che in un'interfaccia inglese non compaiono mai. */
const SPIA =
  /\b(il|lo|la|le|gli|un|una|del|della|dei|delle|che|non|per|con|sul|sulla|nel|nella|questo|questa|quando|come|dove|più|già|sono|essere|fare|dice|detto|detta|salva|apri|chiudi|scegli|nessun|nessuna|ancora|adesso|solo|anche|senza|prova|prove|voce|voci|riga|righe|minuto|conferma|confermata|scartata|entro|chi)\b/i

const perFile = new Map()

for (const percorso of file(RADICE)) {
  if (percorso.endsWith('lingua.ts')) continue // è il catalogo: lì l'italiano ci va
  const testo = senzaCommenti(readFileSync(percorso, 'utf8'))
  const trovate = []

  for (const m of testo.matchAll(/(?<![\w$)])(['"])((?:[^'"\\\n]|\\.){2,})\1/g)) {
    const s = m[2]
    const prima = testo.slice(Math.max(0, m.index - 40), m.index)
    if (/\bfrom\s+$|\b(import|require)\s*\($/.test(prima)) continue
    if (/\b(className|class|id|key|href|src|type|role|name|method|charset)=\s*$/.test(prima)) continue
    if (/\b(t|tr|etichettaValore|etichettaVoce)\(\s*$/.test(prima)) continue
    if (/[.[]\s*$/.test(prima)) continue // accesso a una proprietà
    if (/^[a-z][\w-]*$/.test(s)) continue // chiave, classe, stato
    if (/^[/.]/.test(s)) continue // percorso o rotta
    if (/^[\w.]+$/.test(s)) continue // chiave puntata: `call.in_analisi`
    if (/^[-\w\s,.#%()/]+$/.test(s) && !SPIA.test(s)) continue // css, formati, inglese
    if (!SPIA.test(s) && !/[àèéìòù«»]/.test(s)) continue
    trovate.push(s)
  }

  if (trovate.length) perFile.set(relative(RADICE, percorso).replaceAll(sep, '/'), trovate)
}

const totale = [...perFile.values()].reduce((n, v) => n + v.length, 0)
console.log(`${totale} letterali italiani dentro le espressioni, in ${perFile.size} file\n`)
for (const [nome, elenco] of [...perFile].sort((a, b) => b[1].length - a[1].length)) {
  console.log(`  ${String(elenco.length).padStart(3)}  ${nome}`)
  if (TUTTE) for (const s of elenco) console.log(`         ${s.slice(0, 80)}`)
}
