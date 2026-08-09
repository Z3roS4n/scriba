/**
 * Ogni stringa italiana del catalogo deve esistere, identica, nel sorgente da
 * cui è stata presa.
 *
 * Serve contro due errori che non si vedono:
 *
 * 1. **Riscrivere invece di spostare.** Traducendo si finisce a digitare a
 *    memoria la frase italiana, e la memoria la migliora: «quando è stato
 *    salvato» al posto di «quando è stato collegato». Il prodotto cambia
 *    parole senza che nessuno l'abbia deciso.
 * 2. **Accoppiare per posizione.** Se si affiancano N chiavi a N stringhe
 *    nell'ordine in cui compaiono, basta un duplicato — «Annulla» tre volte —
 *    perché l'elenco scorra di uno e «Quale database?» finisca sul pulsante
 *    Annulla. Il conteggio torna lo stesso, ed è per questo che contare non
 *    basta.
 *
 * Il confronto è con il file al **punto in cui il ramo è nato**, non con
 * HEAD: su HEAD i file già tradotti nei commit precedenti non contengono più
 * l'italiano, e il controllo li segnalerebbe tutti come riscritti. La domanda
 * è «questa frase c'era prima che cominciassimo», e la base è quella.
 *
 *   node scripts/verifica-traduzioni.mjs
 *
 * Esce 1 se una frase non si ritrova: è un cancello, non un metro.
 */

import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

/** Prefisso di chiave -> file da cui quelle stringhe vengono. */
const ORIGINI = {
  'db.': 'ui/renderer/impostazioni/DatabaseRemoto.tsx',
  'ril.': 'ui/renderer/impostazioni/Rilevamento.tsx',
  'ntn.': 'ui/renderer/impostazioni/Notion.tsx',
  'arch.': 'ui/renderer/Archivio.tsx',
  'sez.': 'ui/renderer/Impostazioni.tsx',
  'dat.': 'ui/renderer/impostazioni/Dati.tsx',
  'ras.': 'ui/renderer/Rassegna.tsx',
}

/** Il commit da cui parte il ramo: prima di qualunque traduzione. */
const BASE = execSync('git merge-base HEAD main', { encoding: 'utf8' }).trim()

const catalogo = readFileSync('renderer/lingua.ts', 'utf8')
// Solo il blocco italiano: l'inglese non deve ritrovarsi da nessuna parte.
const italiano = catalogo.slice(0, catalogo.indexOf('const en:'))

const voci = [...italiano.matchAll(/'([a-z]+\.[a-z_0-9]+)':\s*\n?\s*'((?:[^'\\]|\\.)*)'/g)].map(
  (m) => [m[1], m[2].replace(/\\'/g, "'")],
)

const spazi = (s) => s.replace(/\s+/g, ' ').trim()
const sorgenti = new Map()
for (const [prefisso, file] of Object.entries(ORIGINI)) {
  try {
    sorgenti.set(prefisso, spazi(execSync(`git show ${BASE}:${file}`, { encoding: 'utf8' })))
  } catch {
    console.error(`Non riesco a leggere ${file} da ${BASE}.`)
    process.exit(1)
  }
}

let controllate = 0
const perse = []
for (const [chiave, valore] of voci) {
  const prefisso = Object.keys(ORIGINI).find((p) => chiave.startsWith(p))
  if (!prefisso) continue
  // Le stringhe con segnaposto sono COMPOSTE, non spostate: `{n} call` nasce
  // da `{call.length} call` e verbatim non e mai esistita. Confrontarle
  // produrrebbe un rosso perpetuo, e un rosso perpetuo si smette di leggere.
  if (valore.includes('{')) continue
  controllate++
  if (!sorgenti.get(prefisso).includes(spazi(valore))) perse.push(`${chiave} — ${spazi(valore).slice(0, 64)}`)
}

if (controllate === 0) {
  // Il controllo precedente diceva «nessuna frase riscritta» avendo trovato
  // zero voci: dichiarava successo senza aver verificato niente.
  console.error('Nessuna voce controllata: il catalogo non è stato letto. Non è un successo.')
  process.exit(1)
}

console.log(`${controllate} voci italiane confrontate con il sorgente da cui vengono.`)
if (perse.length) {
  console.error(`\n${perse.length} NON si ritrovano — riscritte, o accoppiate alla chiave sbagliata:`)
  for (const p of perse) console.error('   ' + p)
  process.exit(1)
}
console.log('Tutte ritrovate identiche: nessuna frase è stata cambiata traducendo.')
