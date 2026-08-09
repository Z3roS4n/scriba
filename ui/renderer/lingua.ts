/**
 * La lingua dell'interfaccia: italiano, inglese, o come il sistema.
 *
 * **Due assi indipendenti, e non vanno confusi** (comportamento.md, 23). Questa
 * è la lingua del *chrome*: pulsanti, etichette, messaggi. La lingua della
 * *call* è un'altra cosa, sta in `stt.lingua`, e decide in che lingua escono
 * trascrizione, riassunto e task. Un'interfaccia in inglese sopra una call in
 * italiano è il caso normale, non un errore da correggere.
 *
 * Gemello di `tema.ts`, e per gli stessi motivi: tre bundle in tre processi,
 * quindi il valore iniziale arriva dal ponte (non da `GET /settings`, che
 * richiede il core già partito — nel frattempo la finestra sarebbe visibile
 * nella lingua sbagliata) e i cambi si propagano con un evento.
 *
 * A differenza del tema, che è un attributo sul documento, la lingua è **stato
 * di React**: cambiarla deve ridisegnare i testi. Da qui il contesto — senza,
 * i componenti sotto `memo` resterebbero nella lingua di prima, perché le loro
 * prop non sono cambiate. È il modo in cui una traduzione si dimentica un
 * pezzo di schermata e nessuno se ne accorge finché non lo guarda.
 */

import { createContext, useContext, useEffect, useState } from 'react'

export type Lingua = 'sistema' | 'it' | 'en'

const VALIDE = ['sistema', 'it', 'en'] as const

export function linguaValida(valore: unknown): Lingua {
  return (VALIDE as readonly string[]).includes(valore as string) ? (valore as Lingua) : 'sistema'
}

/** Cosa chiede il sistema operativo adesso. Tutto ciò che non è inglese
 *  ripiega su italiano: sono le due lingue che l'interfaccia parla. */
function linguaDiSistema(): 'it' | 'en' {
  return (navigator.language || 'it').toLowerCase().startsWith('en') ? 'en' : 'it'
}

export function risolvi(lingua: Lingua): 'it' | 'en' {
  return lingua === 'sistema' ? linguaDiSistema() : lingua
}

// ---------------------------------------------------------------- catalogo

/**
 * Le stringhe, in italiano.
 *
 * Piatto e per chiave, non annidato: annidando si finisce a discutere dove
 * mettere una stringa invece di scriverla, e il compilatore su un albero non
 * garantisce niente.
 */
const it = {
  'stato.pronto': 'Pronto',
  'stato.avvio': 'Avvio del core…',
  'stato.carico': 'Carico il modello…',
  'stato.registrazione': 'Registrazione',
  'stato.modello_assente': 'Modello non disponibile',

  'azione.registra': 'Registra',
  'azione.ferma': 'Ferma',
  'azione.esporta': 'Esporta',
  'azione.esportando': 'Esporto…',
  'azione.archivio': 'Archivio',
  'azione.impostazioni': 'Impostazioni',
  'azione.screenshot': 'Screenshot',
  'azione.schermo_n': 'Schermo {n}',
  'azione.salva': 'Salva',
  'azione.annulla': 'Annulla',
  'azione.chiudi': 'Chiudi',
  'azione.riprova': 'Riprova',
  'azione.modifica': 'Modifica',
  'azione.conferma': 'Conferma',
  'azione.scarta': 'Scarta',

  'finestra.riduci': 'Riduci a icona',
  'finestra.ingrandisci': 'Ingrandisci',
  'finestra.chiudi': 'Chiudi',

  'call.sezione': 'Call',
  'call.senza_titolo': 'Call #{n}',
  'call.senza_cliente': 'Senza cliente',
  'call.in_registrazione': 'in registrazione',
  'call.non_riuscita': 'non riuscita',
  'call.in_analisi': 'in analisi',
  'call.da_analizzare': 'da analizzare',
  'call.n_task': '{n} task',
  'call.n_da_confermare': '{n} da confermare',
  'call.nessun_impegno': 'nessun impegno',
  'call.vuoto': 'Nessuna call registrata.',
  'call.vuoto_nota': 'Le registrazioni restano su questo computer.',

  'trascrizione.io': 'Io',
  'trascrizione.altri': 'Altri',
  'trascrizione.ripresa': 'ripresa',
  'trascrizione.eco_righe': '{n} righe',
  'trascrizione.eco_riga': '1 riga',
  'trascrizione.eco_riprese': 'riprese dall’altoparlante',
  'trascrizione.eco_ripresa': 'ripresa dall’altoparlante',
  'trascrizione.eco_nota': 'tenute fuori da riassunto, note ed export',
  'trascrizione.scatto': 'Schermata condivisa · clicca per aprirla',
  'trascrizione.scatto_perso': 'Schermata condivisa · il file non è più al suo posto',

  'lingua.etichetta': 'Lingua dell’interfaccia',
  'lingua.nota':
    'Vale per pulsanti, etichette e messaggi. Non tocca la lingua delle call, che si sceglie in Trascrizione: un’interfaccia in inglese sopra una riunione in italiano è il caso normale.',
  'lingua.it': 'Italiano',
  'lingua.en': 'Inglese',
  'lingua.sistema': 'Come il sistema',

  // --- etichette di VALORI SALVATI -------------------------------------
  // Si traducono dove si mostrano, mai dove si confrontano: nel database e
  // nelle richieste restano `basso`, `alta`, `Voce 3`. Una tabella qui, e non
  // una maiuscola messa al valore, è tutta la differenza fra tradurre la vista
  // e rompere il confronto.
  'filtro.basso': 'Basso',
  'filtro.medio': 'Medio',
  'filtro.alto': 'Alto',

  'priorita.bassa': 'bassa',
  'priorita.media': 'media',
  'priorita.alta': 'alta',
  'priorita.critica': 'critica',
  'priorita.nessuna': 'nessuna priorità',

  'voce.n': 'Voce {n}',
  'voce.io': 'io',
  'voce.altri': 'altri',
  // --- impostazioni: le undici sezioni ---------------------------------
  'sez.motore': 'Motore di analisi',
  'sez.modelli': 'Modelli locali',
  'sez.trascrizione': 'Trascrizione',
  'sez.rilevamento': 'Rilevamento call',
  'sez.scorciatoie': 'Scorciatoie',
  'sez.aspetto': 'Aspetto',
  'sez.analisi': 'Analisi',
  'sez.clienti': 'Clienti',
  'sez.database': 'Database remoto',
  'sez.dati': 'Dati e privacy',
  'sez.export': 'Export',

  // --- archivio ---------------------------------------------------------
  'arch.titolo': 'Archivio',
  'arch.esci': 'torna alla call',
  'arch.cerca': 'Cerca nei titoli e in quello che è stato detto…',
  'arch.raggruppa': 'Raggruppa per cliente',
  'arch.per_ia': 'Per l’IA',
  'arch.n_call': '{n} call',
  'arch.ore': '{n} ore registrate',
  'arch.con_parola': '{n} con «{q}»',
  'arch.cerco': 'Cerco…',
  'arch.nessun_filtro': 'Nessuna call corrisponde a questi filtri.',
  'arch.nessuna': 'Nessuna call registrata: qui compariranno appena ne registri una.',

  'arch.stato.tutti': 'Qualsiasi stato',
  'arch.stato.analyzed': 'Analizzate',
  'arch.stato.recorded': 'Registrate',
  'arch.stato.failed': 'Analisi non riuscita',
  'arch.stato.recording': 'In corso',

  'arch.clienti.tutti': 'Tutti i clienti',
  'arch.periodo.sempre': 'Sempre',
  'arch.periodo.30': 'Ultimi 30 giorni',
  'arch.periodo.90': 'Ultimi 3 mesi',
  'arch.periodo.365': 'Ultimo anno',
  'data.oggi': 'oggi',
} as const

export type Chiave = keyof typeof it

/**
 * Le stringhe, in inglese.
 *
 * Il tipo obbliga a coprirle tutte: aggiungere una chiave all'italiano senza
 * tradurla non compila. È l'unica garanzia che regge nel tempo — una
 * traduzione dimenticata non si vede, esce in italiano e sembra una scelta.
 */
const en: Record<Chiave, string> = {
  'stato.pronto': 'Ready',
  'stato.avvio': 'Starting the core…',
  'stato.carico': 'Loading the model…',
  'stato.registrazione': 'Recording',
  'stato.modello_assente': 'Model unavailable',

  'azione.registra': 'Record',
  'azione.ferma': 'Stop',
  'azione.esporta': 'Export',
  'azione.esportando': 'Exporting…',
  'azione.archivio': 'Archive',
  'azione.impostazioni': 'Settings',
  'azione.screenshot': 'Screenshot',
  'azione.schermo_n': 'Screen {n}',
  'azione.salva': 'Save',
  'azione.annulla': 'Cancel',
  'azione.chiudi': 'Close',
  'azione.riprova': 'Try again',
  'azione.modifica': 'Edit',
  'azione.conferma': 'Confirm',
  'azione.scarta': 'Discard',

  'finestra.riduci': 'Minimise',
  'finestra.ingrandisci': 'Maximise',
  'finestra.chiudi': 'Close',

  'call.sezione': 'Calls',
  'call.senza_titolo': 'Call #{n}',
  'call.senza_cliente': 'No client',
  'call.in_registrazione': 'recording',
  'call.non_riuscita': 'failed',
  'call.in_analisi': 'analysing',
  'call.da_analizzare': 'to analyse',
  'call.n_task': '{n} tasks',
  'call.n_da_confermare': '{n} to confirm',
  'call.nessun_impegno': 'nothing to do',
  'call.vuoto': 'No calls recorded.',
  'call.vuoto_nota': 'Recordings stay on this computer.',

  'trascrizione.io': 'Me',
  'trascrizione.altri': 'Others',
  'trascrizione.ripresa': 'picked up',
  'trascrizione.eco_righe': '{n} lines',
  'trascrizione.eco_riga': '1 line',
  'trascrizione.eco_riprese': 'picked up from the speakers',
  'trascrizione.eco_ripresa': 'picked up from the speakers',
  'trascrizione.eco_nota': 'kept out of the summary, notes and exports',
  'trascrizione.scatto': 'Shared screen · click to open it',
  'trascrizione.scatto_perso': 'Shared screen · the file is no longer there',

  'lingua.etichetta': 'Interface language',
  'lingua.nota':
    'Applies to buttons, labels and messages. It does not touch the language of your calls, which is chosen under Transcription: an English interface over an Italian meeting is the normal case.',
  'lingua.it': 'Italian',
  'lingua.en': 'English',
  'lingua.sistema': 'Same as the system',

  'filtro.basso': 'Low',
  'filtro.medio': 'Medium',
  'filtro.alto': 'High',

  'priorita.bassa': 'low',
  'priorita.media': 'medium',
  'priorita.alta': 'high',
  'priorita.critica': 'critical',
  'priorita.nessuna': 'no priority',

  'voce.n': 'Voice {n}',
  'voce.io': 'me',
  'voce.altri': 'others',
  'sez.motore': 'Analysis engine',
  'sez.modelli': 'Local models',
  'sez.trascrizione': 'Transcription',
  'sez.rilevamento': 'Call detection',
  'sez.scorciatoie': 'Shortcuts',
  'sez.aspetto': 'Appearance',
  'sez.analisi': 'Analysis',
  'sez.clienti': 'Clients',
  'sez.database': 'Remote database',
  'sez.dati': 'Data and privacy',
  'sez.export': 'Export',

  'arch.titolo': 'Archive',
  'arch.esci': 'back to the call',
  'arch.cerca': 'Search titles and what was said…',
  'arch.raggruppa': 'Group by client',
  'arch.per_ia': 'For AI',
  'arch.n_call': '{n} calls',
  'arch.ore': '{n} hours recorded',
  'arch.con_parola': '{n} with “{q}”',
  'arch.cerco': 'Searching…',
  'arch.nessun_filtro': 'No call matches these filters.',
  'arch.nessuna': 'No calls recorded: they will show up here as soon as you record one.',

  'arch.stato.tutti': 'Any state',
  'arch.stato.analyzed': 'Analysed',
  'arch.stato.recorded': 'Recorded',
  'arch.stato.failed': 'Analysis failed',
  'arch.stato.recording': 'Recording',

  'arch.clienti.tutti': 'All clients',
  'arch.periodo.sempre': 'Any time',
  'arch.periodo.30': 'Last 30 days',
  'arch.periodo.90': 'Last 3 months',
  'arch.periodo.365': 'Last year',
  'data.oggi': 'today',
}

const CATALOGHI = { it, en } as const

/** Il contesto porta la lingua **risolta**: i componenti non devono sapere che
 *  «come il sistema» esiste. */
export const ContestoLingua = createContext<'it' | 'en'>('it')

export type Traduci = (chiave: Chiave, valori?: Record<string, string | number>) => string

function traduciCon(lingua: 'it' | 'en'): Traduci {
  return (chiave, valori) => {
    let testo: string = CATALOGHI[lingua][chiave]
    if (valori) {
      for (const [k, v] of Object.entries(valori)) testo = testo.split(`{${k}}`).join(String(v))
    }
    return testo
  }
}

/** La funzione di traduzione, legata alla lingua corrente. */
export function useT(): Traduci {
  return traduciCon(useContext(ContestoLingua))
}

/** Il tag BCP-47 per `Intl`: date, ore e numeri seguono la lingua
 *  dell'interfaccia (comportamento.md, 24). Le durate no — restano `mm:ss`,
 *  perché sono un minutaggio e non un orario. */
export function useLocale(): string {
  return useContext(ContestoLingua) === 'en' ? 'en-GB' : 'it-IT'
}

/**
 * Tiene la lingua allineata ovunque la si cambi, come `useTema` fa col tema.
 */
export function useLingua(): { lingua: Lingua; risolta: 'it' | 'en' } {
  const [lingua, setLingua] = useState<Lingua>(() => linguaValida(window.scriba.linguaIniziale))

  useEffect(() => {
    return window.scriba.on('lingua:cambiata', (nuova: unknown) => setLingua(linguaValida(nuova)))
  }, [])

  // Con «come il sistema» la lingua può cambiare senza che nessuno tocchi
  // Scriba. Windows non manda un evento per questo, ma il documento sì quando
  // la pagina si ricarica: qui basta rileggerla a ogni cambio di preferenza.
  const risolta = risolvi(lingua)

  useEffect(() => {
    document.documentElement.setAttribute('lang', risolta)
  }, [risolta])

  return { lingua, risolta }
}

// --------------------------------------------------- etichette di un valore

/**
 * L'etichetta di un valore salvato, presa da una tabella e non ricavata dal
 * valore stesso.
 *
 * Il filtro dell'eco mostrava `v[0].toUpperCase() + v.slice(1)`: funziona
 * finché l'interfaccia è italiana e il valore è italiano, cioè finché le due
 * cose sono la stessa. Tradotta, quella riga avrebbe scritto «Basso» sotto un
 * chrome inglese — oppure, provando a tradurre il valore, avrebbe mandato al
 * core una parola che il core non conosce.
 *
 * `sconosciuto` non è un caso teorico: la priorità la propone un modello, e al
 * primo «urgente» al posto di «alta» qui non c'è una chiave. Si mostra quello
 * che è arrivato, invece di lasciare un buco.
 */
export function etichettaValore(t: Traduci, prefisso: string, valore: string): string {
  const chiave = `${prefisso}.${valore}` as Chiave
  return chiave in it ? t(chiave) : valore
}

/** «Voce 3» / «Voice 3» composto dal numero, non dalla stringa salvata.
 *  Il core genera `Voce N` e lo rilegge con `SUBSTR(label, 6)`: quella
 *  stringa è un identificatore travestito da etichetta, e non va tradotta —
 *  va sostituita al momento di mostrarla. */
export function etichettaVoce(t: Traduci, numero: number | null, label: string): string {
  return numero == null ? label : t('voce.n', { n: numero })
}
