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
  'arch.per_ia': "Per l'IA",
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
  // --- database remoto ---------------------------------------------------
  'db.titolo': 'Database remoto',
  'db.esce': 'La trascrizione, se la includi, esce da questo computer.',
  'db.in_chiaro':
    "L'indirizzo è salvato in chiaro: la cifratura di Windows non ha risposto quando è stato collegato. Chi legge quel file entra nel database.",
  'db.collegato': 'Collegato',
  'db.scollega': 'Scollega',
  'db.cosa_manda': 'Cosa viene mandato',
  'db.cambia': 'Cambia',
  'db.auto': 'Sincronizza da sola a fine analisi',
  'db.auto_nota':
    'Una registrazione in corso non aspetta mai il database: se la rete manca, si riprova dopo.',
  'db.pregresso': 'Il pregresso',
  'db.pregresso_nota':
    'Manda tutte le call non ancora sincronizzate. Si può rifare quante volte si vuole.',
  'db.indirizzo': 'Indirizzo',
  'db.come': 'Come ci si collega',
  'db.prova': 'Prova il collegamento',
  'db.prova_nota':
    'Non salva niente: si collega, chiede la versione e gli schemi, e riferisce.',
  'db.schema': 'In quale schema scrivere',
  'db.schema_nota':
    'Gli schemi di sistema non sono in elenco: non sarebbero una scelta sensata.',
  'db.tabelle': 'Le tabelle',
  'db.tabelle_nota': 'Le crea Scriba, oppure gliele indichi tu se ce le hai già.',
  'db.creale': 'Creale tu',
  'db.ce_le_ho': 'Ce le ho già',
  'db.avanti': 'Avanti',
  'db.indietro': 'Indietro',
  'db.quali_dati': 'Quali dati mandare',
  'db.quali_dati_nota': 'Quello che non spunti non esce da questo computer.',
  'db.ddl': 'Cosa verrà eseguito',
  'db.ddl_nota':
    "Nessun DROP, nessun ALTER: su un database che è tuo si aggiunge, non si sistema d'ufficio.",
  'db.chiave_nota_1': 'I campi con',
  'db.chiave_nota_2':
    'servono a riconoscere una riga già inviata: senza, ogni sincronizzazione ne aggiungerebbe di nuove.',
  'db.prefisso': 'Prefisso dei nomi delle tabelle',
  // --- rilevamento call --------------------------------------------------
  'ril.vede_ora':
    'Cosa sta vedendo adesso',
  'ril.vede_nota':
    'Se una riunione non viene riconosciuta, qui si legge quale delle condizioni non è soddisfatta invece di doverlo indovinare.',
  'ril.mostra':
    'Mostra',
  'ril.aggiorna':
    'Si aggiorna da solo ogni due secondi, finché resta aperto.',
  'ril.nascondi':
    'Nascondi',
  'ril.chiedo':
    'Chiedo al core…',
  'ril.spento':
    'Il rilevamento è spento nell\'interruttore qui sopra: nessuna applicazione viene osservata, e nessuna riunione può essere proposta.',
  'ril.sonda_muta':
    'La sonda è partita ma non ha ancora riferito niente. Se resta così per più di qualche secondo non è una stanza silenziosa: è la sonda che non sta parlando.',
  'ril.nessuna_app':
    'Nessuna applicazione sta usando il microfono in questo momento. Entra in una riunione e questa riga cambia entro un paio di secondi: se non cambia, il problema è a monte del rilevamento.',
  'ril.titolo':
    'Rilevamento automatico delle call',
  'ril.accorgiti':
    'Accorgiti da solo quando entro in call',
  'ril.accorgiti_nota':
    'Guarda quali applicazioni stanno usando il microfono. Non legge il contenuto della riunione.',
  'ril.aspetta':
    'Aspetta prima di propormelo',
  'ril.aspetta_nota':
    'Evita la proposta per le chiamate di dieci secondi.',
  'ril.cosa_fare':
    'Cosa fare quando la rileva',
  'ril.cosa_fare_nota':
    'Anche avviando da sola, il consenso resta obbligatorio: la registrazione parte solo dopo la spunta.',
  'ril.proponi':
    'Proponi',
  'ril.avvia':
    'Avvia da sola',
  // --- Notion ------------------------------------------------------------
  'ntn.manda':
    'Manda le task a Notion',
  'ntn.esce':
    'I dati della call escono dal computer verso Notion.',
  'ntn.cambia_colonne':
    'Cambia le colonne',
  'ntn.cambia_db':
    'Cambia database',
  'ntn.scollega':
    'Scollega',
  'ntn.collega':
    'Collega Notion',
  'ntn.token':
    'Il token dell’integrazione',
  'ntn.token_nota':
    'Si crea su notion.so/my-integrations. Poi va condiviso, dal menù «…» della pagina o del database, con l’integrazione appena creata: senza quel passaggio Notion non la lascia entrare.',
  'ntn.annulla':
    'Annulla',
  'ntn.quale_db':
    'Quale database?',
  'ntn.quale_db_nota':
    'Solo quelli che hai condiviso con l’integrazione. Se il tuo non c’è, aprilo in Notion e condividilo, oppure fatene creare uno nuovo con le colonne che ti servono.',
  'ntn.nessun_db':
    'Nessun database condiviso con l’integrazione.',
  'ntn.creane':
    'Creane uno nuovo',
  'ntn.colonne':
    'Cosa va in quale colonna',
  'ntn.db_nuovo':
    'Un database nuovo',
  'ntn.db_nuovo_nota':
    'Lo crea Scriba dentro una pagina che gli hai condiviso, con le sole colonne che scegli qui.',
  'ntn.dentro_pagina':
    'DENTRO QUALE PAGINA',
  'ntn.nome_db':
    'NOME DEL DATABASE',
  'ntn.colonne_label':
    'COLONNE',
  'ntn.indietro':
    'Indietro',
  // --- dati e privacy ----------------------------------------
  'dat.versione':
    'Versione',
  'dat.titolo':
    'Dati e privacy',
  'dat.apri':
    'Apri',
  'dat.cancellazioni':
    'CANCELLAZIONI · NON SI TORNA INDIETRO',
  'dat.elimina_audio':
    'Elimina l’audio, tieni la trascrizione',
  'dat.elimina_audio_nota':
    'Libera quasi tutto lo spazio. Le task e le loro prove restano, ma non si potrà più riascoltare la frase originale.',
  'dat.conferma_elimina':
    'Conferma: elimina',
  'dat.elimina_audio_btn':
    'Elimina l’audio',
  'dat.elimina_tutto':
    'Elimina tutto di una call',
  'dat.elimina_tutto_nota':
    'Audio, trascrizione, screenshot, task. Verrà chiesto quale call e poi una conferma scritta.',
  'dat.scegli_call':
    'Scegli una call',
  'dat.quale_call':
    'Quale call?',
  'dat.verra_cancellato':
    'Verrà cancellato tutto: audio, trascrizione, screenshot e task.',
  'dat.nessuna_call':
    'Nessuna call registrata.',
  'dat.annulla':
    'Annulla',
  'dat.indietro':
    'Indietro',
  'dat.elimina_def':
    'Elimina definitivamente',

  // --- rassegna ----------------------------------------------
  'ras.titolo':
    'Rassegna',
  'ras.esci':
    'torna alla lista',
  'ras.trascrizione':
    'Trascrizione',
  'ras.ferma':
    'ferma sulle righe citate',
  'ras.carico':
    'Carico…',
  'ras.carico_nota':
    'Sto leggendo le task di questa call.',
  'ras.nessuna':
    'Nessuna task da rivedere',
  'ras.nessuna_nota':
    'Questa call non ha task in sospeso.',
  'ras.modifica':
    'Modifica',
  'ras.annulla':
    'Annulla',
  'ras.salva':
    'Salva',
  'ras.dedotta':
    'Dedotta. Nessuna frase della riunione la sostiene.',
  'ras.conferma':
    'Conferma',
  'ras.scarta':
    'Scarta',
  'ras.campo.titolo': 'Titolo',
  'ras.campo.assignee': 'Responsabile',
  'ras.campo.scadenza': 'Scadenza',
  'ras.campo.priorita': 'Priorità',
  'ras.task_n_di': 'Task {i} di {n}',
  'ras.di': '{i} di {n}',
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
  'db.titolo': 'Remote database',
  'db.esce': 'The transcript, if you include it, leaves this computer.',
  'db.in_chiaro':
    'The address is stored in the clear: Windows encryption did not answer when it was connected. Whoever reads that file gets into the database.',
  'db.collegato': 'Connected',
  'db.scollega': 'Disconnect',
  'db.cosa_manda': 'What gets sent',
  'db.cambia': 'Change',
  'db.auto': 'Sync by itself when an analysis finishes',
  'db.auto_nota':
    'A recording in progress never waits for the database: if the network is down, it retries later.',
  'db.pregresso': 'The backlog',
  'db.pregresso_nota':
    'Sends every call not yet synced. You can run it as many times as you like.',
  'db.indirizzo': 'Address',
  'db.come': 'How to connect',
  'db.prova': 'Test the connection',
  'db.prova_nota':
    'Saves nothing: it connects, asks for the version and the schemas, and reports back.',
  'db.schema': 'Which schema to write to',
  'db.schema_nota': 'System schemas are not listed: they would not be a sensible choice.',
  'db.tabelle': 'The tables',
  'db.tabelle_nota': 'Scriba creates them, or you point it at yours if you already have them.',
  'db.creale': 'Create them',
  'db.ce_le_ho': 'I already have them',
  'db.avanti': 'Next',
  'db.indietro': 'Back',
  'db.quali_dati': 'Which data to send',
  'db.quali_dati_nota': 'Anything you leave unticked does not leave this computer.',
  'db.ddl': 'What will be run',
  'db.ddl_nota':
    'No DROP, no ALTER: on a database that is yours you add, you do not tidy up after anyone.',
  'db.chiave_nota_1': 'Fields marked',
  'db.chiave_nota_2':
    'identify a row already sent: without them every sync would add new ones.',
  'db.prefisso': 'Table name prefix',
  'ril.vede_ora':
    'What it is seeing right now',
  'ril.vede_nota':
    'If a meeting is not recognised, this says which condition is not met instead of leaving you to guess.',
  'ril.mostra':
    'Show',
  'ril.aggiorna':
    'It refreshes by itself every two seconds, while it stays open.',
  'ril.nascondi':
    'Hide',
  'ril.chiedo':
    'Asking the core…',
  'ril.spento':
    'Detection is off in the switch above: no application is being watched, and no meeting can be proposed.',
  'ril.sonda_muta':
    'The probe started but has not reported anything yet. If it stays like this for more than a few seconds it is not a quiet room: it is the probe not talking.',
  'ril.nessuna_app':
    'No application is using the microphone right now. Join a meeting and this line changes within a couple of seconds: if it does not, the problem is upstream of detection.',
  'ril.titolo':
    'Automatic call detection',
  'ril.accorgiti':
    'Notice by yourself when I join a call',
  'ril.accorgiti_nota':
    'It looks at which applications are using the microphone. It does not read the content of the meeting.',
  'ril.aspetta':
    'Wait before offering',
  'ril.aspetta_nota':
    'Avoids offering for ten-second calls.',
  'ril.cosa_fare':
    'What to do when it detects one',
  'ril.cosa_fare_nota':
    'Even when starting by itself, consent stays mandatory: recording only begins after the tick.',
  'ril.proponi':
    'Offer',
  'ril.avvia':
    'Start by itself',
  'ntn.manda':
    'Send tasks to Notion',
  'ntn.esce':
    'The call data leaves the computer, towards Notion.',
  'ntn.cambia_colonne':
    'Change the columns',
  'ntn.cambia_db':
    'Change database',
  'ntn.scollega':
    'Disconnect',
  'ntn.collega':
    'Connect Notion',
  'ntn.token':
    'The integration token',
  'ntn.token_nota':
    'You create it at notion.so/my-integrations. Then it has to be shared, from the «…» menu of the page, with the integration you just made.',
  'ntn.annulla':
    'Cancel',
  'ntn.quale_db':
    'Which database?',
  'ntn.quale_db_nota':
    'Only the ones you shared with the integration. If yours is not here, open it on Notion and share it.',
  'ntn.nessun_db':
    'No database shared with the integration.',
  'ntn.creane':
    'Create a new one',
  'ntn.colonne':
    'What goes in which column',
  'ntn.db_nuovo':
    'A new database',
  'ntn.db_nuovo_nota':
    'Scriba creates it inside a page you have shared with it, with only the columns it needs.',
  'ntn.dentro_pagina':
    'INSIDE WHICH PAGE',
  'ntn.nome_db':
    'DATABASE NAME',
  'ntn.colonne_label':
    'COLUMNS',
  'ntn.indietro':
    'Back',
  'dat.versione':
    'Version',
  'dat.titolo':
    'Data and privacy',
  'dat.apri':
    'Open',
  'dat.cancellazioni':
    'DELETIONS · THERE IS NO GOING BACK',
  'dat.elimina_audio':
    'Delete the audio, keep the transcript',
  'dat.elimina_audio_nota':
    'Frees almost all the space. Tasks and their evidence stay, but the original sentence can no longer be listened to.',
  'dat.conferma_elimina':
    'Confirm: delete',
  'dat.elimina_audio_btn':
    'Delete the audio',
  'dat.elimina_tutto':
    'Delete everything about a call',
  'dat.elimina_tutto_nota':
    'Audio, transcript, screenshots, tasks. It will ask which call and then for a written confirmation.',
  'dat.scegli_call':
    'Choose a call',
  'dat.quale_call':
    'Which call?',
  'dat.verra_cancellato':
    'Everything will be deleted: audio, transcript, screenshots and tasks.',
  'dat.nessuna_call':
    'No calls recorded.',
  'dat.annulla':
    'Cancel',
  'dat.indietro':
    'Back',
  'dat.elimina_def':
    'Delete permanently',

  'ras.titolo':
    'Review',
  'ras.esci':
    'back to the list',
  'ras.trascrizione':
    'Transcript',
  'ras.ferma':
    'held on the quoted lines',
  'ras.carico':
    'Loading…',
  'ras.carico_nota':
    'Reading this call’s tasks.',
  'ras.nessuna':
    'No task to review',
  'ras.nessuna_nota':
    'This call has no pending tasks.',
  'ras.modifica':
    'Edit',
  'ras.annulla':
    'Cancel',
  'ras.salva':
    'Save',
  'ras.dedotta':
    'Inferred. No sentence in the meeting supports it.',
  'ras.conferma':
    'Confirm',
  'ras.scarta':
    'Discard',
  'ras.campo.titolo': 'Title',
  'ras.campo.assignee': 'Assignee',
  'ras.campo.scadenza': 'Due',
  'ras.campo.priorita': 'Priority',
  'ras.task_n_di': 'Task {i} of {n}',
  'ras.di': '{i} of {n}',
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
