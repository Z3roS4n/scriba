/**
 * Scrive `dist/versione.json` con versione, commit e data della compilazione.
 *
 * La versione da sola non basta a distinguere due build: durante lo sviluppo se
 * ne fanno molte con lo stesso numero, ed è esattamente la situazione in cui
 * serve sapere quale si sta usando. Il commit lo dice esattamente.
 *
 * Il numero viene da `package.json` e da nessun'altra parte: è quello che legge
 * anche electron-builder per il nome dell'installer e per le proprietà del file
 * su Windows, quindi tenerne una seconda copia significherebbe vederle
 * divergere.
 *
 * Se git non risponde — sorgenti scompattati da uno zip, per dire — il commit
 * resta null. Un valore inventato sarebbe peggio di un valore assente.
 */

import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const qui = dirname(fileURLToPath(import.meta.url))
const radice = join(qui, '..')

const versione = JSON.parse(readFileSync(join(radice, 'package.json'), 'utf8')).version

function daGit(...args) {
  try {
    return execFileSync('git', args, { cwd: radice, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
  } catch {
    return null
  }
}

const commit = daGit('rev-parse', '--short', 'HEAD')
// Un albero sporco vuol dire che questa build contiene modifiche che non stanno
// in nessun commit: chi la sta usando deve poterlo sapere.
const pulito = commit ? daGit('status', '--porcelain') === '' : null

const dati = {
  versione,
  commit,
  pulito,
  costruito_il: new Date().toISOString(),
}

mkdirSync(join(radice, 'dist'), { recursive: true })
writeFileSync(join(radice, 'dist', 'versione.json'), JSON.stringify(dati, null, 2), 'utf8')
console.log(`  versione ${versione}${commit ? ` (${commit}${pulito === false ? '+modifiche' : ''})` : ''}`)
