-- Schema di Scriba.
--
-- Due vincoli guidano quasi tutte le scelte qui dentro:
--
-- 1. Durante la call il processo STT scrive di continuo mentre la UI legge per
--    mostrare il testo: serve WAL, altrimenti si bloccano a vicenda.
-- 2. Ogni task deve poter dimostrare da dove viene. I riferimenti alla
--    trascrizione devono restare validi anche quando un segmento provvisorio
--    viene rifinito, il che esclude di cancellare e reinserire i segmenti.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ----------------------------------------------------------------- clienti --

-- Per chi lavora su commessa la domanda vera non è "cos'ho fatto ieri" ma
-- "cosa ci siamo detti con questo cliente negli ultimi tre mesi". Senza una
-- tabella, quella domanda si risponde solo rileggendo i titoli a occhio.
--
-- Una tabella e non un campo di testo su `sessions`: rinominare un cliente
-- deve valere per tutte le sue call insieme, e un testo libero diventa in
-- fretta tre grafie diverse della stessa azienda.
--
-- Dichiarata prima di `sessions` perché quella la referenzia.
CREATE TABLE IF NOT EXISTS clients (
  id         INTEGER PRIMARY KEY,
  uuid       TEXT    NOT NULL UNIQUE,   -- id stabile per export e sync
  nome       TEXT    NOT NULL,
  -- Il nome ridotto a una forma confrontabile: minuscolo, spazi normalizzati.
  -- È qui che si decide se due righe di un CSV importato sono lo stesso
  -- cliente, e va deciso una volta sola invece che a ogni confronto.
  nome_norm  TEXT    NOT NULL UNIQUE,
  note       TEXT,
  -- Archiviato invece che eliminato: un cliente con cui non si lavora più
  -- sparisce dagli elenchi ma le sue call restano attribuite a qualcuno.
  archiviato INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);

-- ---------------------------------------------------------------- sessioni --

CREATE TABLE IF NOT EXISTS sessions (
  id                INTEGER PRIMARY KEY,
  uuid              TEXT    NOT NULL UNIQUE,   -- id stabile per export e sync
  titolo            TEXT,
  piattaforma       TEXT,                      -- zoom | meet | teams | altro | sconosciuta
  piattaforma_conf  REAL,                      -- confidenza del rilevamento
  started_at        INTEGER NOT NULL,          -- epoch ms UTC
  ended_at          INTEGER,
  durata_ms         INTEGER,
  audio_mic_path    TEXT,                      -- tracce separate: consentono di ri-trascrivere
  audio_loop_path   TEXT,                      --   una sola sorgente senza rifare tutto
  stato             TEXT    NOT NULL DEFAULT 'recording'
                    CHECK (stato IN ('recording','transcribing','ready','analyzed','error')),
  stt_model         TEXT,
  stt_quantization  TEXT,
  lingua            TEXT    DEFAULT 'it',
  -- Registrare gli altri partecipanti è una responsabilità: si annota che
  -- l'utente ha confermato di averli avvisati, e quando.
  consenso_confermato_at INTEGER,
  note_utente       TEXT,
  -- Su un database creato prima dei clienti questa colonna arriva da un
  -- ALTER TABLE, che in SQLite non può portarsi dietro la chiave esterna: lì
  -- resta un intero e basta. Perché la differenza non si veda da nessuna
  -- parte, a ripulire i riferimenti di un cliente eliminato pensa
  -- `Store.elimina_cliente`, non il vincolo.
  client_id         INTEGER REFERENCES clients(id) ON DELETE SET NULL,
  created_at        INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);

CREATE INDEX IF NOT EXISTS ix_sessions_started ON sessions(started_at DESC);

-- ------------------------------------------------------------ partecipanti --

CREATE TABLE IF NOT EXISTS speakers (
  id          INTEGER PRIMARY KEY,
  session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  ruolo       TEXT    NOT NULL CHECK (ruolo IN ('me','them')),
  label       TEXT    NOT NULL,        -- 'io' | 'Voce 2' | 'Marco Rossi'
  nome_reale  TEXT,                    -- confermato dall'utente in review
  email       TEXT,
  external_id TEXT,                    -- id nel servizio di export (es. persona Notion)
  confermato  INTEGER NOT NULL DEFAULT 0,
  UNIQUE (session_id, label)
);

-- ------------------------------------------------------------ trascrizione --

CREATE TABLE IF NOT EXISTS transcript_segments (
  id          INTEGER PRIMARY KEY,
  session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  speaker_id  INTEGER REFERENCES speakers(id) ON DELETE SET NULL,
  -- Da quale sorgente arriva il suono. È esatto per costruzione e non va MAI
  -- sovrascritto da un'inferenza: i nomi dei parlanti sono un livello a parte.
  source      TEXT    NOT NULL CHECK (source IN ('mic','loopback')),
  t_start_ms  INTEGER NOT NULL,        -- offset dall'inizio della sessione
  t_end_ms    INTEGER NOT NULL,
  testo       TEXT    NOT NULL,
  -- Com'era prima che il glossario rimettesse a posto i nomi propri (vedi
  -- stt/glossario.py). NULL quando non è stato corretto niente, che è il caso
  -- normale. Serve a rendere la correzione verificabile: l'app sta mettendo in
  -- bocca a qualcuno una parola che il modello non ha sentito, e chi rilegge
  -- deve poter risalire a cosa c'era scritto.
  testo_originale TEXT,
  confidence  REAL,
  -- Il testo compare provvisorio mentre si parla e viene rifinito a fine frase.
  -- Il record resta lo stesso: si aggiorna testo e si incrementa revision, così
  -- le evidence che puntano qui non si rompono.
  is_final    INTEGER NOT NULL DEFAULT 0,
  revision    INTEGER NOT NULL DEFAULT 0,
  CHECK (t_end_ms >= t_start_ms)
);

CREATE INDEX IF NOT EXISTS ix_seg_session_time ON transcript_segments(session_id, t_start_ms);
CREATE INDEX IF NOT EXISTS ix_seg_pending ON transcript_segments(session_id) WHERE is_final = 0;

-- Ricerca full-text su tutte le call. Indice esterno: il testo resta in
-- transcript_segments, qui c'è solo l'indice.
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
  testo,
  content='transcript_segments',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS trg_seg_ai AFTER INSERT ON transcript_segments BEGIN
  INSERT INTO segments_fts(rowid, testo) VALUES (new.id, new.testo);
END;

CREATE TRIGGER IF NOT EXISTS trg_seg_ad AFTER DELETE ON transcript_segments BEGIN
  INSERT INTO segments_fts(segments_fts, rowid, testo) VALUES ('delete', old.id, old.testo);
END;

CREATE TRIGGER IF NOT EXISTS trg_seg_au AFTER UPDATE OF testo ON transcript_segments BEGIN
  INSERT INTO segments_fts(segments_fts, rowid, testo) VALUES ('delete', old.id, old.testo);
  INSERT INTO segments_fts(rowid, testo) VALUES (new.id, new.testo);
END;

-- ------------------------------------------------------------- screenshot --

CREATE TABLE IF NOT EXISTS screenshots (
  id          INTEGER PRIMARY KEY,
  session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  t_ms        INTEGER NOT NULL,        -- istante della call, chiesto al core
  path        TEXT    NOT NULL,
  thumb_path  TEXT,
  width       INTEGER,
  height      INTEGER,
  ocr_text    TEXT,                    -- se copre già il contenuto, si evita di
                                       -- mandare l'immagine all'LLM
  caption_ai  TEXT,
  nota_utente TEXT,                    -- segnale forte di rilevanza
  phash       TEXT,                    -- dedup di slide identiche
  usato_in_ai INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_shot_session_time ON screenshots(session_id, t_ms);

-- -------------------------------------------------------------- output AI --

CREATE TABLE IF NOT EXISTS ai_outputs (
  id             INTEGER PRIMARY KEY,
  session_id     INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  kind           TEXT    NOT NULL CHECK (kind IN
                 ('running_note','summary','highlights','decisions','risks','custom')),
  -- NULL,NULL = riguarda tutta la call; altrimenti la finestra coperta.
  scope_start_ms INTEGER,
  scope_end_ms   INTEGER,
  content_md     TEXT    NOT NULL,
  content_json   TEXT,
  model          TEXT    NOT NULL,
  provider       TEXT    NOT NULL,     -- local | anthropic | openai
  prompt_id      TEXT    NOT NULL,
  prompt_version TEXT    NOT NULL,
  version        INTEGER NOT NULL DEFAULT 1,
  -- Le rigenerazioni non cancellano le precedenti: servono a confrontare le
  -- versioni di prompt fra loro.
  is_current     INTEGER NOT NULL DEFAULT 1,
  tokens_in      INTEGER,
  tokens_out     INTEGER,
  cost_usd       REAL,
  created_at     INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_current
  ON ai_outputs(session_id, kind, IFNULL(scope_start_ms, -1))
  WHERE is_current = 1;

-- ------------------------------------------------------------------ task --

CREATE TABLE IF NOT EXISTS tasks (
  id            INTEGER PRIMARY KEY,
  session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  titolo        TEXT    NOT NULL,
  descrizione   TEXT,
  assignee_speaker_id INTEGER REFERENCES speakers(id) ON DELETE SET NULL,
  assignee_text TEXT,                  -- quando non si risolve a un partecipante
  due_date      TEXT,                  -- ISO 8601, risolta
  due_raw       TEXT,                  -- 'entro fine mese': conserva l'ambiguità
  priorita      TEXT CHECK (priorita IN ('bassa','media','alta','critica')),
  stato         TEXT    NOT NULL DEFAULT 'proposed'
                CHECK (stato IN ('proposed','confirmed','rejected','merged','done')),
  merged_into_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  confidence    REAL,
  needs_review  INTEGER NOT NULL DEFAULT 1,
  review_reason TEXT,
  ai_output_id  INTEGER REFERENCES ai_outputs(id) ON DELETE SET NULL,
  export_status TEXT    NOT NULL DEFAULT 'none'
                CHECK (export_status IN ('none','pending','synced','error')),
  export_target TEXT,                  -- notion | http | ...
  export_ref    TEXT,                  -- id remoto: rende l'export idempotente
  exported_at   INTEGER,
  export_error  TEXT,
  created_at    INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);

CREATE INDEX IF NOT EXISTS ix_task_session ON tasks(session_id, stato);
CREATE INDEX IF NOT EXISTS ix_task_export ON tasks(export_status) WHERE export_status <> 'synced';

-- Da dove viene ogni singolo campo di una task.
--
-- È la tabella che risolve il problema centrale del progetto: in una call vera
-- il lavoro si nomina al minuto 5, la scadenza si concorda al 32 e il
-- responsabile si decide al 48. La granularità è quindi per CAMPO, non per
-- task, altrimenti non si può mostrare "questa scadenza viene da qui".
CREATE TABLE IF NOT EXISTS task_evidence (
  id            INTEGER PRIMARY KEY,
  task_id       INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  segment_id    INTEGER REFERENCES transcript_segments(id) ON DELETE SET NULL,
  screenshot_id INTEGER REFERENCES screenshots(id) ON DELETE SET NULL,
  t_ms          INTEGER NOT NULL,
  -- Copia del testo al momento dell'estrazione. Duplicata di proposito: se il
  -- segmento viene poi rifinito, la citazione già mostrata all'utente non
  -- cambia sotto i suoi occhi.
  quote         TEXT,
  supports      TEXT    NOT NULL CHECK (supports IN
                ('titolo','descrizione','assignee','due_date','priorita','esistenza')),
  weight        REAL    NOT NULL DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS ix_ev_task ON task_evidence(task_id, t_ms);
CREATE INDEX IF NOT EXISTS ix_ev_segment ON task_evidence(segment_id);

-- --------------------------------------------------------------- versione --

CREATE TABLE IF NOT EXISTS schema_version (
  version    INTEGER NOT NULL,
  applied_at INTEGER NOT NULL DEFAULT (unixepoch() * 1000)
);
