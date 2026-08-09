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
  // --- overlay ----------------------------------------
  'ovl.salvato':
    'Salvato nella trascrizione',
  'ovl.scatta':
    'Scatta',
  'ovl.ferma':
    'Ferma',
  'ovl.registra':
    'Registra',
  'ovl.scatto_nota':
    'Lo screenshot finisce nella trascrizione al minuto in cui è stato preso.',
  'ovl.fermo':
    'Non sto registrando.',

  // --- Clienti ----------------------------------------
  'cli.titolo':
    'Clienti',
  'cli.aggiungi':
    'Aggiungi un cliente',
  'cli.aggiungi_nota':
    "Serve a raggruppare le call nell'archivio. L'attribuzione si fa da lì, dove le call si vedono tutte insieme.",
  'cli.aggiungi_btn':
    'Aggiungi',
  'cli.carica':
    'Carica un elenco',
  'cli.scegli_file':
    'Scegli un file',
  'cli.vuoto':
    "Nessun cliente. Finché non ce n'è, l'archivio funziona lo stesso: le call restano cercabili per testo e per data.",
  'cli.salva':
    'Salva',
  'cli.annulla':
    'Annulla',
  'cli.archiviato':
    '· archiviato',
  'cli.rinomina':
    'Rinomina',
  'cli.elimina':
    'Elimina',

  // --- Dialoghi ----------------------------------------
  'dlg.consenso_titolo':
    'Registrare questa call',
  'dlg.consenso_cosa':
    "Verranno registrati il tuo microfono e l'audio del computer.",
  'dlg.consenso_spunta':
    'Ho avvisato le persone in call che sto registrando.',
  'dlg.consenso_nota':
    "Registrare gli altri significa trattare i loro dati personali. Questa spunta viene annotata nella sessione, ma non sostituisce l'averglielo detto.",
  'dlg.annulla':
    'Annulla',
  'dlg.registra':
    'Registra',
  'dlg.rilevata':
    "Posso registrarla. Include l'audio degli altri partecipanti, non solo la tua voce.",
  'dlg.no_grazie':
    'No grazie',
  'dlg.torna':
    'torna alla prossima call',
  // --- Modelli -------------------------------------
  'mod.titolo':
    'Modelli locali',
  'mod.spazio':
    'Spazio su disco',
  'mod.apri_cartella':
    'Apri la cartella',
  'mod.download_nota':
    'Un download si può sospendere e riprendere: riparte da dove si era fermato, anche dopo aver chiuso l’applicazione. A fine scaricamento il file viene verificato, e l’esito si vede qui.',
  'mod.scarica':
    'Scarica',
  'mod.sospendi':
    'Sospendi',
  'mod.riprendi':
    'Riprendi',
  'mod.avvia':
    'Avvia',
  'mod.elimina':
    'Elimina',
  'mod.ferma':
    'Ferma',

  // --- Trascrizione --------------------------------
  'tra.nessuna_call':
    'Nessuna call',
  'tra.mai_registrato':
    'Non hai ancora registrato niente',
  'tra.mai_registrato_nota':
    'Avvia la registrazione quando entri in una call. Sentirai il tuo microfono e l’audio del computer, così la trascrizione contiene tutti.',
  'tra.registra':
    'Registra',
  'tra.io':
    'Io',
  'tra.altri':
    'Altri',
  'tra.nomina_voci':
    'DAI UN NOME ALLE VOCI',
  'tra.in_ascolto':
    'In ascolto. Nessuno ha ancora parlato.',
  'tra.nessuna_trascrizione':
    'Nessuna trascrizione per questa call.',
  'tra.eco_nota':
    'tenute fuori da riassunto, note ed export',
  'tra.scatto_alt':
    'Schermata condivisa al minuto {t}',

  // --- Analisi -------------------------------------
  'ana.titolo':
    'Analisi',
  'ana.quando':
    'Quando analizzare',
  'ana.quando_nota':
    'A fine call parte da sola e la trovi pronta. A richiesta decidi tu di volta in volta.',
  'ana.fine_call':
    'A fine call',
  'ana.richiesta':
    'A richiesta',
  'ana.note':
    'Note incrementali durante la call',
  'ana.note_nota':
    'Un riassunto parziale ogni dieci minuti, mentre si parla.',
  'ana.note_rete':
    'Con un motore in rete significa mandare fuori la trascrizione più volte durante la riunione, non una sola volta alla fine.',
  'ana.ogni_quanto':
    'Ogni quanto',
  'ana.ogni_quanto_nota':
    'Su una call più corta dell’intervallo non ne esce nessuna: è il motivo più comune per cui sembra che non funzionino.',

  // --- Motore --------------------------------------
  'mot.titolo':
    'Motore di analisi',
  'mot.titolo_nota':
    'Chi legge la trascrizione e ne ricava riassunto, punti salienti e task. Se ne può usare uno solo alla volta.',
  'mot.in_caricamento':
    'Il modello si sta caricando in memoria. Diventa selezionabile da solo appena risponde: non serve riaprire questa finestra.',
  'mot.salva':
    'Salva',
  'mot.annulla':
    'Annulla',
  'mot.serve_chiave':
    'Serve una chiave API',
  'mot.inserisci':
    'Inserisci la chiave',

  // --- overlay -------------------------------------
  'ovl.nome':
    'Scriba',

  // --- Rifinitura ----------------------------------
  'rif.interrompi':
    'Interrompi',
  'rif.gia_in_corso':
    'C’è già una rifinitura in corso, su un’altra call.',
  'rif.rifai':
    'Rifai',
  'rif.durata':
    'Durata stimata',
  'rif.rifai_trascrizione':
    'Rifai la trascrizione',

  // --- Archivio ------------------------------------
  'arc2.ia_nota':
    "Ogni citazione accanto a ciò che sostiene, e detto chiaro quali impegni una fonte non ce l'hanno. Da incollare in un modello.",
  'arc2.integrale':
    'Trascrizione integrale',
  'arc2.mostra':
    'Mostra',
  'arc2.esc':
    'Esc',

  // --- Export --------------------------------------
  'exp.titolo':
    'Export',
  'exp.cartella':
    'Cartella predefinita',
  'exp.cambia':
    'Cambia',
  'exp.formato':
    'Formato',
  'exp.formato_nota':
    "Il markdown contiene anche i minuti delle prove. Il testo è la trascrizione pulita, il JSON porta tutto — comprese le prove — in una forma per un programma. «Per l'IA» mette ogni citazione accanto a ciò che sostiene, invece di un riferimento da incrociare, e dice quali impegni una fonte non ce l'hanno: è fatto per essere incollato in un modello. Per esportarne più di una insieme c'è l'archivio.",

  // --- index ---------------------------------------
  'idx.apri_cartella':
    'Apri la cartella',

  // --- Scorciatoie ---------------------------------
  'sco.titolo':
    'Scorciatoie',
  'sco.titolo_nota':
    'Si premono, non si scrivono: clicca il campo e digita la combinazione. Se è già presa da un’altra applicazione lo diciamo subito, perché Windows la rifiuta in silenzio.',
  'sco.ripristina':
    'Ripristina',
  'sco.gia_usata':
    'Già usata da un’altra applicazione. Windows la rifiuta in silenzio: finché non la cambi, il tasto non fa niente.',

  // --- Aspetto -------------------------------------
  'asp.titolo':
    'Aspetto',
  'asp.tema':
    'Tema',
  'asp.tema_nota':
    '«Come il sistema» segue Windows, anche quando cambia da solo al tramonto. Vale subito, senza riavviare. La striscia di trascrizione resta scura in ogni caso: sta sopra la finestra della riunione, e lì il bianco abbaglia.',

  // --- Notion --------------------------------------
  'ntn2.annulla':
    'Annulla',

  // --- Impostazioni --------------------------------
  'imp.titolo':
    'Impostazioni',
  'imp.carico':
    'Caricamento delle impostazioni…',
  'imp.chiudi':
    'Chiudi',

  // --- Prove ---------------------------------------
  'prv.titolo':
    'PROVE',
  'prv.nota':
    'Ogni campo della task viene da una di queste frasi. Se una prova non regge, il campo va corretto.',

  // --- NotaDiLavoro --------------------------------
  'not.titolo':
    'NOTA DI LAVORO',
  'not.aggiorno':
    'sto aggiornando…',

  // --- Rilevamento ---------------------------------
  'ril2.vede':
    'Cosa sta vedendo adesso',

  // --- Rassegna ------------------------------------
  'ras2.esc':
    'Esc',

  // --- Select --------------------------------------
  'sel.vuoto':
    'Nessuna opzione disponibile',

  // --- Topbar --------------------------------------
  'top.nome':
    'Scriba',
  // --- Analisi.tsx ------------------------
  'pan.da_confermare':
    'task da confermare',
  'pan.rassegna':
    'Passa in rassegna',
  'pan.conferma':
    'Conferma',
  'pan.scarta':
    'Scarta',
  'pan.modifica':
    'Modifica',
  'pan.annulla':
    'Annulla',
  'pan.no_pyannote':
    'Distinguere le voci dentro «altri» non è disponibile: manca pyannote.audio, non incluso nel pacchetto. Va installato a parte.',
  'pan.voci_distinte':
    'voci distinte',
  'pan.durata_stimata':
    'Durata stimata',
  'pan.misurati':
    'Misurati davvero su questa macchina. Gira in locale: nessun dato esce dal computer. Puoi chiudere la finestra, il lavoro continua e lo ritrovi finito.',
  'pan.avvia':
    'Avvia',
  'pan.riprova':
    'Riprova',
  'pan.distingui':
    'Distingui le voci',
  'pan.label':
    'ANALISI',
  'pan.scegli_call':
    'Seleziona una call per vederne l\'analisi.',
  'pan.a_call_finita':
    'Si fa a call finita. Riassunto, punti salienti e task su tutta la registrazione, non a pezzi.',
  'pan.label_in_corso':
    'ANALISI IN CORSO',
  'pan.puoi_chiudere':
    'Puoi chiudere la finestra.',
  'pan.lavoro_continua':
    'Il lavoro continua e lo ritrovi finito. Ti avvisiamo quando è pronto.',
  'pan.interrompi':
    'Interrompi',
  'pan.titolo':
    'Analisi',
  'pan.carico':
    'Carico l\'analisi…',
  'pan.non_analizzata':
    'Questa call non è ancora stata analizzata.',
  'pan.analizza':
    'Analizza la call',
  'pan.motore':
    'Motore',
  'pan.costo':
    'Costo stimato',
  'pan.rianalizza':
    'Rianalizza',
  'pan.riassunto':
    'Riassunto',
  'pan.salienti':
    'Punti salienti',
  'pan.task':
    'Task',
  'pan.nessun_impegno':
    'Nessun impegno individuato.',

  // --- impostazioni/Trascrizione.tsx ------------------------
  'tra2.titolo':
    'Trascrizione',
  'tra2.lingua':
    'Lingua delle call',
  'tra2.lingua_nota':
    'Vale per la trascrizione e per quello che ne viene ricavato: riassunto, punti salienti e task escono in questa lingua. Le altre vengono riconosciute lo stesso, ma con più errori sui nomi.',
  'tra2.microfono':
    'Microfono',
  'tra2.microfono_nota':
    'Registra la tua voce.',
  'tra2.loopback':
    'Audio del computer',
  'tra2.loopback_nota':
    'Registra la voce degli altri. Senza questo si sente solo te.',
  'tra2.filtro':
    'Filtro dell’eco',
  'tra2.filtro_nota':
    'Riconosce quando il microfono riprende l’altoparlante. Se alzi troppo, le sovrapposizioni di voce si perdono.',
  'tra2.dopo':
    'Dopo la call',
  'tra2.rifai':
    'Rifai la trascrizione da sola',
  'tra2.nomi':
    'Nomi propri',
  'tra2.glossario':
    'Glossario',
  'tra2.glossario_nota':
    'I nomi che il modello non conosce li indovina da capo a ogni frase, e ogni volta in modo diverso: nella stessa call «Clotilde» diventa Tilde, Cotilde e Protile. Scrivili qui, uno per riga, e vengono rimessi a posto a frase finita. Il testo di partenza resta salvato.',
  'tra2.anche_clienti':
    'Anche i clienti',
  'tra2.anche_clienti_nota':
    'I nomi dell’anagrafica entrano nel glossario da soli, senza riscriverli qui.',
  'tra2.quanto':
    'Quanto insistere',

  // --- attributi che si leggono ------------
  'ovl.ingrandisci':
    'Ingrandisci la striscia',
  'ovl.riduci':
    'Riduci la striscia',
  'ovl.chiudi':
    'Chiudi',
  'ovl.scatto_n':
    'Scatta {n}',
  'idx.nascondi_call':
    'Nascondi elenco call',
  'idx.mostra_call':
    'Mostra elenco call',
  'idx.nascondi_analisi':
    'Nascondi pannello analisi',
  'idx.mostra_analisi':
    'Mostra pannello analisi',
  'rif.conferma_nota':
    'Ripassa ogni riga con un modello più preciso, a cui la lingua si può imporre davvero: è la correzione per le frasi finite in un’altra lingua. Il testo di adesso resta salvato. Gira in locale, e puoi chiudere la finestra.',
  'rif.avvia':
    'Avvia',
  'rif.annulla':
    'Annulla',
  'arch.includi_integrale':
    'Includi la trascrizione integrale',
  'dlg.esempio_titolo':
    'Revisione sprint 24',
  'cli.ph_nome':
    'Nome',
  'mot.ph_chiave':
    'Chiave API',
  'prv.chiudi':
    'Chiudi le prove',
  'tra.ph_nome_vero':
    'nome vero',

  // --- pannello analisi, dentro le espressioni --------
  'pan.chi':
    'chi',
  'pan.entro':
    'entro',
  'pan.non_detto':
    'non detto',
  'pan.non_detta':
    'non detta',
  'pan.solo_a_voce':
    'solo a voce: «{q}»',
  'pan.prova_1':
    '1 prova',
  'pan.prove_n':
    '{n} prove',
  'pan.confermata':
    'confermata',
  'pan.scartata':
    'scartata',
  'pan.diariz_fallita':
    'Diarizzazione non riuscita.',
  'pan.diariz_fallita_n':
    'Diarizzazione non riuscita ({n}).',
  'pan.fallita':
    'Analisi non riuscita.',
  'pan.fallita_n':
    'Analisi non riuscita ({n}).',
  'pan.fallita_titolo':
    'Analisi non riuscita',
  'pan.ultimo_tentativo':
    'ultimo tentativo {ora}',
  'pan.avvia_locale':
    'Avvia il modello locale…',
  'pan.altro_motore':
    'Usa un altro motore…',
  'pan.esce_dal_computer':
    'La trascrizione di {min} minuti esce da questo computer e viene inviata a {dove}.',

  // --- Notion, dentro le espressioni --------
  'ntipo.title':
    'titolo',
  'ntipo.rich_text':
    'testo',
  'ntipo.number':
    'numero',
  'ntipo.date':
    'data',
  'ntipo.checkbox':
    'spunta',
  'ntipo.select':
    'elenco',
  'ntipo.multi_select':
    'elenco multiplo',
  'ntipo.status':
    'stato',
  'ntipo.url':
    'link',
  'ntn2.oppure':
    ' o ',
  'ntn2.no_risposta':
    'Notion non ha risposto',
  'ntn2.no_lettura':
    'Il database non si è letto',
  'ntn2.no_collegamento':
    'Il collegamento non è riuscito',
  'ntn2.no_creazione':
    'Il database non si è creato',
  'ntn2.no_scollegamento':
    'Lo scollegamento non è riuscito',
  'ntn2.collegato_a':
    'Collegato al database «{db}». Le task confermate diventano righe lì, nelle colonne che hai scelto.',
  'ntn2.non_collegato':
    'Le task confermate diventano righe in un database di Notion, con il minuto della prova come citazione.',
  'ntn2.sto_guardando':
    'Sto guardando…',
  'ntn2.continua':
    'Continua',
  'ntn2.sto_salvando':
    'Sto salvando…',
  'ntn2.salva':
    'Salva',
  'ntn2.sto_creando':
    'Sto creando…',
  'ntn2.crea_collega':
    'Crea e collega',
  'ntn2.non_mandare':
    'Non mandare',
  'ntn2.scegli_pagina':
    'Scegli una pagina',
  'ntn2.mappa_nota':
    'Database «{db}». Un campo lasciato su «Non mandare» resta in Scriba e non arriva a Notion.',
  'ntn2.serve_tipo':
    'Serve una colonna di tipo',
  'ntn2.campi_su_notion':
    '{n} campi su Notion',

  // --- database remoto, dentro le espressioni --------
  'db2.modo.diretta':
    'Diretta',
  'db2.modo.pooling_transazione':
    'Pooling (transazione)',
  'db2.modo.pooling_sessione':
    'Pooling (sessione)',
  'db2.modo_nota.diretta':
    'Porta 5432 sul server vero. Su Supabase spesso risponde solo in IPv6.',
  'db2.modo_nota.pooling_transazione':
    'Porta 6543. Gli statement preparati si spengono da soli: senza, il secondo invio fallisce.',
  'db2.modo_nota.pooling_sessione':
    'Il pooler sulla 5432. Ripiego quando la diretta non è raggiungibile in IPv4.',
  'db2.non_riuscito':
    'Non è riuscito.',
  'db2.gia_sincronizzato':
    'Era già tutto sincronizzato.',
  'db2.inviate':
    '{n} call inviate ({righe} righe)',
  'db2.fallite':
    ', {n} non riuscite: {errore}',
  'db2.scollegare':
    'Scollegare il database? I dati già scritti là fuori restano dove sono.',
  'db2.intro':
    'Tiene una copia delle call su un PostgreSQL — Supabase, o qualunque altro. Scegli tu in quale schema scrivere e quali dati mandare.',
  'db2.attivo':
    'Attivo',
  'db2.spento':
    'Spento',
  'db2.invio':
    'Invio…',
  'db2.sincronizza_tutto':
    'Sincronizza tutto',
  'db2.lascialo_vuoto':
    '— lascialo vuoto per non cambiare quello già salvato.',
  'db2.provo':
    'Provo…',
  'db2.prova':
    'Prova',
  'db2.creo':
    'Creo…',
  'db2.crea_collega':
    'Crea e collega',
  'db2.collego':
    'Collego…',
  'db2.collega':
    'Collega',
  'db2.voluminosa':
    '— può essere grande',
  'db2.quale_tabella':
    '— quale tabella? —',

  // --- dati, dentro le espressioni --------
  'dat2.compilata':
    'Compilata il {data}.',
  'dat2.senza_data':
    'Data di compilazione non disponibile.',
  'dat2.sporco':
    'Contiene modifiche non salvate in nessun commit.',
  'dat2.call_del':
    'Call del {data}',
  'dat2.eliminare':
    'Eliminare «{titolo}»?',
  'dat2.questa_call':
    'questa call',
  'dat2.scrivi_per_confermare':
    'Non si torna indietro. Scrivi {parola} per confermare.',
  'dat2.parola':
    'ELIMINA',

  // --- clienti, dentro le espressioni --------
  'cli2.mai':
    'mai',
  'cli2.ultima':
    'ultima:',
  'cli2.aggiunto':
    '{n} aggiunto',
  'cli2.aggiunti':
    '{n} aggiunti',
  'cli2.presente':
    '{n} già presente',
  'cli2.presenti':
    '{n} già presenti',
  'cli2.scartata':
    '{n} riga senza nome',
  'cli2.scartate':
    '{n} righe senza nome',
  'cli2.niente':
    'niente da aggiungere',
  'cli2.nome_vuoto':
    'Il nome non può essere vuoto.',
  'cli2.nome_non_cambiato':
    'Nome non cambiato: è vuoto, oppure è già di un altro cliente.',
  'cli2.nessun_nome_nel_file':
    'Nessun nome trovato nel file: serve almeno una colonna con i nomi.',
  'cli2.eliminare_con_call':
    'Eliminare «{nome}»? Le sue {n} call restano, ma senza cliente.',
  'cli2.eliminare':
    'Eliminare «{nome}»?',

  // --- rilevamento, dentro le espressioni --------
  'ril_esito.riunione':
    'riunione',
  'ril_esito.in_conferma':
    'in conferma',
  'ril_esito.gia_proposta':
    'già proposta',
  'ril_esito.in_attesa':
    'in attesa',
  'ril_esito.escluso':
    'escluso',
  'ril_perche.ignorato':
    'è nell'elenco dei processi da ignorare',
  'ril_perche.sessione_vecchia':
    'ha una sessione microfono aperta ma non ha mai dato segnale: sembra una sessione vecchia, non una registrazione in corso',
  'ril_perche.senza_audio':
    'usa il microfono ma non risulta riprodurre audio, né lui né un suo processo figlio: in una riunione qualcuno parla',
  'ril_perche.gia_proposta':
    'la proposta è già stata fatta per questa riunione',
  'ril_perche.in_conferma':
    'sembra una riunione: si aspetta che la situazione regga',
  'ril_perche.riunione':
    'microfono in uso e audio in riproduzione da abbastanza tempo',
  'ril2.in_valutazione':
    'in valutazione',
  'ril2.ancora_s':
    ' · ancora {s}s',
  'ril2.mic_attivo':
    'microfono attivo ({picco})',
  'ril2.mic_muto':
    'microfono muto',
  'ril2.riproduce':
    'riproduce audio',
  'ril2.riproduce_figlio':
    'riproduce (da un processo figlio)',
  'ril2.non_riproduce':
    'non riproduce',
  'ril2.sonda_attiva':
    'Sonda audio attiva',
  'ril2.sonda_spenta':
    'Sonda audio non attiva',
  'ril2.non_in_ascolto':
    'Rilevamento non in ascolto',
  'ril2.ultima_lettura':
    'ultima lettura {s}s fa',
  'ril2.conferma_dopo':
    'conferma dopo {s}s',
  'ril2.ripartenze':
    '{n} ripartenze',
  'ril2.rinunciato':
    'La sonda audio non è riuscita a restare in piedi e il rilevamento si è sospeso: fino al prossimo riavvio di Scriba nessuna riunione verrà proposta.',
  'ril2.ultimo_motivo':
    'Ultimo motivo: {m}',
  'ril2.sonda_zitta':
    'L'ultima lettura è di {s}s fa, e ne dovrebbe arrivare una ogni {ogni}s: la sonda ha smesso di riferire.',
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
  'ovl.salvato':
    'Saved in the transcript',
  'ovl.scatta':
    'Capture',
  'ovl.ferma':
    'Stop',
  'ovl.registra':
    'Record',
  'ovl.scatto_nota':
    'The screenshot goes into the transcript at the minute it was taken.',
  'ovl.fermo':
    'Not recording.',

  'cli.titolo':
    'Clients',
  'cli.aggiungi':
    'Add a client',
  'cli.aggiungi_nota':
    'It groups calls in the archive. You attribute them from there, where the calls are all in front of you.',
  'cli.aggiungi_btn':
    'Add',
  'cli.carica':
    'Load a list',
  'cli.scegli_file':
    'Choose a file',
  'cli.vuoto':
    'No clients. Until there is one the archive works just the same: calls stay searchable by text and by date.',
  'cli.salva':
    'Save',
  'cli.annulla':
    'Cancel',
  'cli.archiviato':
    '· archived',
  'cli.rinomina':
    'Rename',
  'cli.elimina':
    'Delete',

  'dlg.consenso_titolo':
    'Record this call',
  'dlg.consenso_cosa':
    'Your microphone and the computer audio will be recorded.',
  'dlg.consenso_spunta':
    'I have told the people on the call that I am recording.',
  'dlg.consenso_nota':
    'Recording other people means processing their personal data. This tick is recorded in the session, but it does not replace having told them.',
  'dlg.annulla':
    'Cancel',
  'dlg.registra':
    'Record',
  'dlg.rilevata':
    'I can record it. That includes the other participants’ audio, not only your voice.',
  'dlg.no_grazie':
    'No thanks',
  'dlg.torna':
    'it comes back on the next call',
  'mod.titolo':
    'Local models',
  'mod.spazio':
    'Disk space',
  'mod.apri_cartella':
    'Open the folder',
  'mod.download_nota':
    'A download can be paused and resumed: it picks up where it left off, even after closing Scriba.',
  'mod.scarica':
    'Download',
  'mod.sospendi':
    'Pause',
  'mod.riprendi':
    'Resume',
  'mod.avvia':
    'Start',
  'mod.elimina':
    'Delete',
  'mod.ferma':
    'Stop',

  'tra.nessuna_call':
    'No call',
  'tra.mai_registrato':
    'You have not recorded anything yet',
  'tra.mai_registrato_nota':
    'Start recording when you join a call. You will hear your microphone and the computer audio.',
  'tra.registra':
    'Record',
  'tra.io':
    'Me',
  'tra.altri':
    'Others',
  'tra.nomina_voci':
    'NAME THE VOICES',
  'tra.in_ascolto':
    'Listening. Nobody has spoken yet.',
  'tra.nessuna_trascrizione':
    'No transcript for this call.',
  'tra.eco_nota':
    'kept out of the summary, notes and exports',
  'tra.scatto_alt':
    'Shared screen at minute {t}',

  'ana.titolo':
    'Analysis',
  'ana.quando':
    'When to analyse',
  'ana.quando_nota':
    'When the call ends it starts by itself and you find it ready. On request you decide each time.',
  'ana.fine_call':
    'When the call ends',
  'ana.richiesta':
    'On request',
  'ana.note':
    'Running notes during the call',
  'ana.note_nota':
    'A partial summary every ten minutes, while people are talking.',
  'ana.note_rete':
    'With an engine on the network this means sending the transcript out several times during the call.',
  'ana.ogni_quanto':
    'How often',
  'ana.ogni_quanto_nota':
    'On a call shorter than the interval none come out: it is the most common reason for not seeing any.',

  'mot.titolo':
    'Analysis engine',
  'mot.titolo_nota':
    'Who reads the transcript and draws out the summary, key points and tasks. Only one can be used at a time.',
  'mot.in_caricamento':
    'The model is loading into memory. It becomes selectable by itself as soon as it is ready.',
  'mot.salva':
    'Save',
  'mot.annulla':
    'Cancel',
  'mot.serve_chiave':
    'An API key is needed',
  'mot.inserisci':
    'Enter the key',

  'ovl.nome':
    'Scriba',

  'rif.interrompi':
    'Stop',
  'rif.gia_in_corso':
    'A refinement is already running, on another call.',
  'rif.rifai':
    'Redo',
  'rif.durata':
    'Estimated time',
  'rif.rifai_trascrizione':
    'Redo the transcription',

  'arc2.ia_nota':
    'Every quotation next to what it supports, and stated plainly which commitments a call produced.',
  'arc2.integrale':
    'Full transcript',
  'arc2.mostra':
    'Show',
  'arc2.esc':
    'Esc',

  'exp.titolo':
    'Export',
  'exp.cartella':
    'Default folder',
  'exp.cambia':
    'Change',
  'exp.formato':
    'Format',
  'exp.formato_nota':
    'Markdown also carries the minutes of the evidence. Plain text is the transcript and nothing else.',

  'idx.apri_cartella':
    'Open the folder',

  'sco.titolo':
    'Shortcuts',
  'sco.titolo_nota':
    'You press them, you do not type them: click the field and press the combination. If another application already has it we say so immediately, because Windows refuses it in silence.',
  'sco.ripristina':
    'Reset',
  'sco.gia_usata':
    'Already taken by another application. Windows refuses it in silence: until you change it, the shortcut does nothing.',

  'asp.titolo':
    'Appearance',
  'asp.tema':
    'Theme',
  'asp.tema_nota':
    '“Same as the system” follows Windows, including when it changes by itself at sunset. It applies immediately, without restarting. The transcript strip stays dark either way: it sits over the meeting window, and white glares there.',

  'ntn2.annulla':
    'Cancel',

  'imp.titolo':
    'Settings',
  'imp.carico':
    'Loading settings…',
  'imp.chiudi':
    'Close',

  'prv.titolo':
    'EVIDENCE',
  'prv.nota':
    'Every field of the task comes from one of these sentences. If a piece of evidence does not hold up, the field is wrong.',

  'not.titolo':
    'WORKING NOTE',
  'not.aggiorno':
    'updating…',

  'ril2.vede':
    'What it is seeing right now',

  'ras2.esc':
    'Esc',

  'sel.vuoto':
    'No option available',

  'top.nome':
    'Scriba',
  'pan.da_confermare':
    'tasks to confirm',
  'pan.rassegna':
    'Review them',
  'pan.conferma':
    'Confirm',
  'pan.scarta':
    'Discard',
  'pan.modifica':
    'Edit',
  'pan.annulla':
    'Cancel',
  'pan.no_pyannote':
    'Telling the voices inside “others” apart is not available: pyannote.audio is missing, and it is not part of the package. It has to be installed separately.',
  'pan.voci_distinte':
    'distinct voices',
  'pan.durata_stimata':
    'Estimated time',
  'pan.misurati':
    'Actually measured on this machine. It runs locally: no data leaves the computer. You can close the window, the work carries on and you find it finished.',
  'pan.avvia':
    'Start',
  'pan.riprova':
    'Try again',
  'pan.distingui':
    'Tell the voices apart',
  'pan.label':
    'ANALYSIS',
  'pan.scegli_call':
    'Select a call to see its analysis.',
  'pan.a_call_finita':
    'It happens once the call is over. Summary, key points and tasks over the whole recording, not in pieces.',
  'pan.label_in_corso':
    'ANALYSING',
  'pan.puoi_chiudere':
    'You can close the window.',
  'pan.lavoro_continua':
    'The work carries on and you find it finished. We will tell you when it is ready.',
  'pan.interrompi':
    'Stop',
  'pan.titolo':
    'Analysis',
  'pan.carico':
    'Loading the analysis…',
  'pan.non_analizzata':
    'This call has not been analysed yet.',
  'pan.analizza':
    'Analyse the call',
  'pan.motore':
    'Engine',
  'pan.costo':
    'Estimated cost',
  'pan.rianalizza':
    'Analyse again',
  'pan.riassunto':
    'Summary',
  'pan.salienti':
    'Key points',
  'pan.task':
    'Tasks',
  'pan.nessun_impegno':
    'No commitment found.',

  'tra2.titolo':
    'Transcription',
  'tra2.lingua':
    'Call language',
  'tra2.lingua_nota':
    'It applies to the transcript and to everything drawn from it: summary, key points and tasks come out in this language. The others are still recognised, but with more mistakes on names.',
  'tra2.microfono':
    'Microphone',
  'tra2.microfono_nota':
    'Records your own voice.',
  'tra2.loopback':
    'Computer audio',
  'tra2.loopback_nota':
    'Records the other people’s voices. Without it you only hear yourself.',
  'tra2.filtro':
    'Echo filter',
  'tra2.filtro_nota':
    'Recognises when the microphone picks the loudspeaker back up. Turn it too high and overlapping speech is lost.',
  'tra2.dopo':
    'After the call',
  'tra2.rifai':
    'Redo the transcript on its own',
  'tra2.nomi':
    'Proper names',
  'tra2.glossario':
    'Glossary',
  'tra2.glossario_nota':
    'Names the model does not know it guesses afresh at every sentence, and differently each time: in the same call “Clotilde” becomes Tilde, Cotilde and Protile. Write them here, one per line, and they are put back in place once a sentence ends. The original text stays saved.',
  'tra2.anche_clienti':
    'Clients too',
  'tra2.anche_clienti_nota':
    'The names in your client list join the glossary by themselves, without retyping them here.',
  'tra2.quanto':
    'How hard to try',

  'ovl.ingrandisci':
    'Expand the strip',
  'ovl.riduci':
    'Shrink the strip',
  'ovl.chiudi':
    'Close',
  'ovl.scatto_n':
    'Capture {n}',
  'idx.nascondi_call':
    'Hide the call list',
  'idx.mostra_call':
    'Show the call list',
  'idx.nascondi_analisi':
    'Hide the analysis panel',
  'idx.mostra_analisi':
    'Show the analysis panel',
  'rif.conferma_nota':
    'It goes over every line with a more accurate model, one you can really impose a language on: it is the fix for sentences that end up in another language. The text you have now stays saved. It runs locally, and you can close the window.',
  'rif.avvia':
    'Start',
  'rif.annulla':
    'Cancel',
  'arch.includi_integrale':
    'Include the full transcript',
  'dlg.esempio_titolo':
    'Sprint 24 review',
  'cli.ph_nome':
    'Name',
  'mot.ph_chiave':
    'API key',
  'prv.chiudi':
    'Close the evidence',
  'tra.ph_nome_vero':
    'real name',

  'pan.chi':
    'who',
  'pan.entro':
    'by',
  'pan.non_detto':
    'not said',
  'pan.non_detta':
    'not said',
  'pan.solo_a_voce':
    'said out loud only: “{q}”',
  'pan.prova_1':
    '1 piece of evidence',
  'pan.prove_n':
    '{n} pieces of evidence',
  'pan.confermata':
    'confirmed',
  'pan.scartata':
    'discarded',
  'pan.diariz_fallita':
    'Telling the voices apart did not work.',
  'pan.diariz_fallita_n':
    'Telling the voices apart did not work ({n}).',
  'pan.fallita':
    'The analysis did not work.',
  'pan.fallita_n':
    'The analysis did not work ({n}).',
  'pan.fallita_titolo':
    'The analysis did not work',
  'pan.ultimo_tentativo':
    'last try {ora}',
  'pan.avvia_locale':
    'Start the local model…',
  'pan.altro_motore':
    'Use a different engine…',
  'pan.esce_dal_computer':
    'The {min}-minute transcript leaves this computer and is sent to {dove}.',

  'ntipo.title':
    'title',
  'ntipo.rich_text':
    'text',
  'ntipo.number':
    'number',
  'ntipo.date':
    'date',
  'ntipo.checkbox':
    'checkbox',
  'ntipo.select':
    'select',
  'ntipo.multi_select':
    'multi-select',
  'ntipo.status':
    'status',
  'ntipo.url':
    'link',
  'ntn2.oppure':
    ' or ',
  'ntn2.no_risposta':
    'Notion did not answer',
  'ntn2.no_lettura':
    'The database could not be read',
  'ntn2.no_collegamento':
    'Connecting did not work',
  'ntn2.no_creazione':
    'The database could not be created',
  'ntn2.no_scollegamento':
    'Disconnecting did not work',
  'ntn2.collegato_a':
    'Connected to the “{db}” database. Confirmed tasks become rows there, in the columns you picked.',
  'ntn2.non_collegato':
    'Confirmed tasks become rows in a Notion database, with the minute of the evidence as the quote.',
  'ntn2.sto_guardando':
    'Looking…',
  'ntn2.continua':
    'Continue',
  'ntn2.sto_salvando':
    'Saving…',
  'ntn2.salva':
    'Save',
  'ntn2.sto_creando':
    'Creating…',
  'ntn2.crea_collega':
    'Create and connect',
  'ntn2.non_mandare':
    'Do not send',
  'ntn2.scegli_pagina':
    'Pick a page',
  'ntn2.mappa_nota':
    'Database “{db}”. A field left on “Do not send” stays in Scriba and never reaches Notion.',
  'ntn2.serve_tipo':
    'It needs a column of type',
  'ntn2.campi_su_notion':
    '{n} fields on Notion',

  'db2.modo.diretta':
    'Direct',
  'db2.modo.pooling_transazione':
    'Pooling (transaction)',
  'db2.modo.pooling_sessione':
    'Pooling (session)',
  'db2.modo_nota.diretta':
    'Port 5432 on the real server. On Supabase it often answers over IPv6 only.',
  'db2.modo_nota.pooling_transazione':
    'Port 6543. Prepared statements turn themselves off: without that, the second send fails.',
  'db2.modo_nota.pooling_sessione':
    'The pooler on 5432. The fallback when the direct one cannot be reached over IPv4.',
  'db2.non_riuscito':
    'It did not work.',
  'db2.gia_sincronizzato':
    'Everything was already in sync.',
  'db2.inviate':
    '{n} calls sent ({righe} rows)',
  'db2.fallite':
    ', {n} failed: {errore}',
  'db2.scollegare':
    'Disconnect the database? The data already written out there stays where it is.',
  'db2.intro':
    'It keeps a copy of your calls on a PostgreSQL — Supabase, or any other. You choose which schema to write to and which data to send.',
  'db2.attivo':
    'On',
  'db2.spento':
    'Off',
  'db2.invio':
    'Sending…',
  'db2.sincronizza_tutto':
    'Sync everything',
  'db2.lascialo_vuoto':
    '— leave it empty to keep the one already saved.',
  'db2.provo':
    'Trying…',
  'db2.prova':
    'Try it',
  'db2.creo':
    'Creating…',
  'db2.crea_collega':
    'Create and connect',
  'db2.collego':
    'Connecting…',
  'db2.collega':
    'Connect',
  'db2.voluminosa':
    '— it can be big',
  'db2.quale_tabella':
    '— which table? —',

  'dat2.compilata':
    'Built on {data}.',
  'dat2.senza_data':
    'Build date not available.',
  'dat2.sporco':
    'It contains changes not saved in any commit.',
  'dat2.call_del':
    'Call of {data}',
  'dat2.eliminare':
    'Delete “{titolo}”?',
  'dat2.questa_call':
    'this call',
  'dat2.scrivi_per_confermare':
    'There is no going back. Type {parola} to confirm.',
  'dat2.parola':
    'DELETE',

  'cli2.mai':
    'never',
  'cli2.ultima':
    'last:',
  'cli2.aggiunto':
    '{n} added',
  'cli2.aggiunti':
    '{n} added',
  'cli2.presente':
    '{n} already there',
  'cli2.presenti':
    '{n} already there',
  'cli2.scartata':
    '{n} row with no name',
  'cli2.scartate':
    '{n} rows with no name',
  'cli2.niente':
    'nothing to add',
  'cli2.nome_vuoto':
    'The name cannot be empty.',
  'cli2.nome_non_cambiato':
    'Name unchanged: it is empty, or it already belongs to another client.',
  'cli2.nessun_nome_nel_file':
    'No name found in the file: it needs at least one column with the names.',
  'cli2.eliminare_con_call':
    'Delete “{nome}”? Their {n} calls stay, but with no client.',
  'cli2.eliminare':
    'Delete “{nome}”?',

  'ril_esito.riunione':
    'meeting',
  'ril_esito.in_conferma':
    'confirming',
  'ril_esito.gia_proposta':
    'already proposed',
  'ril_esito.in_attesa':
    'waiting',
  'ril_esito.escluso':
    'excluded',
  'ril_perche.ignorato':
    'it is in the list of processes to ignore',
  'ril_perche.sessione_vecchia':
    'it has a microphone session open but has never given a signal: it looks like an old session, not a recording in progress',
  'ril_perche.senza_audio':
    'it uses the microphone but does not seem to be playing audio, neither it nor a child process: in a meeting somebody talks',
  'ril_perche.gia_proposta':
    'the offer has already been made for this meeting',
  'ril_perche.in_conferma':
    'it looks like a meeting: waiting to see whether it holds',
  'ril_perche.riunione':
    'microphone in use and audio playing for long enough',
  'ril2.in_valutazione':
    'being judged',
  'ril2.ancora_s':
    ' · {s}s to go',
  'ril2.mic_attivo':
    'microphone active ({picco})',
  'ril2.mic_muto':
    'microphone silent',
  'ril2.riproduce':
    'playing audio',
  'ril2.riproduce_figlio':
    'playing (from a child process)',
  'ril2.non_riproduce':
    'not playing',
  'ril2.sonda_attiva':
    'Audio probe running',
  'ril2.sonda_spenta':
    'Audio probe not running',
  'ril2.non_in_ascolto':
    'Detection not listening',
  'ril2.ultima_lettura':
    'last reading {s}s ago',
  'ril2.conferma_dopo':
    'confirms after {s}s',
  'ril2.ripartenze':
    '{n} restarts',
  'ril2.rinunciato':
    'The audio probe could not stay up and detection has suspended itself: until Scriba is restarted no meeting will be offered.',
  'ril2.ultimo_motivo':
    'Last reason: {m}',
  'ril2.sonda_zitta':
    'The last reading is {s}s old, and one should arrive every {ogni}s: the probe has stopped reporting.',
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
