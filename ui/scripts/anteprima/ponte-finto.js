/**
 * Ponte finto verso il core, per guardare l'interfaccia senza avviare Electron.
 *
 * Serve a una cosa sola: mettere le schermate vere accanto alle pagine del
 * handoff e vedere se combaciano. I dati sono gli stessi delle pagine di prova
 * — stesse call, stesse frasi, stessi minuti — perché un confronto fatto con
 * dati diversi non dice niente su quello che si voleva verificare.
 *
 * NON fa parte del prodotto e non finisce nella build.
 */
;(function () {
  const ORA = Date.parse('2026-08-12T14:05:00')
  const GIORNO = 86_400_000

  const righe = [
    ['loopback', 252, 'Allora, il punto principale di oggi è la dashboard clienti. Sulla parte visiva siamo ancora fermi.'],
    ['mic', 271, 'Sì, non abbiamo ancora niente da mostrare. Nemmeno uno schema.'],
    ['loopback', 300, 'Dovremmo preparare i mockup della dashboard prima di parlarne con loro.'],
    ['mic', 314, 'D’accordo. Serve almeno la vista principale e il dettaglio cliente.'],
    ['loopback', 339, 'E i filtri. Senza filtri non si capisce a cosa serve.'],
    ['mic', 380, 'Questo è il pannello vecchio, lo tengo come riferimento di cosa non rifare.'],
    ['loopback', 1120, 'Non mi è chiaro se un utente esterno vede anche i dati degli altri clienti.'],
    ['loopback', 1152, 'Comunque va chiarito prima del rilascio, non dopo.'],
    // Il microfono ha ripreso l'altoparlante: e' la riga di sopra, tornata
    // indietro tre secondi dopo. Sta qui per far vedere come compare — fuori
    // dalla trascrizione finche' non la si chiede, e mai attribuita a "Io".
    ['mic', 1155, 'Comunque va chiarito prima del rilascio, non dopo.', true],
    ['mic', 1904, 'Quando li vogliamo pronti?'],
    ['loopback', 1920, 'Diciamo entro il quattordici, così abbiamo una settimana per rivederli.'],
    ['mic', 1938, 'Il quattordici è un venerdì, va bene.'],
    ['loopback', 2851, 'Ultima cosa: chi ci mette mano?'],
    ['loopback', 2880, 'Per i mockup se ne occupa Marco, ha già fatto quelli del portale.'],
    ['mic', 2902, 'Perfetto, gli passo io il contesto e i link al portale.'],
  ]

  // Sessione 24 (l'unica "analyzed"): finta gia' diarizzata, con una voce
  // ancora senza nome, cosi' la striscia "DAI UN NOME ALLE VOCI" e la riga
  // "Voce 3" compaiono nell'anteprima senza dover simulare l'intero lavoro.
  const SPEAKER = {
    io: { id: 100, label: 'io', nome_reale: null },
    voce2: { id: 101, label: 'Voce 2', numero: 2, nome_reale: 'Marco' },
    voce3: { id: 102, label: 'Voce 3', numero: 3, nome_reale: null },
  }
  const speakerRighe = [
    SPEAKER.voce2, null, SPEAKER.voce2, null, SPEAKER.voce3, null,
    SPEAKER.voce2, SPEAKER.voce2, null, null, SPEAKER.voce3, null,
    SPEAKER.voce2, SPEAKER.voce3, null,
  ]

  const segmenti = righe.map(([source, s, testo, eco], i) => ({
    id: i + 1,
    source,
    t_start_ms: s * 1000,
    t_end_ms: (s + 4) * 1000,
    testo,
    is_final: true,
    eco: Boolean(eco),
    speaker: source === 'loopback' ? speakerRighe[i] : null,
  }))

  const voci24 = [
    { id: 1, ruolo: 'me', label: 'io', nome_reale: null, confermato: false },
    { id: 2, ruolo: 'them', label: 'altri', nome_reale: null, confermato: false },
    { id: SPEAKER.voce2.id, ruolo: 'them', label: 'Voce 2', numero: 2, nome_reale: 'Marco', confermato: true },
    { id: SPEAKER.voce3.id, ruolo: 'them', label: 'Voce 3', numero: 3, nome_reale: null, confermato: false },
  ]
  const vociVuote = [
    { id: 1, ruolo: 'me', label: 'io', nome_reale: null, confermato: false },
    { id: 2, ruolo: 'them', label: 'altri', nome_reale: null, confermato: false },
  ]

  const prova = (supports, t, quote) => ({ supports, t_ms: t * 1000, quote, segment_id: null })

  const tasks = [
    {
      id: 1, titolo: 'Preparare i mockup della dashboard clienti', descrizione: null,
      assignee_text: 'Marco', due_date: '2026-08-14', due_raw: 'entro il quattordici',
      priorita: 'alta', stato: 'proposed', confidence: 0.92, needs_review: 0, review_reason: null,
      evidence: [
        prova('titolo', 300, 'Dovremmo preparare i mockup della dashboard prima di parlarne con loro.'),
        prova('due_date', 1920, 'Diciamo entro il quattordici, così abbiamo una settimana per rivederli.'),
        prova('assignee', 2880, 'Per i mockup se ne occupa Marco, ha già fatto quelli del portale.'),
      ],
    },
    {
      id: 2, titolo: 'Verificare chi vede i dati degli altri clienti tra gli utenti esterni', descrizione: null,
      assignee_text: null, due_date: null, due_raw: 'prima del rilascio',
      priorita: 'media', stato: 'proposed', confidence: 0.61, needs_review: 1,
      review_reason: 'Nessun responsabile nominato.',
      evidence: [
        prova('titolo', 1120, 'Non mi è chiaro se un utente esterno vede anche i dati degli altri clienti.'),
        prova('due_date', 1152, 'Comunque va chiarito prima del rilascio, non dopo.'),
      ],
    },
    {
      id: 3, titolo: 'Chiudere il contratto con il fornitore di SMS', descrizione: null,
      assignee_text: null, due_date: '2026-08-20', due_raw: 'entro fine mese',
      priorita: 'critica', stato: 'proposed', confidence: 0.78, needs_review: 0, review_reason: null,
      evidence: [prova('titolo', 2465, 'Il contratto scade e va rifirmato.')],
    },
    {
      id: 4, titolo: 'Rifare le stime del backend con la nuova struttura dei permessi', descrizione: null,
      assignee_text: 'Giulia', due_date: null, due_raw: null,
      priorita: 'media', stato: 'proposed', confidence: 0.83, needs_review: 0, review_reason: null,
      evidence: [prova('titolo', 1335, 'Se i permessi cambiano, le stime non valgono più.')],
    },
    {
      id: 5, titolo: 'Aggiornare la documentazione delle API', descrizione: null,
      assignee_text: null, due_date: null, due_raw: null,
      priorita: null, stato: 'proposed', confidence: 0.55, needs_review: 1,
      review_reason: 'Detto di sfuggita, senza responsabile né scadenza.',
      evidence: [prova('esistenza', 1500, 'E la documentazione andrebbe aggiornata.')],
    },
  ]

  const analisi = {
    riassunto: null,
    punti_salienti: null,
    riassunto_gruppi: [
      { titolo: 'Dashboard clienti', voci: [
        { testo: 'Non c’è ancora materiale visivo: si parte da vista principale, dettaglio cliente e filtri.', t_ms: 300_000 },
        { testo: 'Consegna concordata per il quattordici, con una settimana di revisione prima di mostrarla al cliente.', t_ms: 1_920_000 },
      ] },
      { titolo: 'Permessi', voci: [
        { testo: 'Resta aperto se un utente esterno veda i dati degli altri clienti. Va chiuso prima del rilascio.', t_ms: 1_120_000 },
        { testo: 'Se i permessi cambiano, le stime del backend non valgono più.', t_ms: 1_335_000 },
      ] },
      { titolo: 'Fornitore SMS', voci: [
        { testo: 'Il contratto scade e va rifirmato, altrimenti restano ferme le notifiche.', t_ms: 2_465_000 },
      ] },
    ],
    salienti: [
      { t_ms: 300_000, etichetta: 'Mockup dashboard', corpo: 'Nessun materiale visivo pronto: blocca il confronto con il cliente.' },
      { t_ms: 1_120_000, etichetta: 'Permessi utenti esterni', corpo: 'Dubbio non risolto su chi vede i dati degli altri clienti.' },
      { t_ms: 1_920_000, etichetta: 'Data di consegna', corpo: 'Concordato il quattordici, con una settimana di revisione.' },
      { t_ms: 2_465_000, etichetta: 'Fornitore SMS', corpo: 'Contratto in scadenza, da chiudere prima del rilascio.' },
    ],
    tasks,
    meta: {
      provider: 'anthropic', etichetta_provider: 'API Anthropic', modello: 'claude-sonnet-5',
      costo_usd: 0.04, durata_ms: 192_000, finita_at: ORA,
    },
    errore: null,
  }

  const sessioni = [
    { id: 24, titolo: 'Revisione sprint 24 — dashboard clienti', piattaforma: 'Zoom', started_at: ORA, ended_at: ORA + 3_134_000, durata_ms: 3_134_000, stato: 'analyzed', lingua: 'it', n_task: 5, n_da_confermare: 2 },
    { id: 23, titolo: null, piattaforma: null, started_at: ORA - GIORNO, ended_at: null, durata_ms: 1_720_000, stato: 'recorded', lingua: 'it', n_task: 0, n_da_confermare: 0 },
    { id: 22, titolo: 'Allineamento fornitore SMS', piattaforma: 'Teams', started_at: ORA - 3 * GIORNO, ended_at: null, durata_ms: 2_512_000, stato: 'failed', lingua: 'it', n_task: 0, n_da_confermare: 0 },
    { id: 21, titolo: null, piattaforma: null, started_at: ORA - 4 * GIORNO, ended_at: null, durata_ms: 727_000, stato: 'recorded', lingua: 'it', n_task: 0, n_da_confermare: 0 },
    { id: 20, titolo: 'Primo incontro cliente Bertoni', piattaforma: 'Meet', started_at: ORA - 7 * GIORNO, ended_at: null, durata_ms: 3_858_000, stato: 'analyzed', lingua: 'it', n_task: 3, n_da_confermare: 0 },
  ]

  const providers = [
    // `local` è di proposito «in avvio»: è lo stato che prima non esisteva e
    // che qui si vuole poter guardare senza avviare davvero un modello da 9 GB.
    { id: 'local', etichetta: 'Modello locale', descrizione: 'Non esce nulla dal computer.', model: 'gemma-4-12b-it', disponibile: false, attivo: false, esce_dal_computer: false, costo_ora_eur: null, minuti_per_ora: 10, rimedio: null, in_avvio: true },
    { id: 'claude-cli', etichetta: 'Abbonamento Claude', descrizione: 'Usa un abbonamento già attivo, nessun costo a consumo.', model: 'sonnet', disponibile: true, attivo: false, esce_dal_computer: true, costo_ora_eur: null, minuti_per_ora: 3, rimedio: null, in_avvio: false },
    { id: 'anthropic', etichetta: 'API Anthropic', descrizione: 'Si paga a consumo, circa 0,04 € per un’ora di call.', model: 'claude-sonnet-5', disponibile: true, attivo: true, esce_dal_computer: true, costo_ora_eur: 0.04, minuti_per_ora: 3, rimedio: null, in_avvio: false },
    { id: 'openai', etichetta: 'API OpenAI', descrizione: 'Si paga a consumo, circa 0,05 € per un’ora di call.', model: 'gpt-5-mini', disponibile: false, attivo: false, esce_dal_computer: true, costo_ora_eur: 0.05, minuti_per_ora: 3, rimedio: 'Serve una chiave API', in_avvio: false },
  ]

  const GB = 1024 ** 3
  const modelli = [
    { id: 'whisper-large-v3', nome: 'whisper-large-v3', uso: 'trascrizione', size_bytes: 3.1 * GB, stato: 'installato', scaricati_bytes: 3.1 * GB, velocita_bps: null, secondi_rimanenti: null, installato_at: ORA - 40 * GIORNO, nota: null, errore: null, endpoint: null, ram_bytes: null },
    { id: 'mistral-small-3', nome: 'mistral-small-3', uso: 'analisi', size_bytes: 6.4 * GB, stato: 'in_uso', scaricati_bytes: 6.4 * GB, velocita_bps: null, secondi_rimanenti: null, installato_at: ORA - 20 * GIORNO, nota: null, errore: null, endpoint: '127.0.0.1:8080', ram_bytes: 2.1 * GB },
    { id: 'qwen2.5-14b-instruct', nome: 'qwen2.5-14b-instruct', uso: 'analisi', size_bytes: 9.0 * GB, stato: 'in_download', scaricati_bytes: 4.1 * GB, velocita_bps: 12.4 * 1024 * 1024, secondi_rimanenti: 360, installato_at: null, nota: null, errore: null, endpoint: null, ram_bytes: null },
    { id: 'gemma-3-12b', nome: 'gemma-3-12b', uso: 'analisi', size_bytes: 7.2 * GB, stato: 'in_verifica', scaricati_bytes: 6.6 * GB, velocita_bps: null, secondi_rimanenti: null, installato_at: null, nota: 'controllo dell’integrità · sha256', errore: null, endpoint: null, ram_bytes: null },
    { id: 'parakeet-tdt-0.6b', nome: 'parakeet-tdt-0.6b', uso: 'trascrizione', size_bytes: 1.2 * GB, stato: 'non_installato', scaricati_bytes: 0, velocita_bps: null, secondi_rimanenti: null, installato_at: null, nota: 'più veloce di whisper, meno preciso sui nomi propri', errore: null, endpoint: null, ram_bytes: null },
    { id: 'llama-3.3-70b-q4', nome: 'llama-3.3-70b-q4', uso: 'analisi', size_bytes: 17 * GB, stato: 'spazio_insufficiente', scaricati_bytes: 0, velocita_bps: null, secondi_rimanenti: null, installato_at: null, nota: 'servono 17 GB, ne restano 12', errore: 'Il download non parte: mancano 5 GB. Va liberato spazio prima, non a metà scaricamento.', endpoint: null, ram_bytes: null },
  ]

  const impostazioni = {
    llm: { provider: 'anthropic', base_url: 'http://127.0.0.1:8080', model: 'claude-sonnet-5', api_key_presente: true },
    stt: { provider: 'local', lingua: 'it', microfono_id: 'mic-0', loopback_id: 'lb-0', filtro_eco: 'medio' },
    analisi_automatica: true,
    note_incrementali: false,
    interfaccia: { scorciatoia_overlay: 'Alt+R', scorciatoia_screenshot: 'CommandOrControl+Shift+S', righe_overlay: 6, opacita_overlay: 0.92, overlay_ridotto: false },
    rilevamento: { attivo: true, avvio_automatico: false, conferma_s: 20 },
    export: { cartella: 'C:\\Users\\utente\\Documenti\\Scriba', formato: 'markdown' },
  }

  // Notion finto: un database con nomi di colonna che combaciano solo in parte
  // (Owner sta in inglese, «Quando» non è riconoscibile, non c'è nessuna
  // colonna per la prova) — è il caso che la mappatura deve saper risolvere.
  const notionCampi = [
    { id: 'titolo', etichetta: 'Titolo della task', aiuto: 'Va sempre nella proprietà titolo del database: è l’unica che Notion garantisce.', tipi: ['title'], nome_notion: 'Task', consigliato: true, obbligatorio: true },
    { id: 'descrizione', etichetta: 'Descrizione', aiuto: 'Il dettaglio della task, quando il modello l’ha scritto.', tipi: ['rich_text'], nome_notion: 'Descrizione', consigliato: true, obbligatorio: false },
    { id: 'assegnatario', etichetta: 'Assegnatario', aiuto: 'Il nome come è stato detto nella call, non un utente di Notion.', tipi: ['rich_text', 'select', 'multi_select'], nome_notion: 'Assegnatario', consigliato: true, obbligatorio: false },
    { id: 'scadenza', etichetta: 'Scadenza', aiuto: 'La data, quando dalla call si capisce quale sia.', tipi: ['date'], nome_notion: 'Scadenza', consigliato: true, obbligatorio: false },
    { id: 'priorita', etichetta: 'Priorità', aiuto: 'Bassa, media, alta o critica.', tipi: ['select', 'status', 'rich_text'], nome_notion: 'Priorità', consigliato: true, obbligatorio: false },
    { id: 'stato', etichetta: 'Fatto', aiuto: 'Segnato quando la task risulta fatta in Scriba.', tipi: ['checkbox', 'select', 'status'], nome_notion: 'Fatto', consigliato: true, obbligatorio: false },
    { id: 'prova', etichetta: 'Prova', aiuto: 'Le frasi della call da cui viene la task, col minuto. È quello che la rende verificabile.', tipi: ['rich_text'], nome_notion: 'Prova', consigliato: true, obbligatorio: false },
    { id: 'call', etichetta: 'Call di provenienza', aiuto: 'Il titolo della riunione da cui arriva la task.', tipi: ['rich_text', 'select'], nome_notion: 'Call', consigliato: true, obbligatorio: false },
    { id: 'data_call', etichetta: 'Data della call', aiuto: 'Quando si è tenuta la riunione.', tipi: ['date'], nome_notion: 'Data della call', consigliato: true, obbligatorio: false },
    { id: 'link_call', etichetta: 'Link alla pagina della call', aiuto: 'L’indirizzo della pagina che Scriba crea per la call.', tipi: ['url', 'rich_text'], nome_notion: 'Link alla call', consigliato: false, obbligatorio: false },
    { id: 'confidenza', etichetta: 'Confidenza del modello', aiuto: 'Quanto il modello era sicuro, da 0 a 1.', tipi: ['number', 'rich_text'], nome_notion: 'Confidenza', consigliato: false, obbligatorio: false },
    { id: 'da_rivedere', etichetta: 'Da rivedere', aiuto: 'Segnato quando Scriba consiglia di controllare la task a mano.', tipi: ['checkbox'], nome_notion: 'Da rivedere', consigliato: false, obbligatorio: false },
  ]

  const notionDatabase = {
    'db-1': {
      titolo: 'Impegni del team',
      titolo_proprieta: 'Nome',
      proprieta: [
        { nome: 'Descrizione', tipo: 'rich_text' },
        { nome: 'Owner', tipo: 'rich_text' },
        { nome: 'Scadenza', tipo: 'date' },
        { nome: 'Quando', tipo: 'date' },
        { nome: 'Priorità', tipo: 'select' },
        { nome: 'Stato', tipo: 'status' },
        { nome: 'Fatto', tipo: 'checkbox' },
        { nome: 'Riferimento', tipo: 'url' },
      ],
      // Quello che il core proporrebbe: «Owner» è un alias noto, «Quando» e
      // «Riferimento» non dicono niente sul loro contenuto e restano da scegliere.
      mappa_proposta: { descrizione: 'Descrizione', assegnatario: 'Owner', scadenza: 'Scadenza', priorita: 'Priorità', stato: 'Fatto' },
    },
    'db-2': {
      titolo: 'Roadmap prodotto',
      titolo_proprieta: 'Titolo',
      proprieta: [{ nome: 'Trimestre', tipo: 'select' }],
      mappa_proposta: {},
    },
  }

  const notionStato = { collegato: false, database_id: null, database_titolo: null, mappa: {} }

  // ---------------------------------------------------- database remoto
  //
  // Lo schermo del database remoto non era raggiungibile dall'anteprima: senza
  // queste risposte `risolvi` tornava `null`, e la schermata restava sul primo
  // passo senza mai mostrare schema, tabelle e DDL — cioe' tre quarti di
  // quello che c'e' da guardare.
  //
  // I nomi sono quelli che si trovano davvero su un Supabase appena fatto:
  // `public` c'e' sempre, `auth` e `storage` pure, e nessuno dei tre e' il
  // posto dove uno vuole mettere le proprie tabelle. E' esattamente il caso
  // che fa venire voglia di crearne uno nuovo.
  const SCHEMI_FINTI = ['auth', 'public', 'storage']
  const TABELLE_FINTE = ['clienti', 'note_riunioni', 'progetti']

  const MODELLO_FINTO = [
    { chiave: 'call', etichetta: 'Le call', descrizione: 'Una riga per riunione: titolo, cliente, durata, stato.', predefinita: true, voluminosa: false },
    { chiave: 'task', etichetta: 'Le task', descrizione: 'Quelle estratte dall\'analisi, con assegnatario e scadenza.', predefinita: true, voluminosa: false },
    { chiave: 'analisi', etichetta: 'Le analisi', descrizione: 'Riassunto, punti salienti, nota di lavoro.', predefinita: true, voluminosa: false },
    { chiave: 'trascrizione', etichetta: 'La trascrizione', descrizione: 'Riga per riga, con i minuti.', predefinita: false, voluminosa: true },
    { chiave: 'partecipante', etichetta: 'I partecipanti', descrizione: 'Le voci distinte, con il nome se gliel\'hai dato.', predefinita: false, voluminosa: false },
    { chiave: 'screenshot', etichetta: 'Gli screenshot', descrizione: 'Percorso e testo letto a schermo.', predefinita: false, voluminosa: false },
  ]

  const CAMPI_FINTI = {
    call: ['uuid', 'titolo', 'cliente', 'inizio', 'durata_ms'],
    task: ['uuid', 'call_uuid', 'titolo', 'assegnatario', 'scadenza'],
  }

  function databaseRemoto(path, body) {
    const dati = body ?? {}
    if (path === '/database-remoto/prova') {
      if (!(dati.url || '').startsWith('postgres')) {
        return { ok: false, status: 400, body: { detail: 'L\'indirizzo deve cominciare con postgresql:// (o postgres://).' } }
      }
      return {
        ok: true,
        status: 200,
        body: {
          ok: true,
          versione: 'PostgreSQL 17.2 on x86_64-pc-linux-gnu, compiled by gcc',
          schemi: SCHEMI_FINTI,
          modalita: dati.modalita || 'diretta',
        },
      }
    }
    if (path === '/database-remoto/tabelle') {
      // Solo negli schemi che esistono: uno appena nominato e' vuoto, ed e'
      // proprio la cosa che la schermata deve saper dire.
      const dentro = SCHEMI_FINTI.includes(dati.schema_remoto) ? TABELLE_FINTE : []
      return { ok: true, status: 200, body: dentro }
    }
    if (path === '/database-remoto/anteprima') {
      const schema = dati.schema_remoto || 'public'
      const pezzi = dati.crea_schema
        ? [{ tabella: '(schema)', sql: `CREATE SCHEMA IF NOT EXISTS "${schema}"` }]
        : []
      for (const chiave of dati.tabelle ?? []) {
        const nome = `${dati.prefisso ?? ''}${chiave}`
        const campi = CAMPI_FINTI[chiave] ?? ['uuid', 'call_uuid', 'contenuto']
        pezzi.push({
          tabella: nome,
          sql:
            `CREATE TABLE IF NOT EXISTS "${schema}"."${nome}" (\n` +
            campi.map((c) => `  "${c}" text`).join(',\n') +
            ',\n  "sincronizzato_at" timestamptz NOT NULL DEFAULT now(),\n' +
            `  PRIMARY KEY ("${campi[0]}")\n)`,
        })
      }
      return { ok: true, status: 200, body: pezzi }
    }
    if (path === '/database-remoto/colonne') {
      const colonne = [
        { nome: 'id', tipo: 'text', obbligatoria: true },
        { nome: 'oggetto', tipo: 'text', obbligatoria: false },
        { nome: 'creato_il', tipo: 'timestamp with time zone', obbligatoria: false },
      ]
      const campi = (CAMPI_FINTI[dati.per] ?? ['uuid', 'titolo']).map((c, i) => ({
        chiave: c,
        etichetta: c === 'uuid' ? 'Identificatore' : c === 'titolo' ? 'Titolo' : c,
        tipo: 'testo',
        descrizione: i === 0 ? 'Stabile: non cambia mai' : '',
        chiave_naturale: i === 0,
        ammesse: colonne.filter((x) => x.tipo === 'text').map((x) => x.nome),
      }))
      return { ok: true, status: 200, body: { colonne, campi } }
    }
    return null
  }

  function notion(path, body) {
    const dati = body ?? {}
    if (path === '/export/notion/destinazioni') {
      if (!dati.token && !notionStato.collegato) {
        return { ok: false, status: 400, body: { detail: 'Manca il token di Notion: collega l’integrazione dalle impostazioni.' } }
      }
      return {
        ok: true,
        status: 200,
        body: {
          database: Object.entries(notionDatabase).map(([id, d]) => ({ id, titolo: d.titolo })),
          pagine: [
            { id: 'pag-1', titolo: 'Spazio di lavoro' },
            { id: 'pag-2', titolo: 'Progetti 2026' },
          ],
        },
      }
    }
    if (path === '/export/notion/schema') {
      const id = dati.database_id || notionStato.database_id
      const db = notionDatabase[id]
      if (!db) return { ok: false, status: 400, body: { detail: 'Il database indicato: Notion non lo trova.' } }
      return { ok: true, status: 200, body: { database_id: id, ...db } }
    }
    if (path === '/export/notion/collega') {
      const id = dati.database_id || notionStato.database_id
      Object.assign(notionStato, {
        collegato: true,
        database_id: id,
        database_titolo: dati.database_titolo || notionDatabase[id]?.titolo || null,
        mappa: dati.mappa ?? notionStato.mappa,
      })
      return { ok: true, status: 200, body: { ...notionStato } }
    }
    if (path === '/export/notion/database') {
      const scelti = dati.campi ?? []
      const mappa = {}
      for (const campo of notionCampi) {
        if (!campo.obbligatorio && scelti.includes(campo.id)) mappa[campo.id] = campo.nome_notion
      }
      const id = 'db-nuovo'
      notionDatabase[id] = {
        titolo: dati.titolo || 'Task da Scriba',
        titolo_proprieta: 'Task',
        proprieta: notionCampi.filter((c) => !c.obbligatorio && scelti.includes(c.id)).map((c) => ({ nome: c.nome_notion, tipo: c.tipi[0] })),
        mappa_proposta: mappa,
      }
      Object.assign(notionStato, { collegato: true, database_id: id, database_titolo: notionDatabase[id].titolo, mappa })
      return { ok: true, status: 200, body: { ...notionStato } }
    }
    if (path === '/export/notion/scollega') {
      Object.assign(notionStato, { collegato: false, database_id: null, database_titolo: null, mappa: {} })
      return { ok: true, status: 200, body: { ...notionStato } }
    }
    return null
  }

  // Le tre ricerche dell'archivio. Lo stato dell'indice e' una variabile e non
  // una costante di proposito: i tre casi che questa schermata deve saper
  // mostrare — modello assente, call da leggere, lettura in corso — sono stati
  // diversi della stessa barra, e l'unico modo di guardarli tutti e' poterli
  // cambiare da qui.
  const statoIndice = {
    modello_installato: true,
    call_con_parlato: 12,
    call_indicizzate: 9,
    passaggi: 486,
    in_corso: false,
    fatte: 0,
    totale: 0,
    errore: null,
  }

  function ricerca(path, body) {
    const p = path.split('?')[0]
    if (p === '/ricerca/indicizza') {
      statoIndice.call_indicizzate = statoIndice.call_con_parlato
      return { ok: true, status: 200, body: { stato: 'avviata' } }
    }
    if (p === '/ricerca/indicizza/ferma') return { ok: true, status: 200, body: { stato: 'fermata' } }
    if (p === '/ricerca/semantica') {
      // Le stesse call dell'archivio, con un passaggio al posto del titolo:
      // quello che si verifica qui e' come sono messe in pagina.
      return {
        ok: true,
        status: 200,
        body: {
          call: sessioni.slice(0, 3).map((s, i) => ({
            ...s,
            frammento: [
              'la tariffa oraria va rivista, cosi’ com’e’ non ci sta dentro',
              'sul prezzo siamo lontani: loro partono da quarantamila',
              'lo sconto lo teniamo per il rinnovo, non per il primo anno',
            ][i],
            quando_ms: 362_000 + i * 120_000,
          })),
          indicizzate: 9,
          da_indicizzare: 3,
        },
      }
    }
    if (p === '/ricerca/contestuale') {
      if (!body || !String(body.domanda || '').trim()) {
        return { ok: false, status: 400, body: { detail: 'La domanda è vuota.' } }
      }
      const unite = body.unisci_catene !== false
      return {
        ok: true,
        status: 200,
        body: {
          risposta:
            'La consegna è stata spostata a inizio maggio. Nella call del 3 marzo era '
            + 'ancora fissata per il 15 aprile: è stata cambiata il 18 marzo, quando il '
            + 'fornitore ha comunicato tre settimane di ritardo.',
          call: sessioni.slice(0, 2).map((s, i) => ({
            ...s,
            perche: [
              'Qui la data viene spostata, ed è la versione valida.',
              'Qui era ancora il 15 aprile: è la versione superata.',
            ][i],
            passaggi: [
              [{ testo: 'il fornitore ci ha spostato tutto di tre settimane', quando_ms: 421_000 }],
              [{ testo: 'la consegna è prevista per il quindici di aprile', quando_ms: 118_000 }],
            ][i],
          })),
          // La seconda call e' senza titolo di proposito: e' il caso in cui
          // la riga della catena, scritta male, lascia una freccia sospesa.
          catene: unite
            ? [{ call: sessioni.slice(0, 2).map((s) => ({ id: s.id, titolo: s.titolo })) }]
            : [],
          passaggi_letti: 18,
          modello: 'gemma-4-12b',
          provider: 'local',
          costo_usd: null,
        },
      }
    }
    return null
  }

  const RISPOSTE = {
    '/ricerca/stato': statoIndice,
    '/database-remoto/stato': {
      collegato: false,
      modalita: 'diretta',
      schema: '',
      prefisso: 'scriba_',
      automatico: true,
      tabelle: {},
      segreto_in_chiaro: false,
      server: null,
    },
    '/database-remoto/modello': MODELLO_FINTO,
    '/export/notion/stato': notionStato,
    '/export/notion/campi': notionCampi,
    '/sessions': sessioni,
    // Senza queste due voci l'archivio non si apriva affatto nell'anteprima:
    // `risolvi` tornava `null`, e `call.map` su null faceva saltare tutto
    // l'albero React. Cioe' l'unica schermata che l'anteprima non sapeva
    // mostrare era anche l'unica che non si poteva verificare.
    '/clienti': [
      { id: 1, nome: 'Ferrotecnica Sud', n_call: 6 },
      { id: 2, nome: 'Metalgraf', n_call: 4 },
    ],
    // La ricerca vera filtra lato core; qui bastano le stesse call, perche'
    // quello che si verifica e' come sono messe in pagina.
    '/archivio': sessioni,
    '/providers': providers,
    '/settings': impostazioni,
    '/modelli': modelli,
    '/disco': { cartella: 'C:\\Users\\utente\\AppData\\Scriba\\models', libero_bytes: 12 * GB, totale_bytes: 476 * GB },
    '/dispositivi': {
      microfoni: [{ id: 'mic-0', nome: 'Realtek Array', predefinito: true }, { id: 'mic-1', nome: 'Webcam', predefinito: false }],
      loopback: [{ id: 'lb-0', nome: 'Altoparlanti (loopback)', predefinito: true }],
    },
    '/dati': [
      { chiave: 'audio', etichetta: 'Registrazioni audio', path: '…\\Scriba\\audio', bytes: 4.8 * GB },
      { chiave: 'db', etichetta: 'Trascrizioni e task', path: '…\\Scriba\\scriba.db', bytes: 86 * 1024 ** 2 },
      { chiave: 'screenshots', etichetta: 'Screenshot', path: '…\\Scriba\\screenshots', bytes: 312 * 1024 ** 2 },
    ],
    '/analisi/stato': { in_corso: false, session_id: null, fasi: [] },
    // true: il comando "Distingui le voci" e lo stato "voci distinte" /
    // "DAI UN NOME ALLE VOCI" si vedono. Per provare lo stato "non
    // disponibile" (comportamento.md non lo descrive, ma il rapporto lo
    // richiede) basta mettere questo a false a mano.
    '/diarizzazione/disponibile': { disponibile: true },
    // Senza questo il modello risulta "in caricamento" e «Registra» resta
    // spento: giusto nell'app, inutile qui, dove serve arrivare al modale.
    // `db_danneggiato` valorizzato di proposito: e' lo stato che si vuole poter
    // guardare senza dover rovinare un database vero. Metterlo a null mostra
    // l'applicazione com'e' quando va tutto bene.
    '/health': {
      ok: true,
      modello: 'pronto',
      in_registrazione: false,
      db_danneggiato: {
        motivo: 'database disk image is malformed',
        quarantena: 'C:\\Users\\utente\\AppData\\Scriba\\danneggiato-2026-08-12-1405',
        ripristinato: 'C:\\Users\\utente\\AppData\\Scriba\\backup\\scriba-2026-08-12-1130.sqlite',
      },
    },
    '/session/state': { in_registrazione: false },
  }

  function risolvi(path) {
    const pulito = path.split('?')[0]
    if (pulito in RISPOSTE) return RISPOSTE[pulito]
    if (/^\/sessions\/\d+\/segments$/.test(pulito)) return segmenti
    if (/^\/sessions\/\d+\/analysis$/.test(pulito)) return analisi
    if (/^\/sessions\/\d+\/screenshots$/.test(pulito)) {
      return [{ id: 1, t_ms: 362_000, path: 'C:\\finto\\shot.png', width: 1280, height: 760, nota_utente: null }]
    }
    if (/^\/sessions\/24\/voci$/.test(pulito)) return voci24
    if (/^\/sessions\/\d+\/voci$/.test(pulito)) return vociVuote
    return null
  }

  const ok = (body) => Promise.resolve({ ok: true, status: 200, body })
  // Solo per PATCH .../voci/{id}: aggiorna la voce finta cosi' l'anteprima
  // mostra davvero il nome appena scritto, invece di limitarsi a rispondere
  // 200 senza cambiare niente.
  function rinomina(path, body) {
    const match = path.match(/^\/sessions\/\d+\/voci\/(\d+)/)
    if (!match) return { ok: false, status: 404, body: { detail: 'voce inesistente' } }
    const id = Number(match[1])
    const voce = voci24.find((v) => v.id === id)
    if (voce) {
      voce.nome_reale = body?.nome_reale ?? voce.nome_reale
      voce.confermato = true
    }
    return { ok: true, status: 200, body: { id, nome_reale: body?.nome_reale, confermato: true } }
  }

  const ascoltatori = new Set()

  window.scriba = {
    endpoint: () => Promise.resolve({ port: 1234 }),
    paths: () => Promise.resolve({ dataDir: 'C:\\finto', screenshotDir: 'C:\\finto\\shots' }),
    get: (p) => ok(risolvi(p)),
    post: (p, body) =>
      Promise.resolve(
        notion(p, body) ?? databaseRemoto(p, body) ?? ricerca(p, body) ?? { ok: true, status: 200, body: risolvi(p) ?? {} },
      ),
    patch: (p, body) => Promise.resolve(rinomina(p, body)),
    screenshot: () => Promise.resolve(),
    // Due schermi: uno solo farebbe sparire il selettore dalla topbar, che e'
    // proprio la parte che qui si vuole poter guardare.
    schermi: () =>
      Promise.resolve([
        { id: 'schermo-0', etichetta: 'Principale', larghezza: 2560, altezza: 1440, principale: true },
        { id: 'schermo-1', etichetta: 'Secondario', larghezza: 1920, altezza: 1080, principale: false },
      ]),
    mostraFile: () => Promise.resolve(),
    apriCartella: () => Promise.resolve(),
    scegliCartella: () => Promise.resolve(null),
    finestra: { riduci: () => Promise.resolve(), ingrandisci: () => Promise.resolve(), chiudi: () => Promise.resolve() },
    apriImpostazioni: () => Promise.resolve(),
    overlay: {
      nascondi: () => Promise.resolve(),
      apriPrincipale: () => Promise.resolve(),
      alternaRidotto: () => Promise.resolve(false),
    },
    registraScorciatoie: () => Promise.resolve({ overlay: 'Alt+R', screenshot: 'CommandOrControl+Shift+S' }),
    provaScorciatoia: () => Promise.resolve(true),

    // Tema e lingua arrivano dal processo principale, che qui non c'e'. Senza
    // questi due l'anteprima parte con `undefined` e cade sul ripiego, che e'
    // il caso peggiore per accorgersi di un difetto: sembra funzionare.
    temaIniziale: 'scuro',
    annunciaTema: () => Promise.resolve(),
    linguaIniziale: 'it',
    annunciaLingua: (l) => { ascoltatori.forEach((f) => f(l)); return Promise.resolve() },

    // Un solo canale, quello della lingua: serve a provare che cambiandola le
    // schermate si ridisegnano davvero, contesto compreso.
    on: (canale, cb) => {
      if (canale !== 'lingua:cambiata') return () => {}
      ascoltatori.add(cb)
      return () => ascoltatori.delete(cb)
    },
  }
})()
