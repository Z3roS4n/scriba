/**
 * Controlla che dentro l'asar ci sia davvero quello che serve a partire.
 *
 *   node scripts/verifica-pacchetto.mjs [percorso/app.asar]
 *
 * Perché non basta controllare `dist/`. `copia-risorse.mjs` garantisce che le
 * risorse arrivino in `dist/renderer/`; da lì a dentro il pacchetto c'è un
 * altro passaggio — il `files:` di electron-builder — e finora quel passaggio
 * era **dato per buono**. È l'anello che non si vedeva: un font copiato in
 * `dist` e non impacchettato produce la stessa cosa di un font mai copiato,
 * cioè un'applicazione che parte nel carattere di ripiego e sembra a posto
 * (#81).
 *
 * Qui si guarda il file che si spedisce, non un passaggio intermedio. Stessa
 * idea del timbro (`leggi-timbro.mjs`): rispondere guardando il pacchetto
 * invece di fidarsi di chi lo ha prodotto.
 */

import { closeSync, openSync, readSync } from 'node:fs'

/** Quello senza cui l'applicazione parte sbagliata invece che non partire —
 *  che è il caso pericoloso. Il resto (bundle, main) se manca si nota subito. */
const RICHIESTI = [
  'renderer/index.html',
  'renderer/overlay.html',
  'renderer/impostazioni.html',
  'renderer/tokens.css',
  'renderer/app.css',
  'renderer/shell.css',
  'renderer/bundle.js',
  // Il font e la sua licenza: la SIL OFL 1.1 chiede che il testo accompagni il
  // font, quindi un pacchetto senza OFL.txt non e' solo incompleto, e' fuori
  // licenza.
  'renderer/font/montserrat-latin.woff2',
  'renderer/font/OFL.txt',
]

const percorso = process.argv[2] ?? 'release/win-unpacked/resources/app.asar'

let f
try {
  f = openSync(percorso, 'r')
} catch {
  console.error(`Nessun pacchetto in ${percorso}.`)
  process.exit(1)
}

try {
  const testa = Buffer.alloc(16)
  readSync(f, testa, 0, 16, 0)
  const lunghezza = testa.readUInt32LE(12)
  const grezzo = Buffer.alloc(lunghezza)
  readSync(f, grezzo, 0, lunghezza, 16)

  let indice
  try {
    indice = JSON.parse(grezzo.toString('utf8'))
  } catch {
    console.error("L'indice dell'asar non è JSON valido: pacchetto illeggibile.")
    process.exit(1)
  }

  /** La voce all'interno di `dist/`, seguendo il percorso pezzo per pezzo. */
  function voce(percorsoInterno) {
    let nodo = indice.files?.dist
    for (const pezzo of percorsoInterno.split('/')) {
      nodo = nodo?.files?.[pezzo]
      if (!nodo) return null
    }
    return nodo
  }

  const mancanti = []
  for (const r of RICHIESTI) {
    const v = voce(r)
    if (!v) mancanti.push(`${r} — non c'è`)
    else if (!v.size) mancanti.push(`${r} — c'è ma è vuoto`)
  }

  if (mancanti.length > 0) {
    console.error(`Il pacchetto ${percorso} è incompleto:`)
    for (const m of mancanti) console.error(`  dist/${m}`)
    console.error('')
    console.error("Controlla `files:` in electron-builder.yml e la copia in copia-risorse.mjs.")
    console.error("Senza questi file l'applicazione parte lo stesso, sbagliata: è il caso peggiore.")
    process.exit(1)
  }

  for (const r of RICHIESTI) {
    console.log(`  ok  dist/${r}  (${voce(r).size} byte)`)
  }
} finally {
  closeSync(f)
}
