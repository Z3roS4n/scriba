/**
 * Le stringhe del processo principale: menu dell'area di notifica, suggerimenti,
 * titoli di finestra, la finestra d'errore all'avvio.
 *
 * È un terzo catalogo, e non è una duplicazione da eliminare: questo processo
 * non può usare quello del renderer — gira prima che una pagina esista, e le
 * sue stringhe finiscono in menu di sistema, non nel DOM — né quello del core,
 * che sta in un altro linguaggio e in un altro processo ancora.
 *
 * Quello che **non** si duplica è la regola con cui si decide la lingua:
 * `linguaEffettiva()` sta in index.ts, ed è la stessa che finisce
 * nell'intestazione delle richieste al core. Un secondo modo di scioglierla
 * vorrebbe dire, prima o poi, un tray in una lingua e un pannello nell'altra.
 */

const it = {
  'tray.apri': 'Apri Scriba',
  'tray.overlay': 'Trascrizione sovrapposta',
  'tray.screenshot': 'Screenshot',
  'tray.esci': 'Esci',
  'tray.tooltip': 'Scriba',
  'tray.tooltip_rec': 'Scriba — registrazione in corso',

  'finestra.impostazioni': 'Impostazioni',

  'errore.core_titolo': 'Scriba non riesce ad avviare il core',
} as const

type Chiave = keyof typeof it

const en: Record<Chiave, string> = {
  'tray.apri': 'Open Scriba',
  'tray.overlay': 'Transcript overlay',
  'tray.screenshot': 'Screenshot',
  'tray.esci': 'Quit',
  'tray.tooltip': 'Scriba',
  'tray.tooltip_rec': 'Scriba — recording',

  'finestra.impostazioni': 'Settings',

  'errore.core_titolo': 'Scriba cannot start the core',
}

const CATALOGHI = { it, en } as const

/**
 * La traduzione, nella lingua passata.
 *
 * Prende la lingua come argomento invece di leggersela da sola: chi chiama la
 * conosce già — è la stessa che va nell'intestazione — e una funzione che se
 * la va a prendere per conto suo è una funzione che può rispondere diversamente
 * dalla riga accanto.
 */
export function testo(lingua: string, chiave: Chiave): string {
  const catalogo = lingua === 'en' ? CATALOGHI.en : CATALOGHI.it
  return catalogo[chiave]
}
