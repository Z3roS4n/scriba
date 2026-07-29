/**
 * Confronta l'implementazione React con il handoff di Claude Design.
 *
 * Non è un controllo visivo — quello si fa aprendo l'applicazione — ma coglie
 * le due derive che passano inosservate:
 *
 *   1. una classe che il design usa e il codice non nomina da nessuna parte: un
 *      pezzo di schermata non costruito, o costruito in un altro modo;
 *   2. una classe che il codice scrive e nessun CSS conosce: uno stile
 *      inventato, che non verrà mai applicato e resterà lì a mentire.
 *
 * Non si prova a interpretare le espressioni JSX: un `className` può essere un
 * template con dentro ternari annidati, e un estrattore che ci prova finisce a
 * scambiare i nomi delle variabili per nomi di classe. Si guardano invece
 * **tutte** le stringhe letterali del file, che è dove le classi devono per
 * forza comparire — quindi le classi assemblate pezzo per pezzo a runtime
 * (`'line--' + tipo`) restano invisibili, ed è giusto così: vanno scritte
 * intere anche nel codice, altrimenti non sono verificabili da nessuno.
 *
 *   npm run confronta
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const QUI = dirname(fileURLToPath(import.meta.url))
const UI = join(QUI, '..')
const RENDERER = join(UI, 'renderer')
const HANDOFF = join(UI, '..', '.claude', 'project', 'design', 'handoff')

/** Classi che vivono solo nelle pagine di prova: non vanno implementate. */
const SOLO_DEMO = new Set([
  'harness', 'harness__bar',
  'stage__half', 'stage__half--dark', 'stage__half--light',
  'scrimwrap', 'scrimwrap__bg', 'scrimwrap__scrim',
  'level',
])

/** Forma di un nome di classe del design: `blocco`, `blocco__parte`, `blocco--variante`. */
const NOME_CLASSE = /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:__[a-z0-9]+(?:-[a-z0-9]+)*)?(?:--[a-z0-9]+(?:-[a-z0-9]+)*)?$/

/** Solo queste hanno la forma inconfondibile di una classe: le altre potrebbero
 *  essere qualunque parola dentro una stringa, e segnalarle sarebbe rumore. */
const RICONOSCIBILE = /(?:__|--)|^(?:is|has)-/

function files(dir, filtro, out = []) {
  for (const nome of readdirSync(dir)) {
    const p = join(dir, nome)
    if (statSync(p).isDirectory()) {
      if (nome !== 'node_modules') files(p, filtro, out)
    } else if (filtro.test(nome)) {
      out.push(p)
    }
  }
  return out
}

/** Le classi usate nel handoff, con la pagina in cui compaiono. */
function classiDelHandoff() {
  const mappa = new Map()
  for (const file of files(HANDOFF, /\.html$/)) {
    const pagina = relative(HANDOFF, file)
    for (const m of readFileSync(file, 'utf8').matchAll(/class="([^"]+)"/g)) {
      for (const c of m[1].split(/\s+/).filter(Boolean)) {
        if (!mappa.has(c)) mappa.set(c, new Set())
        mappa.get(c).add(pagina)
      }
    }
  }
  return mappa
}

/** Ogni parola scritta dentro una stringa del codice React, col file di origine. */
function paroleDelCodice() {
  const mappa = new Map()
  const stringhe = /'([^'\\\n]*)'|"([^"\\\n]*)"|`([^`\\]*)`/g
  for (const file of files(RENDERER, /\.tsx$/)) {
    const nome = relative(RENDERER, file)
    for (const m of readFileSync(file, 'utf8').matchAll(stringhe)) {
      const contenuto = m[1] ?? m[2] ?? m[3] ?? ''
      // Le virgolette entrano nello split: un template letterale contiene le
      // stringhe dei suoi ternari, e senza toglierle si otterrebbe `'is-cited'`
      // con gli apici attaccati, che non somiglia più a un nome di classe.
      for (const parola of contenuto.split(/[\s${}'"`]+/)) {
        if (!parola || !NOME_CLASSE.test(parola)) continue
        if (!mappa.has(parola)) mappa.set(parola, new Set())
        mappa.get(parola).add(nome)
      }
    }
  }
  return mappa
}

/** Le classi che il CSS conosce davvero. */
function classiDelCss() {
  const insieme = new Set()
  for (const file of ['app.css', 'tokens.css', 'shell.css']) {
    for (const m of readFileSync(join(RENDERER, file), 'utf8').matchAll(/\.([a-zA-Z][a-zA-Z0-9_-]*)/g)) {
      insieme.add(m[1])
    }
  }
  return insieme
}

const handoff = classiDelHandoff()
const codice = paroleDelCodice()
const css = classiDelCss()

const mancanti = [...handoff.keys()]
  .filter((c) => !SOLO_DEMO.has(c) && !codice.has(c))
  .sort()

const inventate = [...codice.keys()]
  .filter((c) => RICONOSCIBILE.test(c) && !css.has(c) && !handoff.has(c))
  .sort()

console.log(`handoff: ${handoff.size} classi · parole nel codice: ${codice.size} · css: ${css.size}\n`)

if (mancanti.length) {
  console.log(`Nel design ma mai nominate nel codice — ${mancanti.length}:`)
  for (const c of mancanti) console.log(`  .${c}  (${[...handoff.get(c)].join(', ')})`)
  console.log()
} else {
  console.log('Nessuna classe del design è rimasta fuori dal codice.\n')
}

if (inventate.length) {
  console.log(`Hanno forma di classe ma nessun CSS le conosce — ${inventate.length}:`)
  for (const c of inventate) console.log(`  .${c}  (${[...codice.get(c)].join(', ')})`)
  console.log()
} else {
  console.log('Nessuna classe inventata.\n')
}

process.exitCode = mancanti.length || inventate.length ? 1 : 0
