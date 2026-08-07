/**
 * Legge versione, commit e data dal pacchetto costruito.
 *
 * Non dal repository: **da dentro l'asar**. È l'unico modo di rispondere alla
 * domanda «questo file da dove viene» guardando il file, invece di fidarsi di
 * chi lo ha prodotto — che è tutto il punto del timbro.
 *
 *   node scripts/leggi-timbro.mjs [percorso/app.asar]
 *
 * L'asar comincia con un header Pickle: quattro byte, la dimensione del JSON,
 * poi il JSON con l'elenco dei file e i loro scostamenti. Basta quello per
 * arrivare a un file dentro l'archivio senza scompattare niente.
 */

import { closeSync, openSync, readSync } from 'node:fs'

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
  // Il JSON è allineato a quattro byte: la coda è riempita di zeri.
  const indice = JSON.parse(grezzo.toString('utf8').replace(/\0+$/, ''))

  const voce = indice.files?.dist?.files?.['versione.json']
  if (!voce) {
    console.error('Il pacchetto non contiene dist/versione.json.')
    console.error("Controlla che `files:` in electron-builder.yml lo nomini: senza, l'asar")
    console.error('prende tutto tranne lui e il pacchetto non sa da che commit viene.')
    process.exit(1)
  }

  const dati = Buffer.alloc(voce.size)
  readSync(f, dati, 0, voce.size, 16 + lunghezza + Number(voce.offset))
  process.stdout.write(dati.toString('utf8') + '\n')
} finally {
  closeSync(f)
}
