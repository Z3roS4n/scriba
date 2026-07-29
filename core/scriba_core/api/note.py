"""Le note incrementali già prese di una sessione.

Sul modello di `api/modelli.py`: la rotta è sottile, legge e basta. Chi scrive
le note è `GestoreNote` (`ai/note_correnti.py`), che gira nel thread della
registrazione e non sa nulla di HTTP — qui si espone solo cosa c'è già nel
database quando qualcuno lo chiede.
"""

from __future__ import annotations

import json

from fastapi import APIRouter

from . import Contesto


def crea_router(ctx: Contesto) -> APIRouter:
    router = APIRouter(tags=["note"])

    @router.get("/sessions/{session_id}/note")
    async def note(session_id: int) -> dict:
        # Ogni nota incrementale occupa la propria finestra
        # (scope_start_ms/scope_end_ms) ed è "corrente" insieme a tutte le
        # altre della stessa call: non si sovrascrivono a vicenda, si
        # accumulano in ordine cronologico. Vedi GestoreNote._genera_nota.
        righe = ctx.store.conn.execute(
            """
            SELECT scope_start_ms, scope_end_ms, content_md, content_json, created_at
              FROM ai_outputs
             WHERE session_id = ? AND kind = 'running_note' AND is_current = 1
             ORDER BY scope_end_ms
            """,
            (session_id,),
        ).fetchall()

        note_out = []
        for r in righe:
            # I candidati sono un valore aggiunto opportunistico: una nota
            # senza (content_json NULL, o un giro in cui l'estrazione è
            # fallita) resta comunque una nota valida da mostrare.
            try:
                candidati = json.loads(r["content_json"]) if r["content_json"] else []
            except (json.JSONDecodeError, TypeError):
                candidati = []
            note_out.append(
                {
                    "t_inizio_ms": r["scope_start_ms"],
                    "t_ms": r["scope_end_ms"],
                    "testo": r["content_md"],
                    "candidati_task": len(candidati),
                    "creata_at": r["created_at"],
                }
            )

        return {"note": note_out}

    return router
