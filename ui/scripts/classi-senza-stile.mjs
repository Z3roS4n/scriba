/**
 * Ogni classe scritta in un `className` deve esistere nel foglio di stile.
 *
 *   node scripts/classi-senza-stile.mjs
 *
 * Nasce da un difetto che è arrivato fino a un rilascio. Passando al foglio di
 * stile 1.0 diverse classi hanno cambiato nome — `.nota__testa` è diventata
 * `.nota__head`, `.model__name` è diventata `.model__n` — e undici componenti
 * hanno continuato a scrivere il nome vecchio. Quelle regole non si
 * applicavano più a niente: la nota di lavoro usciva con l'etichetta e il
 * minuto attaccati, «NOTA DI LAVOROfino a 29:59» (#86).
 *
 * **Perché l'audit non l'aveva visto.** Durante la migrazione misuravo altezze
 * e raggi dei controlli, e un elemento senza regole un'altezza ce l'ha
 * comunque: era la domanda sbagliata. La domanda giusta è se la regola scritta
 * raggiunga qualcuno, e si risponde solo confrontando i due lati.
 *
 * È un cancello, non un metro: una classe che non esiste non è mai una scelta.
 *
 * **Cosa non vede, dichiarato.** Guarda `className` scritto nel file. Una
 * classe composta a runtime (`className={variabile}`, o un nome montato pezzo
 * per pezzo) qui non compare, e il senso opposto — una regola CSS che non
 * raggiunge nessuno — non è un difetto e non si controlla.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

const RADICE = 'renderer'
const FOGLI = ['app.css', 'tokens.css', 'shell.css']

function file(dir) {
  const fuori = []
  for (const nome of readdirSync(dir)) {
    const p = join(dir, nome)
    if (statSync(p).isDirectory()) fuori.push(...file(p))
    else if (nome.endsWith('.tsx')) fuori.push(p)
  }
  return fuori
}

/** Via i commenti prima di contare le graffe.
 *
 * Senza, un `className={…}` seguito da un commento che contiene un apostrofo
 * — «l'altro» — apriva un letterale che non si chiudeva più, e il controllo
 * segnalava come classi le parole del commento. */
function senzaCommenti(t) {
  return t
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/(^|[\s({[])\/\/[^\n]*/g, '$1 ')
}

const css = FOGLI.map((n) => readFileSync(join(RADICE, n), 'utf8')).join('\n')
const definite = new Set([...css.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)].map((m) => m[1]))

/**
 * Classi che il design lascia apposta senza regole.
 *
 * `.line--other` è la riga di chi non sei tu: nel foglio di stile ha una
 * regola solo `.line--me`, perché «gli altri» è il caso normale e il caso
 * normale non si dipinge. La classe serve lo stesso — a leggere il markup, e
 * a poterci attaccare qualcosa un giorno senza cambiare i componenti.
 *
 * L'elenco è corto e scritto a mano di proposito: ogni voce è una decisione,
 * non una scappatoia. Se diventa lungo, il difetto è altrove.
 */
const SENZA_REGOLA = new Set(['line--other'])

/**
 * I letterali dentro `className={…}` non sono tutti classi.
 *
 *     className={(stt.glossario_livello ?? 'prudente') === id ? 'is-on' : ''}
 *
 * `'prudente'` è un valore salvato con cui si sta confrontando, `'is-on'` è la
 * classe. Si distinguono da cosa hanno davanti: dopo `??`, `===`, `!==`, `==`
 * e `!=` c'è un operando, mai un nome di classe.
 */
const CONFRONTO = /(\?\?|===|!==|==|!=)\s*$/

/** I nomi che si vedono in un `className`, con la riga in cui stanno. */
function classiDi(testo) {
  const fuori = []
  const aggiungi = (grezzo, indice) => {
    for (const nome of grezzo.split(/\s+/)) {
      if (nome && !nome.includes('$') && !nome.includes('{')) fuori.push([nome, indice])
    }
  }

  for (const m of testo.matchAll(/className="([^"]*)"/g)) aggiungi(m[1], m.index)

  // `className={…}`: si prende il contenuto fino alla graffa che chiude, poi
  // dentro si guardano i pezzi dei template e i letterali in posizione di
  // classe.
  for (const m of testo.matchAll(/className=\{/g)) {
    let i = m.index + m[0].length
    let profondita = 1
    while (i < testo.length && profondita > 0) {
      if (testo[i] === '{') profondita += 1
      else if (testo[i] === '}') profondita -= 1
      i += 1
    }
    const dentro = testo.slice(m.index + m[0].length, i - 1)
    const base = m.index + m[0].length
    for (const t of dentro.matchAll(/`([^`]*)`/g)) {
      aggiungi(t[1].replace(/\$\{[^}]*\}/g, ' '), base + t.index)
    }
    for (const l of dentro.matchAll(/'([^']*)'/g)) {
      if (CONFRONTO.test(dentro.slice(0, l.index))) continue
      aggiungi(l[1], base + l.index)
    }
  }
  return fuori
}

const perFile = new Map()
let guardate = 0

for (const percorso of file(RADICE)) {
  const testo = senzaCommenti(readFileSync(percorso, 'utf8'))
  const righe = testo.split('\n')
  const offset = [0]
  for (const r of righe) offset.push(offset[offset.length - 1] + r.length + 1)
  const numeroRiga = (i) => offset.findIndex((o) => o > i)

  const perse = []
  for (const [nome, indice] of classiDi(testo)) {
    guardate += 1
    if (!definite.has(nome) && !SENZA_REGOLA.has(nome)) perse.push([nome, numeroRiga(indice)])
  }
  if (perse.length) perFile.set(relative(RADICE, percorso).replaceAll(sep, '/'), perse)
}

if (guardate === 0) {
  // Un controllo che non ha guardato niente dichiara successo per errore.
  console.error('Nessun className letto: il controllo non ha guardato niente. Non è un successo.')
  process.exit(1)
}

const totale = [...perFile.values()].reduce((n, v) => n + v.length, 0)
console.log(`${guardate} classi lette dai componenti, ${definite.size} definite nei fogli di stile.`)

if (!totale) {
  console.log('Ognuna ha una regola che la raggiunge.')
  process.exit(0)
}

console.error(`\n${totale} classi non esistono nel foglio di stile:\n`)
for (const [nome, elenco] of [...perFile].sort((a, b) => b[1].length - a[1].length)) {
  console.error(`  ${nome}`)
  for (const [classe, riga] of elenco) console.error(`      .${classe}  (riga ${riga})`)
}
process.exit(1)
