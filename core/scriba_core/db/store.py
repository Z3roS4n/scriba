"""Accesso al database di Scriba.

Il punto delicato di questo modulo è che durante una call ci sono due scrittori
(la trascrizione del microfono e quella dell'audio di sistema) e almeno un
lettore (la UI che mostra il testo mentre si parla). Da qui il WAL e le
connessioni per-thread: SQLite non condivide una connessione fra thread, e
provarci dà errori che compaiono solo sotto carico.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1

# Tabella aggiunta per l'esito dell'analisi, tenuta fuori da schema.sql invece
# di modificarlo: session_id come chiave permette un UPSERT che aggiorna
# l'ultimo tentativo senza doverlo cercare prima. `errore` e le altre colonne
# si aggiornano indipendentemente (vedi set_analysis_meta/set_analysis_errore):
# una call già analizzata con successo deve continuare a mostrare quel
# risultato anche se un "Rianalizza" successivo fallisce.
_SCHEMA_EXTRA = """
CREATE TABLE IF NOT EXISTS analysis_meta (
  session_id          INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
  provider            TEXT,
  etichetta_provider  TEXT,
  modello             TEXT,
  costo_usd           REAL,
  durata_ms           INTEGER,
  finita_at           INTEGER,
  errore              TEXT
);
"""


@dataclass(frozen=True)
class Segment:
    """Un pezzo di trascrizione, provvisorio o definitivo."""

    id: int
    session_id: int
    source: str
    t_start_ms: int
    t_end_ms: int
    testo: str
    is_final: bool
    revision: int
    confidence: float | None = None
    # Popolati solo se la sessione è stata diarizzata (vedi stt/diarizzazione.py).
    # Restano None per ogni chiamante che non li chiede esplicitamente: nessuno
    # dei call site esistenti li legge, quindi aggiungerli qui non cambia il
    # comportamento di chi già usa `Segment` con `is_final`/`confidence` posizionali
    # in coda — sono ulteriori campi opzionali, non un cambio di firma.
    speaker_id: int | None = None
    speaker_label: str | None = None
    speaker_nome_reale: str | None = None


class Store:
    """Connessioni SQLite per thread, sullo stesso file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_lock = threading.Lock()
        with self._init_lock:
            self._migrate()

    # ------------------------------------------------------------ connessioni

    @property
    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, isolation_level=None, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            # NORMAL invece di FULL: con il WAL è sicuro rispetto ai crash del
            # processo, e togliere un fsync per ogni segmento conta quando se ne
            # scrive uno al secondo per due tracce.
            conn.execute("PRAGMA synchronous = NORMAL")
            # Quanto aspettare se un altro thread sta scrivendo. Serve insieme a
            # BEGIN IMMEDIATE più sotto: da solo non basta.
            conn.execute("PRAGMA busy_timeout = 10000")
            self._local.conn = conn
        return conn

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self.conn
        # IMMEDIATE, non il BEGIN semplice. Un BEGIN normale è "deferred": prende
        # il lock di scrittura solo alla prima scrittura vera e, se nel frattempo
        # l'ha preso qualcun altro, non può più aspettare e fallisce subito con
        # "database is locked", ignorando il busy_timeout. Chiedendo il lock
        # subito, l'attesa funziona. Con due trascrittori che scrivono in
        # parallelo durante una call, la differenza è fra funzionare e no.
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    def consolida(self, tentativi: int = 3) -> bool:
        """Travasa il WAL dentro il database e lo azzera.

        Senza questo, tutto ciò che una call scrive resta nel solo file `-wal`
        finché SQLite non decide di consolidarlo — e il consolidamento
        automatico è **passivo**: rinuncia in silenzio se un'altra connessione
        sta usando il WAL, che durante una call è sempre vero (due tracce
        scrivono un segmento al secondo, e l'interfaccia legge di continuo).

        Non è teoria: su questo progetto sono rimaste 24 ore di lavoro dentro un
        WAL da 4 MB mentre il database restava fermo allo stato di due giorni
        prima. Un WAL che nessuno consolida è l'unica copia di quei dati, e
        basta un riavvio andato storto per non averla più.

        Va chiamata quando c'è qualcosa da mettere in sicurezza — fine
        registrazione, fine analisi, spegnimento — e **fuori** da una
        transazione: dentro, il PRAGMA non fa nulla.

        Restituisce False se il WAL è rimasto occupato: chi chiama non deve
        trattarlo come un guasto (i dati sono comunque scritti e leggibili),
        ma è giusto che finisca nei log.
        """
        for tentativo in range(tentativi):
            occupato, _, _ = self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if not occupato:
                return True
            time.sleep(0.2 * (tentativo + 1))
        log.warning("Il WAL è rimasto occupato: consolidamento rinviato (%s)", self.path.name)
        return False

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -------------------------------------------------------------- migrazioni

    def _migrate(self) -> None:
        conn = self.conn
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.executescript(_SCHEMA_EXTRA)
        self._migra_colonna_diarizzata_at(conn)
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        if row is None or row["v"] is None:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))

    @staticmethod
    def _migra_colonna_diarizzata_at(conn: sqlite3.Connection) -> None:
        """Aggiunge `sessions.diarizzata_at` ai database creati prima della diarizzazione.

        Serve a distinguere "nessuno ha ancora eseguito la diarizzazione su
        questa call" da "eseguita, e non ha trovato altre voci oltre 'altri'":
        senza questa colonna il secondo caso sarebbe indistinguibile dal
        primo, e `GET /sessions/{id}/segments` non saprebbe quando può
        smettere di mandare `speaker: null` (vedi contratto-moduli.md).

        `CREATE TABLE IF NOT EXISTS` in schema.sql non aggiunge colonne a una
        tabella che esiste già, e SQLite non ha un `ADD COLUMN IF NOT
        EXISTS`: si controlla a mano con `PRAGMA table_info`, com'è già
        `analysis_meta` in `_SCHEMA_EXTRA` a stare fuori da schema.sql invece
        di modificare la CREATE TABLE originale.
        """
        colonne = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
        if "diarizzata_at" not in colonne:
            conn.execute("ALTER TABLE sessions ADD COLUMN diarizzata_at INTEGER")

    # --------------------------------------------------------------- sessioni

    def create_session(
        self,
        started_at_ms: int,
        *,
        titolo: str | None = None,
        piattaforma: str | None = None,
        lingua: str = "it",
        stt_model: str | None = None,
        consenso_confermato_at: int | None = None,
    ) -> int:
        with self.tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO sessions
                  (uuid, titolo, piattaforma, started_at, lingua, stt_model,
                   consenso_confermato_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    titolo,
                    piattaforma,
                    started_at_ms,
                    lingua,
                    stt_model,
                    consenso_confermato_at,
                ),
            )
            session_id = int(cur.lastrowid)
            # I due ruoli esistono sempre: derivano dalla sorgente audio, non da
            # un'inferenza, quindi si creano insieme alla sessione.
            conn.executemany(
                "INSERT INTO speakers (session_id, ruolo, label) VALUES (?, ?, ?)",
                [(session_id, "me", "io"), (session_id, "them", "altri")],
            )
            return session_id

    def end_session(self, session_id: int, ended_at_ms: int) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE sessions
                   SET ended_at = ?,
                       durata_ms = ? - started_at,
                       stato = CASE WHEN stato = 'recording' THEN 'transcribing' ELSE stato END
                 WHERE id = ?
                """,
                (ended_at_ms, ended_at_ms, session_id),
            )

    def set_session_state(self, session_id: int, stato: str) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE sessions SET stato = ? WHERE id = ?", (stato, session_id))

    def chiudi_sessioni_appese(self) -> list[int]:
        """Rimette in ordine le sessioni rimaste 'recording' da un avvio morto male.

        Se il core viene ucciso mentre registra, nessuno chiama `end_session` e
        quella riga resta 'recording' per sempre: l'elenco continua a mostrare
        una call in corso che non esiste, e la trascrizione sotto non arriverà
        mai. Va sistemato all'avvio, perché è l'unico momento in cui si sa con
        certezza che nessuno sta registrando — il core è appena partito.

        La fine si prende dall'ultimo segmento trascritto, non dall'ora
        corrente: fra il crash e il riavvio possono passare giorni, e scriverli
        dentro la durata di una riunione la renderebbe assurda. Senza nemmeno un
        segmento resta l'istante di inizio, cioè durata zero: si è perso tutto,
        e dirlo è meglio che inventare una durata.
        """
        with self.tx() as conn:
            appese = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM sessions WHERE stato = 'recording' OR ended_at IS NULL"
                )
            ]
            if not appese:
                return []
            conn.execute(
                """
                UPDATE sessions
                   SET ended_at = COALESCE(
                           (SELECT MAX(t_end_ms) + started_at
                              FROM transcript_segments
                             WHERE session_id = sessions.id),
                           started_at
                       ),
                       durata_ms = COALESCE(
                           (SELECT MAX(t_end_ms) FROM transcript_segments
                             WHERE session_id = sessions.id),
                           0
                       ),
                       stato = CASE WHEN stato = 'recording' THEN 'ready' ELSE stato END
                 WHERE stato = 'recording' OR ended_at IS NULL
                """
            )
        return appese

    def get_session(self, session_id: int) -> sqlite3.Row | None:
        """La riga intera di `sessions`.

        Serve a chi, come la diarizzazione, ha bisogno di campi che le altre
        query mirate non portano — qui `audio_loop_path`, per sapere quale
        file analizzare.
        """
        return self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()

    # ------------------------------------------------------------ trascrizione

    def add_segment(
        self,
        session_id: int,
        source: str,
        t_start_ms: int,
        t_end_ms: int,
        testo: str,
        *,
        is_final: bool = False,
        confidence: float | None = None,
    ) -> int:
        with self.tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO transcript_segments
                  (session_id, source, t_start_ms, t_end_ms, testo, is_final, confidence,
                   speaker_id)
                VALUES (?, ?, ?, ?, ?, ?, ?,
                        (SELECT id FROM speakers
                          WHERE session_id = ? AND ruolo = ?))
                """,
                (
                    session_id,
                    source,
                    t_start_ms,
                    t_end_ms,
                    testo,
                    int(is_final),
                    confidence,
                    session_id,
                    "me" if source == "mic" else "them",
                ),
            )
            return int(cur.lastrowid)

    def refine_segment(
        self,
        segment_id: int,
        testo: str,
        *,
        t_end_ms: int | None = None,
        is_final: bool = True,
        confidence: float | None = None,
    ) -> None:
        """Sostituisce il testo provvisorio con quello rifinito.

        Il record non viene ricreato: le evidence delle task puntano a questo id
        e devono restare valide. Cambia il testo, `revision` cresce.
        """
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE transcript_segments
                   SET testo = ?,
                       t_end_ms = COALESCE(?, t_end_ms),
                       is_final = ?,
                       confidence = COALESCE(?, confidence),
                       revision = revision + 1
                 WHERE id = ?
                """,
                (testo, t_end_ms, int(is_final), confidence, segment_id),
            )

    def elimina_segmento(self, segment_id: int) -> None:
        """Toglie un segmento riconosciuto come eco dell'altoparlante.

        Si cancella invece di correggere l'attribuzione perché quelle parole
        esistono già sull'altra traccia, dette da chi le ha davvero dette:
        tenerle due volte raddoppierebbe la frase nel riassunto.
        """
        with self.tx() as conn:
            conn.execute("DELETE FROM transcript_segments WHERE id = ?", (segment_id,))

    def set_audio_paths(self, session_id: int, mic: str | None, loopback: str | None) -> None:
        with self.tx() as conn:
            conn.execute(
                "UPDATE sessions SET audio_mic_path = ?, audio_loop_path = ? WHERE id = ?",
                (mic, loopback, session_id),
            )

    def segments(self, session_id: int, *, only_final: bool = False) -> list[Segment]:
        # Il LEFT JOIN è per costruzione: finché nessuno ha diarizzato la
        # sessione, speaker_id sui segmenti punta comunque a 'io'/'altri' (lo
        # imposta già add_segment), quindi la voce c'è sempre — solo `nome_reale`
        # resta NULL finché l'utente non ha dato un nome. Un segmento senza
        # speaker_id (non dovrebbe succedere, ma la colonna è nullable) non
        # deve sparire dai risultati: da qui il LEFT invece di un JOIN semplice.
        sql = """
            SELECT t.id, t.session_id, t.source, t.t_start_ms, t.t_end_ms, t.testo,
                   t.is_final, t.revision, t.confidence,
                   sp.id AS speaker_id, sp.label AS speaker_label,
                   sp.nome_reale AS speaker_nome_reale
              FROM transcript_segments t
              LEFT JOIN speakers sp ON sp.id = t.speaker_id
             WHERE t.session_id = ?
        """
        if only_final:
            sql += " AND t.is_final = 1"
        sql += " ORDER BY t.t_start_ms, t.id"
        return [
            Segment(
                id=r["id"],
                session_id=r["session_id"],
                source=r["source"],
                t_start_ms=r["t_start_ms"],
                t_end_ms=r["t_end_ms"],
                testo=r["testo"],
                is_final=bool(r["is_final"]),
                revision=r["revision"],
                confidence=r["confidence"],
                speaker_id=r["speaker_id"],
                speaker_label=r["speaker_label"],
                speaker_nome_reale=r["speaker_nome_reale"],
            )
            for r in self.conn.execute(sql, (session_id,))
        ]

    def search(self, query: str, *, limit: int = 50) -> list[sqlite3.Row]:
        """Ricerca full-text su tutte le call."""
        return list(
            self.conn.execute(
                """
                SELECT s.id, s.session_id, s.t_start_ms, s.source, s.testo,
                       sess.titolo, sess.started_at
                  FROM segments_fts f
                  JOIN transcript_segments s ON s.id = f.rowid
                  JOIN sessions sess ON sess.id = s.session_id
                 WHERE segments_fts MATCH ?
                 ORDER BY rank
                 LIMIT ?
                """,
                (query, limit),
            )
        )

    # -------------------------------------------------------------- screenshot

    def add_screenshot(
        self,
        session_id: int,
        t_ms: int,
        path: str,
        *,
        width: int | None = None,
        height: int | None = None,
        thumb_path: str | None = None,
        nota_utente: str | None = None,
        phash: str | None = None,
    ) -> int:
        with self.tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO screenshots
                  (session_id, t_ms, path, width, height, thumb_path, nota_utente, phash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, t_ms, path, width, height, thumb_path, nota_utente, phash),
            )
            return int(cur.lastrowid)

    def set_screenshot_ocr(self, shot_id: int, testo: str) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE screenshots SET ocr_text = ? WHERE id = ?", (testo, shot_id))

    def screenshots(self, session_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM screenshots WHERE session_id = ? ORDER BY t_ms",
                (session_id,),
            )
        )

    # ---------------------------------------------------------------- output AI

    def add_ai_output(
        self,
        session_id: int,
        kind: str,
        content_md: str,
        *,
        model: str,
        provider: str,
        prompt_id: str,
        prompt_version: str,
        scope_start_ms: int | None = None,
        scope_end_ms: int | None = None,
        content_json: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
    ) -> int:
        """Registra un output, ritirando quello che occupava lo stesso posto.

        Le versioni precedenti restano: servono a confrontare fra loro le
        versioni dei prompt quando se ne cambia uno.
        """
        with self.tx() as conn:
            conn.execute(
                """
                UPDATE ai_outputs SET is_current = 0
                 WHERE session_id = ? AND kind = ?
                   AND IFNULL(scope_start_ms, -1) = IFNULL(?, -1)
                   AND is_current = 1
                """,
                (session_id, kind, scope_start_ms),
            )
            next_version = conn.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS v FROM ai_outputs
                 WHERE session_id = ? AND kind = ?
                   AND IFNULL(scope_start_ms, -1) = IFNULL(?, -1)
                """,
                (session_id, kind, scope_start_ms),
            ).fetchone()["v"]

            cur = conn.execute(
                """
                INSERT INTO ai_outputs
                  (session_id, kind, scope_start_ms, scope_end_ms, content_md, content_json,
                   model, provider, prompt_id, prompt_version, version, is_current,
                   tokens_in, tokens_out, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    session_id,
                    kind,
                    scope_start_ms,
                    scope_end_ms,
                    content_md,
                    content_json,
                    model,
                    provider,
                    prompt_id,
                    prompt_version,
                    next_version,
                    tokens_in,
                    tokens_out,
                    cost_usd,
                ),
            )
            return int(cur.lastrowid)

    # -------------------------------------------------------------------- task

    def add_task(
        self,
        session_id: int,
        titolo: str,
        *,
        descrizione: str | None = None,
        assignee_text: str | None = None,
        due_date: str | None = None,
        due_raw: str | None = None,
        priorita: str | None = None,
        confidence: float | None = None,
        needs_review: bool = True,
        review_reason: str | None = None,
        ai_output_id: int | None = None,
        evidence: list[dict] | None = None,
    ) -> int:
        """Crea una task con le sue prove.

        `evidence` è una lista di dict con almeno `segment_id` e `supports`. Il
        testo della citazione **non** viene preso da chi chiama: si legge dal
        segmento indicato. È la garanzia che una citazione non possa essere
        inventata.
        """
        with self.tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO tasks
                  (session_id, titolo, descrizione, assignee_text, due_date, due_raw,
                   priorita, confidence, needs_review, review_reason, ai_output_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    titolo,
                    descrizione,
                    assignee_text,
                    due_date,
                    due_raw,
                    priorita,
                    confidence,
                    int(needs_review),
                    review_reason,
                    ai_output_id,
                ),
            )
            task_id = int(cur.lastrowid)

            for ev in evidence or []:
                segment_id = ev.get("segment_id")
                screenshot_id = ev.get("screenshot_id")
                t_ms, quote = ev.get("t_ms"), None

                if segment_id is not None:
                    row = conn.execute(
                        "SELECT t_start_ms, testo FROM transcript_segments WHERE id = ?",
                        (segment_id,),
                    ).fetchone()
                    if row is None:
                        # Un riferimento a un segmento inesistente è un'evidence
                        # inventata: si scarta invece di salvarla.
                        continue
                    t_ms, quote = row["t_start_ms"], row["testo"]
                elif screenshot_id is not None:
                    row = conn.execute(
                        "SELECT t_ms FROM screenshots WHERE id = ?", (screenshot_id,)
                    ).fetchone()
                    if row is None:
                        continue
                    t_ms = row["t_ms"]

                if t_ms is None:
                    continue

                conn.execute(
                    """
                    INSERT INTO task_evidence
                      (task_id, segment_id, screenshot_id, t_ms, quote, supports, weight)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        segment_id,
                        screenshot_id,
                        t_ms,
                        quote,
                        ev.get("supports", "esistenza"),
                        ev.get("weight", 1.0),
                    ),
                )
            return task_id

    def task_evidence(self, task_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT e.*, s.testo AS testo_corrente, s.revision
                  FROM task_evidence e
                  LEFT JOIN transcript_segments s ON s.id = e.segment_id
                 WHERE e.task_id = ?
                 ORDER BY e.t_ms
                """,
                (task_id,),
            )
        )

    # ----------------------------------------------------------- esito analisi

    def set_analysis_meta(
        self,
        session_id: int,
        *,
        provider: str | None,
        etichetta_provider: str | None,
        modello: str | None,
        costo_usd: float | None,
        durata_ms: int | None,
        finita_at: int,
    ) -> None:
        """Registra un'analisi riuscita, azzerando l'errore di un tentativo precedente.

        Una nuova analisi finita bene rende irrilevante un eventuale fallimento
        prima di questa: non ha senso continuare a mostrare "ultimo tentativo
        fallito" sopra un risultato buono.
        """
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO analysis_meta
                  (session_id, provider, etichetta_provider, modello, costo_usd,
                   durata_ms, finita_at, errore)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(session_id) DO UPDATE SET
                  provider = excluded.provider,
                  etichetta_provider = excluded.etichetta_provider,
                  modello = excluded.modello,
                  costo_usd = excluded.costo_usd,
                  durata_ms = excluded.durata_ms,
                  finita_at = excluded.finita_at,
                  errore = NULL
                """,
                (session_id, provider, etichetta_provider, modello, costo_usd, durata_ms, finita_at),
            )

    def set_analysis_errore(self, session_id: int, messaggio: str) -> None:
        """Registra un tentativo fallito, senza toccare l'esito dell'ultima analisi riuscita.

        Chi ha già una call analizzata deve continuare a vederne il risultato
        anche se un "Rianalizza" successivo non è andato a segno: si aggiorna
        solo la colonna dell'errore, non tutta la riga.
        """
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO analysis_meta
                  (session_id, provider, etichetta_provider, modello, costo_usd,
                   durata_ms, finita_at, errore)
                VALUES (?, NULL, NULL, NULL, NULL, NULL, NULL, ?)
                ON CONFLICT(session_id) DO UPDATE SET errore = excluded.errore
                """,
                (session_id, messaggio),
            )

    def get_analysis_meta(self, session_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM analysis_meta WHERE session_id = ?", (session_id,)
        ).fetchone()

    # ------------------------------------------------------------------- voci

    def speakers(self, session_id: int) -> list[sqlite3.Row]:
        """I partecipanti conosciuti per questa sessione, 'io'/'altri' compresi.

        Prima di una diarizzazione ce ne sono sempre e solo due, creati da
        `create_session`. Dopo, ce ne possono essere altri con `ruolo='them'`
        e `label` tipo 'Voce 2': è la stessa tabella, la diarizzazione non fa
        altro che aggiungere righe e ripuntare `speaker_id` dei segmenti.
        """
        return list(
            self.conn.execute(
                """
                SELECT id, ruolo, label, nome_reale, confermato
                  FROM speakers
                 WHERE session_id = ?
                 ORDER BY id
                """,
                (session_id,),
            )
        )

    def applica_diarizzazione(
        self, session_id: int, assegnazioni: dict[int, str], *, quando_ms: int
    ) -> dict:
        """Registra l'esito di una diarizzazione: nuove voci e segmenti riassegnati.

        `assegnazioni` è {segment_id: etichetta_cluster}, con l'etichetta così
        com'è uscita dal modello (es. "SPEAKER_00"). La corrispondenza fra
        quell'etichetta e "Voce 2", "Voce 3"... si decide qui, non nel
        modello: se una versione futura del modello rinumerasse i cluster
        diversamente, il contratto con chi chiama ("Voce 2" è la prima voce
        per ordine di comparsa) non cambierebbe. "Voce 1" non esiste: sarebbe
        concettualmente 'io', che non passa da qui — vedi il modulo
        `stt/diarizzazione.py` per il perché si diarizza solo il loopback.

        Ogni segment_id viene controllato contro questa sessione e contro la
        traccia: uno fuori posto (di un'altra sessione, o sul microfono) viene
        scartato invece di far fallire l'intera chiamata. Il microfono è per
        costruzione una persona sola, e la garanzia che non gli si possa mai
        assegnare una voce fra le altre non deve dipendere dal fatto che chi
        chiama si sia comportato bene.

        Va bene anche con `assegnazioni` vuoto: la diarizzazione è stata
        comunque eseguita (magari la call non aveva nessun altro sul
        loopback), e `quando_ms` deve registrarlo lo stesso — è quello che
        distingue "mai diarizzata" da "diarizzata, niente da aggiungere" per
        chi decide se mostrare `speaker` nei segmenti (vedi
        `_migra_colonna_diarizzata_at`).
        """
        with self.tx() as conn:
            righe = conn.execute(
                "SELECT id, source, t_start_ms FROM transcript_segments WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            inizio_per_id_loopback = {
                r["id"]: r["t_start_ms"] for r in righe if r["source"] == "loopback"
            }

            # Solo segmenti loopback di questa sessione, ordinati nel tempo:
            # l'ordine decide quale cluster diventa "Voce 2" e quale "Voce 3".
            validi = sorted(
                (
                    (inizio_per_id_loopback[sid], sid, etichetta)
                    for sid, etichetta in assegnazioni.items()
                    if sid in inizio_per_id_loopback
                ),
                key=lambda v: v[0],
            )

            ordine_cluster: list[str] = []
            for _, _, etichetta in validi:
                if etichetta not in ordine_cluster:
                    ordine_cluster.append(etichetta)

            # Si riparte dopo l'ultima "Voce N" già presente, così rilanciare
            # la diarizzazione (un altro tentativo, un audio più lungo…) crea
            # voci nuove invece di andare a sbattere sull'UNIQUE(session_id,
            # label). Fondere le nuove voci con quelle di un run precedente
            # richiederebbe cluster stabili fra un'esecuzione e l'altra del
            # modello, cosa che pyannote non garantisce: unire a mano in
            # revisione resta più affidabile che indovinare qui.
            riga_max = conn.execute(
                """
                SELECT MAX(CAST(SUBSTR(label, 6) AS INTEGER)) AS n
                  FROM speakers
                 WHERE session_id = ? AND ruolo = 'them' AND label LIKE 'Voce %'
                """,
                (session_id,),
            ).fetchone()
            prossimo_numero = (riga_max["n"] or 1) + 1

            id_speaker_per_cluster: dict[str, int] = {}
            for etichetta in ordine_cluster:
                cur = conn.execute(
                    "INSERT INTO speakers (session_id, ruolo, label) VALUES (?, 'them', ?)",
                    (session_id, f"Voce {prossimo_numero}"),
                )
                id_speaker_per_cluster[etichetta] = int(cur.lastrowid)
                prossimo_numero += 1

            for _, sid, etichetta in validi:
                conn.execute(
                    "UPDATE transcript_segments SET speaker_id = ? WHERE id = ?",
                    (id_speaker_per_cluster[etichetta], sid),
                )

            conn.execute(
                "UPDATE sessions SET diarizzata_at = ? WHERE id = ?", (quando_ms, session_id)
            )

            return {"voci": len(id_speaker_per_cluster), "segmenti_assegnati": len(validi)}

    def rinomina_voce(self, speaker_id: int, nome_reale: str) -> bool:
        """Dà un nome a una voce. Vero se la voce esiste, falso altrimenti.

        Senza questo, "Voce 2" resta per sempre: è la sola strada che rende
        confermabile un'etichetta uscita da un modello probabilistico.
        `confermato` passa a vero insieme al nome — è quello che distingue,
        in interfaccia, una voce con un nome dato dall'utente da una ancora
        anonima.
        """
        with self.tx() as conn:
            cur = conn.execute(
                "UPDATE speakers SET nome_reale = ?, confermato = 1 WHERE id = ?",
                (nome_reale, speaker_id),
            )
            return cur.rowcount > 0

    # --------------------------------------------------------- cancellazioni

    def elimina_sessione(self, session_id: int) -> dict[str, list[str]] | None:
        """Toglie una call per intero: audio, trascrizione, screenshot, task.

        Le tabelle a valle sono in CASCADE (transcript_segments, screenshots,
        tasks, task_evidence, ai_outputs, analysis_meta): basta cancellare la
        riga di sessions. I file sul disco, però, un DELETE non li tocca — si
        raccolgono i percorsi prima di cancellare la riga, così chi chiama può
        toglierli lui.
        """
        with self.tx() as conn:
            riga = conn.execute(
                "SELECT audio_mic_path, audio_loop_path FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if riga is None:
                return None
            audio = [p for p in (riga["audio_mic_path"], riga["audio_loop_path"]) if p]
            screenshot = [
                p
                for r in conn.execute(
                    "SELECT path, thumb_path FROM screenshots WHERE session_id = ?",
                    (session_id,),
                )
                for p in (r["path"], r["thumb_path"])
                if p
            ]
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return {"audio": audio, "screenshots": screenshot}

    def azzera_percorsi_audio(self) -> list[str]:
        """Toglie i riferimenti audio da tutte le sessioni, tenendo il resto.

        Le task e le loro prove restano intatte: puntano a segmenti di
        trascrizione, non a file audio. Restituisce i percorsi che c'erano,
        perché toglierli dal disco spetta a chi chiama, non allo store.
        """
        with self.tx() as conn:
            percorsi = [
                p
                for r in conn.execute(
                    "SELECT audio_mic_path, audio_loop_path FROM sessions "
                    "WHERE audio_mic_path IS NOT NULL OR audio_loop_path IS NOT NULL"
                )
                for p in (r["audio_mic_path"], r["audio_loop_path"])
                if p
            ]
            conn.execute("UPDATE sessions SET audio_mic_path = NULL, audio_loop_path = NULL")
            return percorsi
