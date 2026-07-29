"""Rotte per la diarizzazione: avvio a fine call, e dare un nome a una voce.

Segue lo stesso schema delle altre rotte lunghe di questo server (vedi
`_avvia_analisi_task` in `server.py`): si risponde subito e si lavora dopo in
un task, perché una diarizzazione su un'ora di audio può durare decine di
minuti (vedi la stima in `stt/diarizzazione.py`) e tenere aperta una richiesta
HTTP per tutto quel tempo non funziona — il client la chiude molto prima.
L'avanzamento e l'esito arrivano via websocket con `ctx.publish`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import Contesto
from ..stt.diarizzazione import DiarizzazioneNonDisponibile, Diarizzatore

log = logging.getLogger(__name__)


class _RinominaVoce(BaseModel):
    nome_reale: str


def crea_router(ctx: Contesto) -> APIRouter:
    router = APIRouter(tags=["diarizzazione"])
    # Un'unica istanza per processo, come `ModelsManager` in modelli.py: tiene
    # in cache la pipeline caricata (i pesi sono centinaia di MB, ricaricarli
    # a ogni chiamata sarebbe l'unico modo sicuro di rendere la funzione
    # ancora più lenta di quanto già è).
    diarizzatore = Diarizzatore()

    @router.get("/diarizzazione/disponibile")
    async def disponibile() -> dict:
        return {"disponibile": await asyncio.to_thread(diarizzatore.disponibile)}

    @router.post("/sessions/{session_id}/diarizzazione")
    async def avvia(session_id: int) -> dict:
        if ctx.state.get("diarizzazione_in_corso"):
            raise HTTPException(
                status_code=409,
                detail="c'è già una diarizzazione in corso (su un'altra sessione, se non "
                "su questa): il modello resta in memoria un'esecuzione alla volta.",
            )
        if await asyncio.to_thread(ctx.store.get_session, session_id) is None:
            raise HTTPException(status_code=404, detail="sessione inesistente")

        if not await asyncio.to_thread(diarizzatore.disponibile):
            raise HTTPException(
                status_code=409,
                detail="diarizzazione non disponibile: manca pyannote.audio/torch, o "
                "un token Hugging Face che abbia accettato le condizioni del modello.",
            )

        ctx.state["diarizzazione_in_corso"] = True
        ctx.state["diarizzazione_session_id"] = session_id

        def on_avanzamento(frazione: float, nota: str) -> None:
            # Gira nel thread di lavoro (vedi `asyncio.to_thread` sotto):
            # `ctx.publish` è dichiarato chiamabile da qualunque thread.
            ctx.publish(
                {
                    "type": "diarizzazione",
                    "stato": "in_corso",
                    "session_id": session_id,
                    "frazione": frazione,
                    "nota": nota,
                }
            )

        async def lavora() -> None:
            try:
                esito = await asyncio.to_thread(
                    diarizzatore.assegna, session_id, ctx.store, avanzamento=on_avanzamento
                )
            except DiarizzazioneNonDisponibile as exc:
                ctx.publish(
                    {
                        "type": "diarizzazione",
                        "stato": "errore",
                        "session_id": session_id,
                        "dettaglio": str(exc),
                    }
                )
            except Exception as exc:  # pragma: no cover - paracadute, come per l'analisi
                log.exception("Diarizzazione della sessione %s non riuscita", session_id)
                ctx.publish(
                    {
                        "type": "diarizzazione",
                        "stato": "errore",
                        "session_id": session_id,
                        "dettaglio": str(exc),
                    }
                )
            else:
                ctx.publish(
                    {
                        "type": "diarizzazione",
                        "stato": "fatto",
                        "session_id": session_id,
                        "voci": esito["voci"],
                        "segmenti_assegnati": esito["segmenti_assegnati"],
                    }
                )
            finally:
                ctx.state["diarizzazione_in_corso"] = False
                ctx.state["diarizzazione_session_id"] = None

        ctx.publish({"type": "diarizzazione", "stato": "in_corso", "session_id": session_id,
                     "frazione": 0.0, "nota": "avviata"})
        asyncio.create_task(lavora())
        return {"session_id": session_id, "stato": "avviata"}

    @router.get("/sessions/{session_id}/voci")
    async def voci(session_id: int) -> list[dict[str, Any]]:
        if ctx.store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="sessione inesistente")
        righe = await asyncio.to_thread(ctx.store.speakers, session_id)
        return [
            {
                "id": r["id"],
                "ruolo": r["ruolo"],
                "label": r["label"],
                "nome_reale": r["nome_reale"],
                "confermato": bool(r["confermato"]),
            }
            for r in righe
        ]

    @router.patch("/sessions/{session_id}/voci/{speaker_id}")
    async def rinomina(session_id: int, speaker_id: int, req: _RinominaVoce) -> dict:
        nome = req.nome_reale.strip()
        if not nome:
            raise HTTPException(status_code=400, detail="il nome non può essere vuoto")

        trovata = await asyncio.to_thread(ctx.store.rinomina_voce, speaker_id, nome)
        if not trovata:
            raise HTTPException(status_code=404, detail="voce inesistente")

        ctx.publish(
            {
                "type": "diarizzazione",
                "stato": "voce_rinominata",
                "session_id": session_id,
                "speaker_id": speaker_id,
                "nome_reale": nome,
            }
        )
        return {"id": speaker_id, "nome_reale": nome, "confermato": True}

    return router
