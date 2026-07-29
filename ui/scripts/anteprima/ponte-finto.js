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
    ['mic', 1904, 'Quando li vogliamo pronti?'],
    ['loopback', 1920, 'Diciamo entro il quattordici, così abbiamo una settimana per rivederli.'],
    ['mic', 1938, 'Il quattordici è un venerdì, va bene.'],
    ['loopback', 2851, 'Ultima cosa: chi ci mette mano?'],
    ['loopback', 2880, 'Per i mockup se ne occupa Marco, ha già fatto quelli del portale.'],
    ['mic', 2902, 'Perfetto, gli passo io il contesto e i link al portale.'],
  ]

  const segmenti = righe.map(([source, s, testo], i) => ({
    id: i + 1,
    source,
    t_start_ms: s * 1000,
    t_end_ms: (s + 4) * 1000,
    testo,
    is_final: true,
  }))

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
    { id: 'local', etichetta: 'Modello locale', descrizione: 'Non esce nulla dal computer.', model: 'gemma-4-12b-it', disponibile: true, attivo: false, esce_dal_computer: false, costo_ora_eur: null, minuti_per_ora: 10, rimedio: null },
    { id: 'claude-cli', etichetta: 'Abbonamento Claude', descrizione: 'Usa un abbonamento già attivo, nessun costo a consumo.', model: 'sonnet', disponibile: true, attivo: false, esce_dal_computer: true, costo_ora_eur: null, minuti_per_ora: 3, rimedio: null },
    { id: 'anthropic', etichetta: 'API Anthropic', descrizione: 'Si paga a consumo, circa 0,04 € per un’ora di call.', model: 'claude-sonnet-5', disponibile: true, attivo: true, esce_dal_computer: true, costo_ora_eur: 0.04, minuti_per_ora: 3, rimedio: null },
    { id: 'openai', etichetta: 'API OpenAI', descrizione: 'Si paga a consumo, circa 0,05 € per un’ora di call.', model: 'gpt-5-mini', disponibile: false, attivo: false, esce_dal_computer: true, costo_ora_eur: 0.05, minuti_per_ora: 3, rimedio: 'Serve una chiave API' },
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
    export: { cartella: 'C:\\Users\\antonio\\Documenti\\Scriba', formato: 'markdown' },
  }

  const RISPOSTE = {
    '/sessions': sessioni,
    '/providers': providers,
    '/settings': impostazioni,
    '/modelli': modelli,
    '/disco': { cartella: 'C:\\Users\\antonio\\AppData\\Scriba\\models', libero_bytes: 12 * GB, totale_bytes: 476 * GB },
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
    // Senza questo il modello risulta "in caricamento" e «Registra» resta
    // spento: giusto nell'app, inutile qui, dove serve arrivare al modale.
    '/health': { ok: true, modello: 'pronto', in_registrazione: false },
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
    return null
  }

  const ok = (body) => Promise.resolve({ ok: true, status: 200, body })

  window.scriba = {
    endpoint: () => Promise.resolve({ port: 1234 }),
    paths: () => Promise.resolve({ dataDir: 'C:\\finto', screenshotDir: 'C:\\finto\\shots' }),
    get: (p) => ok(risolvi(p)),
    post: (p) => ok(risolvi(p) ?? {}),
    screenshot: () => Promise.resolve(),
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
    on: () => () => {},
  }
})()
