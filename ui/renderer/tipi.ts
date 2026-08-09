/**
 * Le forme dei dati che il core manda all'interfaccia.
 *
 * Stanno in un file solo perché le stesse strutture attraversano finestre
 * diverse — principale, impostazioni, overlay — e tenerne una copia per
 * finestra significa vederle divergere alla prima modifica del core.
 */

// ------------------------------------------------------------------ sessioni

/**
 * Stato di una call, come lo mostra l'elenco a sinistra.
 *
 * `recording` esiste solo per la call in corso; `failed` significa che
 * l'analisi non è riuscita, non che la registrazione sia andata persa — la
 * trascrizione resta.
 */
export type StatoSessione =
  | 'recording'
  | 'recorded'
  | 'analyzing'
  | 'analyzed'
  | 'failed'

export interface Sessione {
  id: number
  titolo: string | null
  piattaforma: string | null
  started_at: number
  ended_at: number | null
  durata_ms: number | null
  stato: StatoSessione
  lingua: string | null
  /** Quante task ha prodotto l'analisi, e quante aspettano ancora una conferma. */
  n_task: number
  n_da_confermare: number
  /** null = call non attribuita a nessun cliente. */
  client_id?: number | null
  /** Il nome del cliente, gia' risolto dal core: la UI non deve incrociarlo da se'. */
  cliente?: string | null
}

/** Un cliente, con quanto lavoro gli e' gia' attribuito. */
export interface Cliente {
  id: number
  uuid: string
  nome: string
  note: string | null
  archiviato: number
  created_at: number
  /** Quante call gli sono attribuite, e quando e' stata l'ultima. */
  n_call: number
  ultima_call: number | null
}

// ------------------------------------------------------------ database remoto

/** Un campo che Scriba sa mandare, e in quali colonne remote può finire. */
export interface CampoModello {
  chiave: string
  etichetta: string
  tipo: string
  descrizione: string
  /** Serve a riconoscere una riga gia' inviata: senza, si duplica. */
  chiave_naturale: boolean
  /** Popolato solo da /database-remoto/colonne: le colonne compatibili. */
  ammesse: string[]
}

export interface TabellaModello {
  chiave: string
  etichetta: string
  descrizione: string
  predefinita: boolean
  /** Puo' essere grande (la trascrizione): si dice prima di farla scegliere. */
  voluminosa: boolean
  chiave_naturale: string[]
  campi: Omit<CampoModello, 'ammesse'>[]
}

export interface ServerRemoto {
  host: string
  porta: number
  database: string
  utente: string
  password_presente: boolean
  sslmode: string | null
  modalita_dedotta: string
}

export interface StatoDatabaseRemoto {
  collegato: boolean
  modalita: string | null
  schema: string | null
  prefisso: string | null
  automatico: boolean
  tabelle: Record<string, { nome: string; campi: string[] }>
  /** La cifratura di Windows non ha risposto: va detto, non nascosto. */
  segreto_in_chiaro: boolean
  server: ServerRemoto | null
}

export interface DatiRemoti {
  ok: boolean
  versione: string
  schemi: string[]
  modalita: string
  server: ServerRemoto
}

export interface ColonneRemote {
  colonne: Array<{ nome: string; tipo: string; obbligatoria: boolean }>
  campi: CampoModello[]
}

/** Un pezzo di DDL, mostrato prima di essere eseguito. */
export interface PezzoDdl {
  tabella: string
  sql: string
}

/** Un processo con una sessione microfono aperta, e cosa il rilevamento ne ha fatto. */
export interface ProcessoVisto {
  pid: number
  processo: string
  /** Il picco riferito dalla sonda: 0 = sessione aperta ma silenziosa. */
  picco: number
  riproduce: boolean
  /** L'audio esce da un suo figlio: il caso di una riunione nel browser. */
  riproduce_un_figlio?: boolean
  /** 'escluso' | 'in attesa' | 'in conferma' | 'riunione' | 'già proposta'. */
  esito?: string
  perche?: string
  /** Quanto manca alla conferma, se e' in conferma. */
  mancano_s?: number
}

export interface DiagnosticaRilevamento {
  /** true = spento nelle impostazioni. Diverso da "non vedo niente". */
  spento: boolean
  in_ascolto: boolean
  conferma_s: number | null
  intervallo_s: number | null
  sonda: {
    viva: boolean
    ripartenze: number
    /** Ha smesso di riprovare: nessuna riunione verra' piu' proposta. */
    rinunciato: boolean
    ultimo_motivo: string | null
    ultima_lettura_fa_s: number | null
  } | null
  /** I processi che riproducono audio, per numero: spiegano i "figlio". */
  riproducono: number[]
  processi: ProcessoVisto[]
}

/** L'esito di un import: si mostra all'utente, perche' "fatto" non basta. */
export interface EsitoImport {
  creati: number
  gia_presenti: number
  scartati: number
}

export type Traccia = 'mic' | 'loopback'

export interface Segmento {
  id: number
  source: Traccia
  t_start_ms: number
  t_end_ms: number
  testo: string
  is_final: boolean
  revision?: number
  /**
   * Chi ha parlato, quando la diarizzazione è stata eseguita su quella call.
   *
   * Resta null finché nessuno l'ha eseguita, e l'interfaccia deve reggere quel
   * caso: `source` (io / altri) viene dalla traccia da cui il suono è entrato
   * ed è l'unica cosa che non può sbagliare. Questo campo la raffina, non la
   * sostituisce.
   */
  speaker?: { id: number; label: string; nome_reale: string | null } | null
  /**
   * Il microfono ha ripreso l'altoparlante: queste parole ci sono già sulla
   * traccia degli altri, dette da chi le ha dette.
   *
   * Sono già escluse da riassunto, note ed export. Arrivano fino a qui perché
   * la trascrizione è l'unico posto in cui si può controllare che il giudizio
   * fosse giusto — nasconderle ovunque sarebbe cancellarle con un altro nome.
   */
  eco?: boolean
}

export interface Scatto {
  id: number
  t_ms: number
  path: string
  width: number | null
  height: number | null
  nota_utente: string | null
}

/**
 * Un partecipante conosciuto per una sessione: `GET /sessions/{id}/voci`.
 *
 * Prima di una diarizzazione ce ne sono sempre e solo due per sessione
 * (`ruolo: 'me'` con label «io», `ruolo: 'them'` con label «altri») — li crea
 * il core insieme alla sessione stessa. Dopo, `ruolo: 'them'` può comparire
 * più volte, una per voce distinta trovata («Voce 2», «Voce 3», …).
 */
export interface Voce {
  id: number
  ruolo: 'me' | 'them'
  label: string
  nome_reale: string | null
  confermato: boolean
}

// ------------------------------------------------------------------- analisi

/** Il campo della task che una prova sostiene. Una prova per campo, non per task. */
export type CampoProva =
  | 'titolo'
  | 'descrizione'
  | 'assignee'
  | 'due_date'
  | 'priorita'
  | 'esistenza'

export interface Prova {
  supports: CampoProva | string
  t_ms: number
  quote: string | null
  segment_id: number | null
}

export type StatoTask = 'proposed' | 'confirmed' | 'rejected'

export interface Task {
  id: number
  titolo: string
  descrizione: string | null
  assignee_text: string | null
  /** Data risolta, quando è stato possibile ricavarla senza inventare. */
  due_date: string | null
  /** Come è stata detta a voce: «entro il quattordici». Resta accanto alla data. */
  due_raw: string | null
  priorita: string | null
  stato: StatoTask
  confidence: number | null
  needs_review: number
  review_reason: string | null
  evidence: Prova[]
}

/** Un punto saliente: etichetta breve, corpo, e il minuto da cui viene. */
export interface PuntoSaliente {
  t_ms: number
  etichetta: string
  corpo: string
}

/** Il riassunto arriva raggruppato per argomento, con i minuti a cui rimandare. */
export interface GruppoRiassunto {
  titolo: string
  voci: Array<{ testo: string; t_ms: number | null }>
}

export interface MetaAnalisi {
  provider: string | null
  /** Come va scritto in interfaccia: «API Anthropic», «Modello locale». */
  etichetta_provider: string | null
  modello: string | null
  costo_usd: number | null
  durata_ms: number | null
  finita_at: number | null
}

export interface Analisi {
  /** Markdown grezzo, conservato: è ciò che il modello ha davvero prodotto. */
  riassunto: string | null
  punti_salienti: string | null
  /** Le stesse cose, già divise in pezzi. Vuote se il testo non era interpretabile. */
  riassunto_gruppi: GruppoRiassunto[]
  salienti: PuntoSaliente[]
  tasks: Task[]
  meta: MetaAnalisi | null
  errore: string | null
}

/** Una delle quattro fasi mostrate mentre l'analisi gira. */
export interface FaseAnalisi {
  chiave: 'riassunto' | 'salienti' | 'task' | 'unione'
  titolo: string
  stato: 'attesa' | 'in_corso' | 'fatta'
  /** «38 s», «3 di 6 blocchi», «in attesa». */
  nota: string | null
}

export interface StatoAnalisi {
  in_corso: boolean
  session_id: number | null
  fasi: FaseAnalisi[]
}

// -------------------------------------------------------------- impostazioni

export interface Provider {
  id: string
  etichetta: string
  descrizione: string
  model: string
  disponibile: boolean
  attivo: boolean
  /** Vero quando la trascrizione lascia il computer. Va detto sempre. */
  esce_dal_computer: boolean
  /** Costo indicativo per un'ora di call, in euro. Null quando non si paga. */
  costo_ora_usd: number | null
  /** Minuti indicativi per analizzare un'ora di call. */
  minuti_per_ora: number | null
  /** Cosa manca perché sia utilizzabile, quando non lo è. */
  rimedio: string | null
  /**
   * Il modello locale è partito ma non risponde ancora: caricarlo richiede
   * decine di secondi. Non è «disponibile», ma nemmeno un guasto — e dirgli
   * «non disponibile» mentre carica manda l'utente a cercare un problema che
   * non c'è.
   */
  in_avvio: boolean
}

export type StatoModello =
  | 'non_installato'
  | 'in_download'
  | 'in_pausa'
  | 'in_verifica'
  | 'installato'
  /** Il processo è partito, il modello si sta caricando in memoria. */
  | 'in_avvio'
  | 'in_uso'
  | 'spazio_insufficiente'
  | 'errore'

export interface Modello {
  id: string
  nome: string
  /** A cosa serve: trascrizione o analisi. */
  uso: 'trascrizione' | 'analisi'
  size_bytes: number
  stato: StatoModello
  /** Byte già sul disco: serve a riprendere un download interrotto. */
  scaricati_bytes: number
  velocita_bps: number | null
  secondi_rimanenti: number | null
  installato_at: number | null
  /** Nota sotto il nome: «più veloce di whisper, meno preciso sui nomi propri». */
  nota: string | null
  errore: string | null
  /** Solo per il modello di analisi acceso: dove risponde e quanta RAM occupa. */
  endpoint: string | null
  ram_bytes: number | null
}

export interface Disco {
  cartella: string
  libero_bytes: number
  totale_bytes: number
}

/**
 * Presente in `GET /health` solo quando all'avvio il database non era leggibile
 * ed è stato messo da parte (`db/manutenzione.py`).
 *
 * Non è un dettaglio tecnico da log: l'elenco delle call torna indietro, e chi
 * guarda l'applicazione deve sapere perché e dove sono finiti i suoi file.
 */
export interface DbDanneggiato {
  /** Cosa ha detto il controllo di integrità. */
  motivo: string
  /** La cartella dove sono finiti il database rotto e il suo WAL. */
  quarantena: string
  /** Il backup da cui si è ripartiti. Stringa vuota se non ce n'era nessuno. */
  ripristinato: string
}

export interface Dispositivo {
  id: string
  nome: string
  predefinito: boolean
}

export interface Dispositivi {
  microfoni: Dispositivo[]
  loopback: Dispositivo[]
}

export interface VoceDati {
  chiave: 'audio' | 'db' | 'screenshots'
  etichetta: string
  path: string
  bytes: number
}

export interface Impostazioni {
  llm: {
    provider: string
    base_url: string
    model: string
    api_key_presente: boolean
  }
  stt: {
    provider: string
    lingua: string
    microfono_id?: string | null
    loopback_id?: string | null
    filtro_eco?: 'basso' | 'medio' | 'alto'
    /** Nomi propri che il modello sbaglia, rimessi a posto dopo la trascrizione. */
    glossario?: string[]
    glossario_livello?: 'prudente' | 'medio' | 'aggressivo'
    glossario_clienti?: boolean
    /** Ripassa la trascrizione con Canary a fine call, prima dell'analisi. */
    rifinitura_automatica?: boolean
  }
  analisi_automatica: boolean
  note_incrementali?: boolean
  /** Secondi fra una nota e l'altra. Il core la legge al volo con un default di 600. */
  note_incrementali_intervallo_s?: number
  interfaccia: {
    scorciatoia_overlay: string
    scorciatoia_screenshot: string
    righe_overlay: number
    opacita_overlay: number
    overlay_ridotto?: boolean
    /** 'scuro' | 'chiaro' | 'sistema'. Vedi renderer/tema.ts. */
    tema?: string
  }
  rilevamento: {
    attivo: boolean
    avvio_automatico: boolean
    conferma_s: number
  }
  export?: {
    cartella: string | null
    /** 'contesto' e' il documento per un modello: vedi export/contesto.py. */
    formato: 'markdown' | 'testo' | 'json' | 'contesto'
  }
}

// -------------------------------------------------------------------- notion

/** Un dato che Scriba sa di una task, e i tipi di proprietà Notion che lo reggono. */
export interface CampoNotion {
  id: string
  etichetta: string
  aiuto: string
  tipi: string[]
  /** Come si chiamerà la colonna, se il database lo crea Scriba. */
  nome_notion: string
  consigliato: boolean
  /** Il titolo: non si mappa, va sempre nella proprietà titolo del database. */
  obbligatorio: boolean
}

export interface StatoNotion {
  collegato: boolean
  database_id: string | null
  database_titolo: string | null
  /** id del campo → nome della proprietà Notion. Vuota = ancora da scegliere. */
  mappa: Record<string, string>
}

export interface DestinazioneNotion {
  id: string
  titolo: string
}

/** Cosa l'integrazione può vedere: database da adattare, pagine dove crearne uno. */
export interface DestinazioniNotion {
  database: DestinazioneNotion[]
  pagine: DestinazioneNotion[]
}

export interface ProprietaNotion {
  nome: string
  tipo: string
}

export interface SchemaNotion {
  database_id: string
  titolo: string
  titolo_proprieta: string
  proprieta: ProprietaNotion[]
  mappa_proposta: Record<string, string>
}

// -------------------------------------------------------------------- eventi

/** Eventi che il core spinge sul websocket, girati alle finestre dal main. */
export type EventoCore =
  | { type: 'transcript'; source: Traccia; t_start_ms: number; t_end_ms: number; text: string; is_final: boolean }
  | {
      type: 'session_started'
      session_id: number
      titolo: string | null
      /** Il nome vero della periferica aperta, per sorgente («mic», «loopback»). */
      devices?: Record<string, string>
      /** Le sorgenti ripiegate sul predefinito perché quella scelta nelle
       *  impostazioni non c'è più. Il core lo manda da sempre; fino a #73 qui
       *  non era nemmeno dichiarato, quindi nessuno lo leggeva e chi
       *  registrava dal microfono sbagliato lo scopriva a call finita. */
      fallback?: Record<string, string>
    }
  | { type: 'session_stopped'; session_id: number; durata_ms: number | null }
  | { type: 'screenshot'; id: number; t_ms: number; path: string }
  | {
      type: 'call_rilevata'
      pid: number
      processo: string
      nome: string
      piattaforma: string
      /**
       * L'utente ha chiesto che Scriba si attivi da solo quando riconosce una
       * call. Non vuol dire registrare senza permesso: la spunta sul consenso
       * resta obbligatoria. Cambia solo l'insistenza — invece di una proposta
       * che si può ignorare, la finestra del consenso si apre da sé.
       */
      avvio_automatico?: boolean
    }
  | { type: 'modello'; stato: 'in_attesa' | 'caricamento' | 'pronto' | 'errore'; dettaglio?: string }
  | { type: 'analisi'; stato: 'in_corso' | 'fatto' | 'errore'; session_id: number; dettaglio?: string; fasi?: FaseAnalisi[] }
  | { type: 'modello_locale'; modello: Modello }
  | {
      type: 'diarizzazione'
      stato: 'in_corso' | 'fatto' | 'errore' | 'voce_rinominata'
      session_id: number
      /** Solo con stato 'in_corso': avanzamento 0..1 e la fase corrente in parole. */
      frazione?: number
      nota?: string
      /** Solo con stato 'errore'. */
      dettaglio?: string
      /** Solo con stato 'fatto': quante voci nuove, quanti segmenti riassegnati. */
      voci?: number
      segmenti_assegnati?: number
      /** Solo con stato 'voce_rinominata'. */
      speaker_id?: number
      nome_reale?: string
    }
  | { type: string; [k: string]: unknown }

// ----------------------------------------------------------------- formattazione

/** mm:ss, oppure h:mm:ss oltre l'ora. La trascrizione ne è piena. */
export function tempo(ms: number): string {
  const totale = Math.max(0, Math.floor(ms / 1000))
  const s = totale % 60
  const m = Math.floor(totale / 60) % 60
  const h = Math.floor(totale / 3600)
  const dueCifre = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${dueCifre(m)}:${dueCifre(s)}` : `${dueCifre(m)}:${dueCifre(s)}`
}

/** «12 ago · 14:05». Oggi diventa «oggi», che è come lo si direbbe a voce. */
export function giornoBreve(epochMs: number): string {
  const d = new Date(epochMs)
  const oggi = new Date()
  const stessoGiorno =
    d.getFullYear() === oggi.getFullYear() &&
    d.getMonth() === oggi.getMonth() &&
    d.getDate() === oggi.getDate()
  return stessoGiorno
    ? 'oggi'
    : d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' }).replace('.', '')
}

/** «12 ago · 14:05». Dove serve anche l'ora del giorno.
 *
 *  Non nell'elenco call: li' la riga porta giorno e **durata**, e infilarci in
 *  mezzo anche l'ora faceva tre voci separate da due puntini dove il design ne
 *  ha due (comportamento.md, 0-bis: meno elementi, non solo piu' spazio). */
export function dataBreve(epochMs: number): string {
  const d = new Date(epochMs)
  const ora = d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
  return `${giornoBreve(epochMs)} · ${ora}`
}

/** «6,4 GB», «312 MB». Virgola decimale: l'interfaccia è in italiano. */
export function dimensione(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const unita = ['KB', 'MB', 'GB', 'TB']
  let valore = bytes / 1024
  let i = 0
  while (valore >= 1024 && i < unita.length - 1) {
    valore /= 1024
    i += 1
  }
  const cifre = valore < 10 && i >= 2 ? 1 : 0
  return `${valore.toFixed(cifre).replace('.', ',')} ${unita[i]}`
}

/** «Alt + R»: come sta sul tasto, non come lo scrive Electron. */
export function scorciatoiaLeggibile(combo: string | null): string {
  if (!combo) return '—'
  return combo
    .replace('CommandOrControl', 'Ctrl')
    .replace('CmdOrCtrl', 'Ctrl')
    .split('+')
    .join(' + ')
}
