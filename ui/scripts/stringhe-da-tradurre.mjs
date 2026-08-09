/**
 * Quante stringhe italiane restano scritte a mano nel renderer.
 *
 *   node scripts/stringhe-da-tradurre.mjs          elenco per file
 *   node scripts/stringhe-da-tradurre.mjs --tutte  anche le singole stringhe
 *
 * Nasce da un contatore precedente che **non sapeva dire se si stava
 * avanzando**: contava ogni frammento di testo fra tag, comprese le parti già
 * tradotte, che dopo la traduzione restano lì come `{t('...')}` circondate da
 * spazi e punteggiatura. Due schermate intere tradotte, e il numero era sceso
 * di sei. Un indicatore così non è ottimista o pessimista: è muto, e uno
 * smette di guardarlo — che è il modo in cui si perde di vista il lavoro vero.
 *
 * Qui si contano solo le stringhe che un utente leggerebbe **e** che sono
 * ancora scritte a mano:
 *
 * - i commenti si tolgono per primi (nei file di questo progetto sono più del
 *   codice, e sono tutti in italiano);
 * - il testo dentro `{...}` non è testo, è un'espressione;
 * - resta fuori quello che non si legge: chiavi, classi, percorsi, id.
 *
 * Non è un cancello: non fallisce mai. È un metro.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { basename, join } from 'node:path'

const RADICE = 'renderer'
const TUTTE = process.argv.includes('--tutte')

function file(dir) {
  const fuori = []
  for (const nome of readdirSync(dir)) {
    const p = join(dir, nome)
    if (statSync(p).isDirectory()) fuori.push(...file(p))
    else if (nome.endsWith('.tsx')) fuori.push(p)
  }
  return fuori
}

/** Via i commenti: qui sono in italiano e non li legge nessun utente. */
function senzaCommenti(t) {
  return t
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, ' ') // {/* commento JSX */}
    .replace(/\/\*[\s\S]*?\*\//g, ' ') // /* blocco */ e /** doc */
    .replace(/(^|\s)\/\/[^\n]*/g, '$1 ') // // riga
}

/** Una stringa la legge qualcuno? Almeno due lettere di fila, e non una
 *  parola sola tutta minuscola senza spazi — quelle sono chiavi e classi.
 *
 *  E soprattutto: **non deve essere codice**. `useState<string>('')` mette un
 *  `>` e un `<` intorno a del TypeScript, e la ricerca del testo fra tag ci
 *  cascava — segnalava `(null) const [esito, setEsito] = useState` come una
 *  stringa da tradurre. Un contatore che conta anche il codice non misura il
 *  lavoro che resta, misura la lunghezza dei file. */
function daLeggere(s) {
  const p = s.trim()
  if (p.length < 2) return false
  if (!/[A-Za-zÀ-ÿ]{2,}/.test(p)) return false
  if (/^[a-z][a-z0-9_-]*$/.test(p)) return false // chiave, classe, id
  if (/^[a-z]+:\/\//.test(p)) return false // url
  // Un nodo di testo JSX non contiene parentesi, uguali o punti e virgola.
  if (/[(){}\[\];=]/.test(p)) return false
  if (/(const|let|return|useState|function|import|export)/.test(p)) return false
  return true
}

const perFile = new Map()

for (const percorso of file(RADICE)) {
  const testo = senzaCommenti(readFileSync(percorso, 'utf8'))
  const trovate = []

  // Testo fra tag. `[^<>{}]` esclude le espressioni: `{t('…')}` non è testo.
  for (const m of testo.matchAll(/>([^<>{}]+)</g)) {
    if (daLeggere(m[1])) trovate.push(m[1].trim().replace(/\s+/g, ' '))
  }
  // Attributi che finiscono sotto gli occhi.
  for (const m of testo.matchAll(/(?:placeholder|title|aria-label|alt)="([^"]+)"/g)) {
    if (daLeggere(m[1])) trovate.push(m[1])
  }

  if (trovate.length) perFile.set(basename(percorso), trovate)
}

const totale = [...perFile.values()].reduce((n, v) => n + v.length, 0)
const distinte = new Set([...perFile.values()].flat()).size

console.log(`${totale} stringhe ancora scritte a mano (${distinte} distinte) in ${perFile.size} file\n`)
for (const [nome, elenco] of [...perFile].sort((a, b) => b[1].length - a[1].length)) {
  console.log(`  ${String(elenco.length).padStart(3)}  ${nome}`)
  if (TUTTE) for (const s of elenco) console.log(`         ${s.slice(0, 76)}`)
}
