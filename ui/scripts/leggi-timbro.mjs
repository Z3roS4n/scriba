/**
 * Legge versione, commit e data dal pacchetto costruito.
 *
 * Non dal repository: **da dentro l'asar**. È l'unico modo di rispondere alla
 * domanda «questo file da dove viene» guardando il file, invece di fidarsi di
 * chi lo ha prodotto — che è tutto il punto del timbro.
 *
 *   node scripts/leggi-timbro.mjs [percorso/app.asar]
 *
 * L'asar comincia con un header Pickle di quattro campi da quattro byte:
 *
 *     0-3    4        quanto e' lungo il campo dopo
 *     4-7    3372     l'header intero, **riempimento compreso**
 *     8-11   3368     il payload
 *     12-15  3361     la stringa JSON, e basta lei
 *
 * I dati dei file cominciano a `8 + header`, non a `16 + lunghezza del JSON`:
 * il JSON e' allineato a quattro byte, quindi fra i due c'e' uno scarto da 0 a
 * 3 byte a seconda di quanto e' lungo l'indice. Questo script usava il secondo
 * calcolo e leggeva fino a tre byte prima dell'inizio (#65). Quando lo scarto
 * era zero funzionava, ed e' per questo che e' passato inosservato: sbagliava
 * e sembrava funzionare — che e' il modo peggiore, per uno script che esiste
 * apposta per verificare.
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
  // Due misure diverse, e servono entrambe: la stringa per leggere il JSON,
  // l'header riempito per sapere dove finisce e cominciano i dati.
  const dimensioneHeader = testa.readUInt32LE(4)
  const lunghezza = testa.readUInt32LE(12)

  const grezzo = Buffer.alloc(lunghezza)
  readSync(f, grezzo, 0, lunghezza, 16)
  const indice = JSON.parse(grezzo.toString('utf8'))

  const voce = indice.files?.dist?.files?.['versione.json']
  if (!voce) {
    console.error('Il pacchetto non contiene dist/versione.json.')
    console.error("Controlla che `files:` in electron-builder.yml lo nomini: senza, l'asar")
    console.error('prende tutto tranne lui e il pacchetto non sa da che commit viene.')
    process.exit(1)
  }

  const dati = Buffer.alloc(voce.size)
  readSync(f, dati, 0, voce.size, 8 + dimensioneHeader + Number(voce.offset))

  // Non ci si ferma ad averlo letto. Un offset sbagliato di pochi byte produce
  // testo che *sembra* il timbro — è successo — e uno script di verifica che
  // non verifica il proprio risultato non verifica niente.
  const testo = dati.toString('utf8')
  let timbro
  try {
    timbro = JSON.parse(testo)
  } catch {
    console.error('Il timbro non è JSON valido. Letto dall\'offset sbagliato?')
    console.error(testo.slice(0, 200))
    process.exit(1)
  }
  if (!timbro.versione || !('commit' in timbro)) {
    console.error('Il timbro non ha versione e commit:')
    console.error(testo.slice(0, 200))
    process.exit(1)
  }
  process.stdout.write(testo.trimEnd() + '\n')
} finally {
  closeSync(f)
}
