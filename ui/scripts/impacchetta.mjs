/**
 * Costruisce l'installer, firmandolo se c'è di che firmare.
 *
 * Esiste per una ragione sola: **dire ad alta voce quando non sta firmando**.
 * Un installer non firmato non è un installer con un difetto estetico — su
 * Windows 11 con Smart App Control attivo viene bloccato, senza «esegui
 * comunque». Costruirne uno in silenzio significa scoprirlo dall'altra parte,
 * quando qualcuno prova a installarlo.
 *
 * Le due strade, in ordine di quanto costano:
 *
 * - **Azure Artifact Signing** (ex Trusted Signing), ~10 $/mese, nessun token
 *   fisico. Si configura con `SCRIBA_AZURE_*` più le credenziali Entra che
 *   legge la libreria di Azure (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`,
 *   `AZURE_CLIENT_SECRET`). Come **privato** è disponibile solo in USA e
 *   Canada; come organizzazione anche in UE.
 * - **Un certificato da una CA** (OV: 150-300 $/anno, con token hardware).
 *   electron-builder lo prende da solo da `CSC_LINK` e `CSC_KEY_PASSWORD`:
 *   qui non c'è niente da configurare, si controlla solo che ci sia.
 *
 * Quello che **non** si fa qui: firmare con un certificato autofirmato. Non
 * toglie nessun avviso — anzi, Windows lo tratta peggio del non firmato —
 * e darebbe l'illusione che il problema sia risolto.
 *
 * Nota che vale la pena sapere prima di spendere: nessuna delle due strade
 * porta a zero avvisi da subito. La firma dà un'identità stabile su cui la
 * reputazione si accumula, e i primi utenti l'avviso lo vedono comunque.
 * L'unica che lo elimina è pubblicare in MSIX sul Microsoft Store, dove è
 * Microsoft a rifirmare il pacchetto (vedi #57).
 */

import { spawnSync } from 'node:child_process'

const env = process.env

const azure = {
  endpoint: env.SCRIBA_AZURE_ENDPOINT,
  account: env.SCRIBA_AZURE_ACCOUNT,
  profilo: env.SCRIBA_AZURE_PROFILO,
  publisher: env.SCRIBA_AZURE_PUBLISHER,
}
const conAzure = Object.values(azure).every(Boolean)
const conCertificato = Boolean(env.CSC_LINK && env.CSC_KEY_PASSWORD)

// Configurata a metà è peggio che non configurata: si fermerebbe a metà build,
// o peggio ne produrrebbe una non firmata credendo di averla firmata.
const azureParziale = !conAzure && Object.values(azure).some(Boolean)
if (azureParziale) {
  const mancanti = Object.entries(azure)
    .filter(([, v]) => !v)
    .map(([k]) => `SCRIBA_AZURE_${k.toUpperCase()}`)
  console.error(`\nFirma Azure configurata a metà: mancano ${mancanti.join(', ')}.`)
  process.exit(1)
}
if (conAzure && conCertificato) {
  console.error('\nSono configurate due firme insieme (Azure e CSC_LINK). Tienine una.')
  process.exit(1)
}

const argomenti = ['electron-builder', '--config', 'electron-builder.yml']

if (conAzure) {
  console.log(`\n  firma: Azure Artifact Signing — ${azure.publisher}`)
  argomenti.push(
    `-c.win.azureSignOptions.endpoint=${azure.endpoint}`,
    `-c.win.azureSignOptions.codeSigningAccountName=${azure.account}`,
    `-c.win.azureSignOptions.certificateProfileName=${azure.profilo}`,
    `-c.win.azureSignOptions.publisherName=${azure.publisher}`,
  )
} else if (conCertificato) {
  // electron-builder legge CSC_LINK/CSC_KEY_PASSWORD da sé: qui si dice solo
  // che sta succedendo, perché il suo output non è esplicito.
  console.log('\n  firma: certificato da CSC_LINK')
} else {
  console.log(
    [
      '',
      '  ┌─ NON FIRMATO ─────────────────────────────────────────────────┐',
      '  │ Windows 11 con Smart App Control attivo blocca questo file:   │',
      '  │ non è un avviso da saltare, è un rifiuto.                     │',
      '  │                                                               │',
      '  │ Va bene per provare in locale. Per darlo a qualcuno serve un  │',
      '  │ certificato: vedi issue #57 e 10-packaging.md.                │',
      '  └───────────────────────────────────────────────────────────────┘',
      '',
    ].join('\n'),
  )
}

const esito = spawnSync('npx', argomenti, { stdio: 'inherit', shell: true })
process.exit(esito.status ?? 1)
