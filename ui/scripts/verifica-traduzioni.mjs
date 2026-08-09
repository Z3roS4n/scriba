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
  'ovl.': 'ui/renderer/overlay.tsx',
  'cli.': 'ui/renderer/impostazioni/Clienti.tsx',
  'dlg.': 'ui/renderer/Dialoghi.tsx',
  'pan.': 'ui/renderer/Analisi.tsx',
  'tra2.': 'ui/renderer/impostazioni/Trascrizione.tsx',
  'ana.': 'ui/renderer/impostazioni/Analisi.tsx',
  'asp.': 'ui/renderer/impostazioni/Aspetto.tsx',
  'exp.': 'ui/renderer/impostazioni/Export.tsx',
  'mod.': 'ui/renderer/impostazioni/Modelli.tsx',
  'mot.': 'ui/renderer/impostazioni/Motore.tsx',
  'sco.': 'ui/renderer/impostazioni/Scorciatoie.tsx',
  'ntn2.': 'ui/renderer/impostazioni/Notion.tsx',
  'not.': 'ui/renderer/NotaDiLavoro.tsx',
  'prv.': 'ui/renderer/Prove.tsx',
  'rif.': 'ui/renderer/Rifinitura.tsx',
  'sel.': 'ui/renderer/Select.tsx',
  'top.': 'ui/renderer/Topbar.tsx',
  'tra.': 'ui/renderer/Trascrizione.tsx',
  'idx.': 'ui/renderer/index.tsx',
  'arc2.': 'ui/renderer/Archivio.tsx',
  'ras2.': 'ui/renderer/Rassegna.tsx',
  'db2.': 'ui/renderer/impostazioni/DatabaseRemoto.tsx',
  'dat2.': 'ui/renderer/impostazioni/Dati.tsx',
  'ntipo.': 'ui/renderer/impostazioni/Notion.tsx',
  'cli2.': 'ui/renderer/impostazioni/Clienti.tsx',
  'ril2.': 'ui/renderer/impostazioni/Rilevamento.tsx',
  // Queste due vengono dal core: erano frasi scritte in `detect/call.py` e
  // mostrate cosi' come sono. Il confronto vale lo stesso — anzi, vale di
  // piu': è la traversata più facile da fare a memoria.
  'ril_esito.': 'core/scriba_core/detect/call.py',
  'ril_perche.': 'core/scriba_core/detect/call.py',
  'idx2.': 'ui/renderer/index.tsx',
  'mod_stato.': 'ui/renderer/impostazioni/Modelli.tsx',
  'mod2.': 'ui/renderer/impostazioni/Modelli.tsx',
  'not2.': 'ui/renderer/NotaDiLavoro.tsx',
  'traccia.': 'ui/renderer/Rifinitura.tsx',
  'rif2.': 'ui/renderer/Rifinitura.tsx',
  'dlg2.': 'ui/renderer/Dialoghi.tsx',
  'mot2.': 'ui/renderer/impostazioni/Motore.tsx',
  'gloss.': 'ui/renderer/impostazioni/Trascrizione.tsx',
  'gloss_nota.': 'ui/renderer/impostazioni/Trascrizione.tsx',
  'arc3.': 'ui/renderer/Archivio.tsx',
  'sco_nome.': 'ui/renderer/impostazioni/Scorciatoie.tsx',
  'sco2.': 'ui/renderer/impostazioni/Scorciatoie.tsx',
  'prv_campo.': 'ui/renderer/Prove.tsx',
  'tema.': 'ui/renderer/impostazioni/Aspetto.tsx',
  'exp2.': 'ui/renderer/impostazioni/Export.tsx',
  'imp2.': 'ui/renderer/Impostazioni.tsx',
  'ras3.': 'ui/renderer/Rassegna.tsx',
  'tra3.': 'ui/renderer/Trascrizione.tsx',
  'ril2.': 'ui/renderer/impostazioni/Rilevamento.tsx',
}

/**
 * Frasi montate da pezzi che nel sorgente stavano separati, e che verbatim non
 * sono mai esistite. L'elenco è esplicito e corto apposta: la regola generale
 * («ha un segnaposto, quindi è composta») copre quasi tutto, e per il resto è
 * meglio una riga scritta a mano che si legge, di una regola più larga che
 * lascia passare anche le riscritture vere.
 */
const COMPOSTE = new Set([
  // `microfono {p.picco > 0 ? … : 'muto'}`: la parola stava fra i tag, lo
  // stato dentro l'espressione. In inglese l'una senza l'altra non si traduce.
  'ril2.mic_muto',
  // «…è ripartito {da un backup | da vuoto}: le call registrate dopo…». Il
  // ternario stava in mezzo alla frase: le due frasi intere non sono mai
  // esistite, ma ognuna delle tre parti sì.
  'idx2.db_da_backup',
  'idx2.db_da_vuoto',
  // `{n === 1 ? 'ripresa' : 'riprese'} dall'altoparlante`: singolare e plurale
  // dentro l'espressione, il complemento fuori.
  'tra3.ripresa',
  'tra3.riprese',
])

/** Il commit da cui parte il ramo: prima di qualunque traduzione. */
const BASE = execSync('git merge-base HEAD main', { encoding: 'utf8' }).trim()

const catalogo = readFileSync('renderer/lingua.ts', 'utf8')
// Solo il blocco italiano: l'inglese non deve ritrovarsi da nessuna parte.
const italiano = catalogo.slice(0, catalogo.indexOf('const en:'))

// La chiave può avere cifre e trattini bassi da entrambe le parti del punto.
// Con `[a-z]+` a sinistra questa espressione saltava in silenzio ogni prefisso
// numerato — `cli2.`, `db2.`, `ril2.`, `tra2.` — cioè quasi tutte le schermate
// tradotte per seconde: il cancello contava, diceva un numero rassicurante, e
// quelle non le guardava nessuno.
const voci = [...italiano.matchAll(/'([a-z][a-z_0-9]*\.[a-z_0-9]+)':\s*\n?\s*'((?:[^'\\]|\\.)*)'/g)].map(
  (m) => [m[1], m[2].replace(/\\'/g, "'")],
)

// Oltre agli spazi si tolgono le giunzioni fra letterali adiacenti: in Python
// una frase lunga si scrive `"prima met… " "seconda metà"`, e i due apici in
// mezzo sono il modo in cui il linguaggio dice «continua», non testo.
const spazi = (s) =>
  s
    .replace(/"\s*"/g, '')
    .replace(/\s+/g, ' ')
    .trim()
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
let scoperte = 0
const perse = []
for (const [chiave, valore] of voci) {
  const prefisso = Object.keys(ORIGINI).find((p) => chiave.startsWith(p))
  if (!prefisso) {
    scoperte++
    continue
  }
  // Le stringhe con segnaposto sono COMPOSTE, non spostate: `{n} call` nasce
  // da `{call.length} call` e verbatim non e mai esistita. Confrontarle
  // produrrebbe un rosso perpetuo, e un rosso perpetuo si smette di leggere.
  if (valore.includes('{') || COMPOSTE.has(chiave)) continue
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
// Quante restano fuori si dice ad alta voce: sono le etichette dei valori
// salvati (`voce.`, `priorita.`, `stato.`) e i testi composti, che verbatim
// nel sorgente non sono mai esistiti. Un cancello che non dice cosa NON
// guarda si legge come se guardasse tutto.
console.log(`${scoperte} senza origine dichiarata: etichette di valori salvati e testo composto.`)
if (perse.length) {
  console.error(`\n${perse.length} NON si ritrovano — riscritte, o accoppiate alla chiave sbagliata:`)
  for (const p of perse) console.error('   ' + p)
  process.exit(1)
}
console.log('Tutte ritrovate identiche: nessuna frase è stata cambiata traducendo.')

/* ------------------------------------------------------------------ inglese
 *
 * Il tipo garantisce che ogni chiave italiana abbia una riga inglese. Non
 * garantisce che quella riga sia inglese: copiare l'italiano compila, e
 * l'errore si vede solo mettendo l'applicazione in inglese e guardando quella
 * schermata — cioè quasi mai.
 *
 * E poi i segnaposto. `{n} righe` tradotto «{righe} lines» compila lo stesso,
 * e in inglese esce la parola `{righe}` scritta com'è, fra graffe, dentro
 * l'interfaccia.
 */
const inglese = catalogo.slice(catalogo.indexOf('const en:'))
const en = new Map(
  [...inglese.matchAll(/'([a-z][a-z_0-9]*\.[a-z_0-9]+)':\s*\n?\s*'((?:[^'\\]|\\.)*)'/g)].map((m) => [
    m[1],
    m[2].replace(/\\'/g, "'"),
  ]),
)

/** Uguali in tutte e due le lingue perché sono nomi propri, tasti o prestiti. */
const UGUALI_APPOSTA = new Set([
  'top.nome',
  'ovl.nome',
  'arc2.esc',
  'ras2.esc',
  'sez.export',
  'exp.titolo',
  'azione.screenshot',
  'call.senza_titolo',
  'ntipo.url',
])

const segnaposti = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()
const copiate = []
const buchi = []
for (const [chiave, valore] of voci) {
  const t = en.get(chiave)
  if (t === undefined) continue
  if (t === valore && !UGUALI_APPOSTA.has(chiave)) copiate.push(`${chiave} — ${valore.slice(0, 56)}`)
  const [a, b] = [segnaposti(valore).join(','), segnaposti(t).join(',')]
  if (a !== b) buchi.push(`${chiave} — it {${a}} vs en {${b}}`)
}

if (copiate.length) {
  console.error(`\n${copiate.length} righe inglesi sono ancora l'italiano:`)
  for (const c of copiate) console.error('   ' + c)
}
if (buchi.length) {
  console.error(`\n${buchi.length} con segnaposto diversi — in una delle due lingue resta scritto fra graffe:`)
  for (const b of buchi) console.error('   ' + b)
}
if (copiate.length || buchi.length) process.exit(1)
console.log(`${en.size} righe inglesi: tradotte davvero, e con gli stessi segnaposto.`)
