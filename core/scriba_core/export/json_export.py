"""Esporta una call in JSON: la stessa cosa del Markdown, senza la prosa.

È il formato che rende il lavoro riutilizzabile fuori da Scriba, quindi non si
scarta niente: sessione, segmenti, screenshot, riassunto, punti salienti e le
task **con le prove per campo** — lo stesso dettaglio che rende una task
verificabile nel Markdown, qui in una forma che un programma può leggere senza
doverla prima interpretare.

`riassunto_md`/`punti_salienti_md` restano nella forma con cui il modello li
scrive (Markdown), non spezzati in gruppi/punti strutturati: quella
suddivisione è logica di presentazione che oggi vive nel server (che un altro
agente sta riscrivendo in parallelo), e duplicarla qui rischierebbe di
disallinearsi da quella vera. Chi consuma questo JSON e vuole i gruppi può
fare lo split sulle stesse convenzioni («## Titolo», «[mm:ss] **Etichetta**
— corpo») che il testo già rispetta.

`costruisci_payload` è pubblica apposta: la usano anche i connettori (Notion,
HTTP generico) così il contenuto che arriva a un sistema esterno è
esattamente lo stesso di questo file, e i due percorsi non possono divergere
su cosa significa "tutto".
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..db.store import Store
from ._util import nome_file


def _task_a_dict(store: Store, t: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": t["id"],
        "titolo": t["titolo"],
        "descrizione": t["descrizione"],
        "assignee_text": t["assignee_text"],
        "due_date": t["due_date"],
        "due_raw": t["due_raw"],
        "priorita": t["priorita"],
        "stato": t["stato"],
        "confidence": t["confidence"],
        "needs_review": bool(t["needs_review"]),
        "review_reason": t["review_reason"],
        # Una prova per campo, non per task: è il punto centrale del progetto.
        "evidence": [
            {
                "supports": e["supports"],
                "t_ms": e["t_ms"],
                "quote": e["quote"],
                "segment_id": e["segment_id"],
                "screenshot_id": e["screenshot_id"],
            }
            for e in store.task_evidence(t["id"])
        ],
    }


def costruisci_payload(store: Store, session_id: int) -> dict[str, Any]:
    """Tutto quello che Scriba sa su una call, in un dict pronto per `json.dumps`."""
    sessione = store.conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if sessione is None:
        raise ValueError(f"Sessione {session_id} inesistente.")

    correnti = {
        r["kind"]: r["content_md"]
        for r in store.conn.execute(
            """
            SELECT kind, content_md FROM ai_outputs
             WHERE session_id = ? AND is_current = 1 AND scope_start_ms IS NULL
            """,
            (session_id,),
        )
    }

    tasks = list(
        store.conn.execute(
            """
            SELECT * FROM tasks
             WHERE session_id = ? AND stato <> 'rejected'
             ORDER BY CASE stato WHEN 'confirmed' THEN 0 WHEN 'done' THEN 1 ELSE 2 END,
                      IFNULL(due_date, '9999'), id
            """,
            (session_id,),
        )
    )

    return {
        "sessione": {
            "id": sessione["id"],
            "titolo": sessione["titolo"],
            "piattaforma": sessione["piattaforma"],
            "started_at": sessione["started_at"],
            "ended_at": sessione["ended_at"],
            "durata_ms": sessione["durata_ms"],
            "lingua": sessione["lingua"],
            "stato": sessione["stato"],
            "consenso_confermato_at": sessione["consenso_confermato_at"],
        },
        "segmenti": [
            {
                "id": s.id,
                "source": s.source,
                "t_start_ms": s.t_start_ms,
                "t_end_ms": s.t_end_ms,
                "testo": s.testo,
                "is_final": s.is_final,
                "revision": s.revision,
                "confidence": s.confidence,
            }
            for s in store.segments(session_id, only_final=True)
        ],
        "screenshot": [
            {
                "id": s["id"],
                "t_ms": s["t_ms"],
                "path": s["path"],
                "width": s["width"],
                "height": s["height"],
                "nota_utente": s["nota_utente"],
                "ocr_text": s["ocr_text"],
            }
            for s in store.screenshots(session_id)
        ],
        "riassunto_md": correnti.get("summary"),
        "punti_salienti_md": correnti.get("highlights"),
        "task": [_task_a_dict(store, t) for t in tasks],
    }


def esporta(store: Store, session_id: int, destinazione: Path | str) -> Path:
    """Scrive il file e restituisce il percorso."""
    payload = costruisci_payload(store, session_id)
    sessione = payload["sessione"]
    quando = datetime.fromtimestamp(sessione["started_at"] / 1000)

    destinazione = Path(destinazione)
    if destinazione.suffix.lower() != ".json":
        destinazione.mkdir(parents=True, exist_ok=True)
        destinazione = destinazione / nome_file(sessione["titolo"], quando, session_id, "json")
    destinazione.parent.mkdir(parents=True, exist_ok=True)

    destinazione.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return destinazione
