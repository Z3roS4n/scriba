"""Ripassare la trascrizione di una call, a registrazione finita.

Le rotte sono sottili: il lavoro vero — allineamento dell'audio, controllo a
campione, riscrittura riga per riga — sta in `stt/rifinitura.py`. Qui ci sono
il ciclo di vita (una alla volta, interrompibile), gli eventi verso
l'interfaccia e il caricamento del modello, che costa secondi e va fatto una
volta sola per processo.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from fastapi import APIRouter, HTTPException

from . import Contesto
from ..models_manager import modello_gestito_installato
from ..stt import glossario, rifinitura

log = logging.getLogger(__name__)

MODELLO = "canary-1b-v2"


def crea_router(ctx: Contesto) -> APIRouter:
    router = APIRouter(tags=["rifinitura"])
    ctx.state.setdefault("rifinitura", _stato_fermo())
    # Il modello resta caricato fra una rifinitura e l'altra: costa secondi ad
    # aprirlo, e chi ne rifinisce due di fila non deve pagarli due volte.
    ctx.state.setdefault("motore_rifinitura", None)

    def _carica_motore():
        if ctx.state.get("motore_rifinitura") is None:
            from ..stt.canary import CanaryEngine

            ctx.state["motore_rifinitura"] = CanaryEngine(quantization="int8")
        return ctx.state["motore_rifinitura"]

    def _termini() -> tuple[list[str], str]:
        """Il glossario com'è adesso: dopo aver ritrascritto va riapplicato.

        Senza, la rifinitura riporterebbe indietro i nomi propri che la
        trascrizione dal vivo aveva già rimesso a posto.
        """
        conf = ctx.settings.tutto().get("stt", {})
        termini = [str(t) for t in conf.get("glossario") or []]
        if conf.get("glossario_clienti", True):
            try:
                termini += [r["nome"] for r in ctx.store.clienti()]
            except Exception:  # pragma: no cover - anagrafica non leggibile
                log.warning("Anagrafica clienti non leggibile durante la rifinitura.")
        livello = str(conf.get("glossario_livello") or glossario.LIVELLO_PREDEFINITO)
        return termini, livello

    def avvia(session_id: int) -> dict[str, Any]:
        """Fa partire la passata. Chi chiama ha già verificato che si possa."""
        annulla = threading.Event()
        ctx.state["rifinitura"] = {
            "in_corso": True,
            "session_id": session_id,
            "fatte": 0,
            "totale": 0,
            "traccia": None,
            "annulla": annulla,
            "esito": None,
            "errore": None,
        }

        def _progresso(fatte: int, totale: int, traccia: str) -> None:
            s = ctx.state["rifinitura"]
            s["fatte"], s["totale"], s["traccia"] = fatte, totale, traccia
            # Non a ogni riga: su una call lunga sono centinaia di eventi che
            # dicono la stessa cosa. Ogni dieci basta a far muovere una barra.
            if fatte % 10 == 0 or fatte == totale:
                ctx.publish(
                    {
                        "type": "rifinitura",
                        "stato": "in_corso",
                        "session_id": session_id,
                        "fatte": fatte,
                        "totale": totale,
                        "traccia": traccia,
                    }
                )

        async def lavora() -> None:
            try:
                termini, livello = _termini()
                lingua = str(ctx.settings.tutto().get("stt", {}).get("lingua") or "it")
                motore = await asyncio.to_thread(_carica_motore)
                esito = await asyncio.to_thread(
                    lambda: rifinitura.rifinisci(
                        ctx.store,
                        session_id,
                        motore,
                        lingua=lingua,
                        termini=termini,
                        livello_glossario=livello,
                        on_progresso=_progresso,
                        annulla=annulla,
                    )
                )
            except rifinitura.Interrotta:
                ctx.state["rifinitura"] = _stato_fermo()
                ctx.publish(
                    {"type": "rifinitura", "stato": "interrotta", "session_id": session_id}
                )
                return
            except Exception as exc:
                log.exception("Rifinitura non riuscita per la sessione %s", session_id)
                fermo = _stato_fermo()
                fermo["errore"] = str(exc)
                fermo["session_id"] = session_id
                ctx.state["rifinitura"] = fermo
                ctx.publish(
                    {
                        "type": "rifinitura",
                        "stato": "errore",
                        "session_id": session_id,
                        "dettaglio": str(exc),
                    }
                )
                return

            fermo = _stato_fermo()
            fermo["session_id"] = session_id
            fermo["esito"] = _serializza(esito)
            ctx.state["rifinitura"] = fermo
            ctx.publish(
                {
                    "type": "rifinitura",
                    "stato": "finita",
                    "session_id": session_id,
                    "esito": fermo["esito"],
                }
            )

        # Il task resta a disposizione: la passata automatica di fine
        # registrazione deve poterla **aspettare**, perché l'analisi legge la
        # trascrizione e deve leggere quella rifinita, non quella di prima.
        ctx.state["rifinitura_task"] = asyncio.get_running_loop().create_task(lavora())
        return {"session_id": session_id, "stato": "avviata"}

    # Serve a `server.py` per la passata automatica a fine registrazione: la
    # logica sta tutta qui, e il chiamante non deve rifarsene una sua.
    ctx.state["avvia_rifinitura"] = avvia

    # ------------------------------------------------------------------ rotte

    @router.post("/sessions/{session_id}/rifinisci")
    async def rifinisci(session_id: int) -> dict[str, Any]:
        corrente = ctx.state.get("rifinitura") or {}
        if corrente.get("in_corso"):
            # Se sta già girando proprio su questa call, la richiesta è
            # soddisfatta: si risponde di sì invece di mostrare un errore per
            # una cosa che sta succedendo.
            if corrente.get("session_id") == session_id:
                return {"session_id": session_id, "stato": "già_avviata"}
            raise HTTPException(status_code=409, detail="una rifinitura è già in corso")

        if ctx.store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="sessione inesistente")
        if not ctx.store.segments(session_id, only_final=True):
            raise HTTPException(
                status_code=412, detail="Questa call non ha una trascrizione da rifinire."
            )
        if not modello_gestito_installato(MODELLO):
            raise HTTPException(
                status_code=412,
                detail="Il modello della rifinitura non è ancora scaricato. "
                "Impostazioni → Modelli locali → Canary 1B v2 (circa 1 GB).",
            )
        return avvia(session_id)

    @router.get("/rifinitura/stato")
    async def stato() -> dict[str, Any]:
        """Dove sta la rifinitura adesso.

        Come `/analisi/stato`: un'interfaccia che si fida solo degli eventi
        resta ferma per sempre quando ne perde uno.
        """
        s = dict(ctx.state.get("rifinitura") or _stato_fermo())
        s.pop("annulla", None)
        s["modello_pronto"] = modello_gestito_installato(MODELLO)
        return s

    @router.post("/rifinitura/interrompi")
    async def interrompi() -> dict[str, Any]:
        s = ctx.state.get("rifinitura") or {}
        annulla = s.get("annulla")
        if not s.get("in_corso") or annulla is None:
            return {"stato": "ferma"}
        annulla.set()
        return {"stato": "interruzione_richiesta"}

    return router


def _stato_fermo() -> dict[str, Any]:
    return {
        "in_corso": False,
        "session_id": None,
        "fatte": 0,
        "totale": 0,
        "traccia": None,
        "annulla": None,
        "esito": None,
        "errore": None,
    }


def _serializza(esito: rifinitura.Esito) -> dict[str, Any]:
    return {
        "riscritte": esito.riscritte,
        "nomi_corretti": esito.nomi_corretti,
        "tracce": {
            nome: {
                "stato": t.stato,
                "esaminate": t.esaminate,
                "riscritte": t.riscritte,
                "somiglianza": t.somiglianza,
                "motivo": t.motivo,
            }
            for nome, t in esito.tracce.items()
        },
    }
