"""Accesso al database di Scriba.

Il punto delicato di questo modulo è che durante una call ci sono due scrittori
(la trascrizione del microfono e quella dell'audio di sistema) e almeno un
lettore (la UI che mostra il testo mentre si parla). Da qui il WAL e le
connessioni per-thread: SQLite non condivide una connessione fra thread, e
provarci dà errori che compaiono solo sotto carico.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1


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

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # -------------------------------------------------------------- migrazioni

    def _migrate(self) -> None:
        conn = self.conn
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        if row is None or row["v"] is None:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))

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
        sql = """
            SELECT id, session_id, source, t_start_ms, t_end_ms, testo, is_final,
                   revision, confidence
              FROM transcript_segments
             WHERE session_id = ?
        """
        if only_final:
            sql += " AND is_final = 1"
        sql += " ORDER BY t_start_ms, id"
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
