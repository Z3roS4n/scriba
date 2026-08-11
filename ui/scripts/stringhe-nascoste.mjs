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

/** Parole che in un'interfaccia inglese non compaiono mai.
 *
 * L'elenco è cresciuto leggendo: la prima versione trovava «non detto» e si
 * lasciava dietro «Sto salvando…» e «campi su Notion», che stanno nello
 * stesso file e nella stessa schermata. Ogni parola aggiunta viene da una
 * stringa vera che era sfuggita, non da un dizionario — `fino` è arrivata
 * così, dopo che «fino a 29:59» è uscito in italiano in un'interfaccia
 * inglese con tutti e due i metri a zero (#89).
 *
 * Tre parole sono uscite dall'elenco per la ragione opposta: `crea`,
 * `elenco` e `conferma` qui non sono testo, sono i passi di una schermata
 * — `passo === 'crea'` — e restavano in cima al metro per sempre. Un numero
 * che non puo' arrivare a zero e' un numero che si smette di guardare. */
const SPIA =
  /\b(il|lo|la|le|gli|un|una|del|della|dei|delle|che|non|per|con|su|sul|sulla|nel|nella|dal|dalla|al|alla|allo|agli|alle|tra|fra|questo|questa|quando|come|dove|più|già|sono|sta|sto|stanno|essere|fare|dice|detto|detta|salva|salvando|creando|apri|chiudi|scegli|serve|servono|vale|torna|manda|mandare|resta|restano|esce|viene|vengono|nessun|nessuna|ogni|tutte|tutti|tutto|tutta|ancora|adesso|solo|anche|senza|fino|circa|gratis|oppure|invece|mentre|però|così|qui|niente|prova|prove|voce|voci|riga|righe|minuto|minuti|campo|campi|colonna|colonne|pagina|nome|nomi|confermata|scartata|entro|chi)\b/i

const perFile = new Map()

for (const percorso of file(RADICE)) {
  if (percorso.endsWith('lingua.ts')) continue // è il catalogo: lì l'italiano ci va
  const testo = senzaCommenti(readFileSync(percorso, 'utf8'))
  const trovate = []

  // Tre nascondigli, non uno:
  //   'letterale'   `template ${con} buchi`   >testo con {espressione} dentro<
  // Il terzo sfugge anche all'altro contatore, che cerca `>[^<>{}]+<` e quindi
  // salta ogni nodo di testo in cui compaia un'espressione — «Database
  // «{schema.titolo}». Un campo lasciato su…» non lo vedeva nessuno dei due.
  const pezzi = []
  // I due apici si cercano separatamente: con una classe sola —
  // `[^'"]` — una stringa fra doppi apici che contenga un apostrofo si
  // interrompe al primo, e «"L'ultima analisi non è riuscita."» non veniva
  // vista da nessuno dei due metri.
  const LETTERALE = /(?<![\w$)])"((?:[^"\\\n]|\\.){2,})"|(?<![\w$)])'((?:[^'\\\n]|\\.){2,})'/g
  for (const m of testo.matchAll(LETTERALE)) {
    const valore = m[1] ?? m[2]
    // `{t('a')}{' '}{x.map(…).join(t('b'))}`: gli apici si accoppiano a due a
    // due, e quello di chiusura di `' '` con quello di apertura di `'b'`
    // racchiudono del codice. Una stringa mostrata non contiene graffe — i
    // segnaposto le hanno solo nel catalogo, non qui.
    if (!/[{}]/.test(valore)) pezzi.push([valore, m.index])
  }
  // I pezzi che vengono da un taglio (template e nodi misti) possono finire a
  // metà di un'espressione: `${` annidati e `=>` mandano a spasso qualunque
  // ritaglio fatto con un'espressione regolare. Un frammento con dentro
  // `=`, `;` o una graffa è codice tagliato male, non una frase.
  const prosa = (p) => p.trim().length > 1 && !/[=;{}`'"[\]]|=>/.test(p)
  for (const m of testo.matchAll(/`((?:[^`\\]|\\.)*)`/g)) {
    for (const parte of m[1].split(/\$\{[^{}]*\}/)) if (prosa(parte)) pezzi.push([parte, m.index])
  }
  // I nodi di testo li guarda anche l'altro metro, ma li scarta quando sono
  // una parola sola tutta minuscola — «chi», «entro» — perché lì di solito
  // c'è una classe. Sono etichette vere, e l'unico posto in cui si vedono è
  // questo: l'altro metro segna zero, quindi ciò che si trova qui è per
  // definizione ciò che gli è sfuggito.
  if (percorso.endsWith('.tsx')) {
    // Solo nei .tsx: in un .ts ogni `>` è la chiusura di un generico, e
    // `Promise<void>` seguito da un `<` più in là produce «chiudi(): Promise»
    // come se fosse una frase. E un nodo di testo non contiene mai `(` o `:`.
    for (const m of testo.matchAll(/(?<![=\-!<>])>([^<>]{2,})</g)) {
      for (const parte of m[1].split(/\{[^{}]*\}/)) {
        // I due punti in una frase ci stanno («Motore: …»); in un generico
        // TypeScript no, e un generico non ha spazi. Si guarda quello.
        const codice = /[()]/.test(parte) || (/:/.test(parte) && !/\s/.test(parte))
        if (prosa(parte) && !codice) pezzi.push([parte.trim(), m.index])
      }
    }
  }

  for (const [grezzo, dove] of pezzi) {
    const s = grezzo
    const prima = testo.slice(Math.max(0, dove - 40), dove)
    if (/\bfrom\s+$|\b(import|require)\s*\($/.test(prima)) continue
    if (/\b(className|class|id|key|href|src|type|role|name|method|charset)=\s*$/.test(prima)) continue
    if (/\b(t|tr|etichettaValore|etichettaVoce)\(\s*$/.test(prima)) continue
    if (/[.[]\s*$/.test(prima)) continue // accesso a una proprietà
    // Una parola sola tutta minuscola è quasi sempre uno stato o una classe —
    // `proposed`, `confirmed`, `sum`. Quasi: `'confermata'` e `'scartata'`
    // hanno la stessa forma e sono quello che l'utente legge sulla riga. Se è
    // una parola-spia vince la spia.
    if (/^[a-z][\w-]*$/.test(s) && !SPIA.test(s)) continue
    // Percorso o rotta: `/database-remoto/prova`, `./lingua`. Un punto
    // seguito da spazio no — è la coda di una frase che riprende dopo
    // un'espressione, «. La trascrizione lascia questo computer.»
    if (/^\/|^\.[^\s]/.test(s)) continue
    if (/^\w+(\.\w+)+$/.test(s)) continue // chiave puntata: `call.in_analisi`
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
