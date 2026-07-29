"""Dispositivi audio, spazio occupato, cancellazioni.

Tre famiglie di rotte, tenute insieme perché condividono lo stesso tratto: qui
si tocca il disco e l'hardware, non solo il database. Le cancellazioni in
particolare sono irreversibili — i file spariscono davvero — quindi ogni rotta
fa **esattamente** quello che promette, né di più né di meno: chi chiama
`/dati/elimina-audio` deve poter continuare a rileggere le sue task subito
dopo, e chi chiama `/sessions/{id}/elimina` deve trovare la call sparita per
intero.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from . import Contesto
from ..audio import devices as audio_devices

log = logging.getLogger(__name__)


def _in_registrazione_su(ctx: Contesto, session_id: int) -> bool:
    """Vero se il recorder sta scrivendo proprio su questa sessione.

    Serve a distinguere "c'è una registrazione in corso" da "c'è una
    registrazione in corso *su questa call*": eliminare una call diversa da
    quella che si sta registrando è sicuro, la propria no.
    """
    recorder = ctx.state.get("recorder")
    return bool(
        recorder is not None and recorder.is_recording and recorder.session_id == session_id
    )


def _dimensione_cartella(cartella: Path) -> int:
    """Byte totali sotto una cartella, 0 se non esiste.

    Ricorsiva perché audio e screenshot vivono in sottocartelle per sessione:
    fermarsi al primo livello sottostimerebbe lo spazio occupato per davvero.
    """
    if not cartella.exists():
        return 0
    return sum(f.stat().st_size for f in cartella.rglob("*") if f.is_file())


def _elimina_file(percorsi: list[str]) -> None:
    """Toglie dal disco i file indicati, senza fermarsi al primo assente.

    Chiamata sempre dopo che il database è già stato aggiornato: a quel punto
    il riferimento non esiste più, e un file già sparito (o mai scritto, come
    una traccia rimasta vuota) non è un errore da segnalare.
    """
    for p in percorsi:
        with contextlib.suppress(OSError):
            Path(p).unlink()


def crea_router(ctx: Contesto) -> APIRouter:
    router = APIRouter(tags=["sistema"])

    # ------------------------------------------------------------ screenshot

    @router.get("/sessions/{session_id}/screenshots")
    async def screenshots(session_id: int) -> list[dict]:
        righe = await asyncio.to_thread(ctx.store.screenshots, session_id)
        return [
            {
                "id": r["id"],
                "t_ms": r["t_ms"],
                "path": r["path"],
                "width": r["width"],
                "height": r["height"],
                "nota_utente": r["nota_utente"],
            }
            for r in righe
        ]

    # ---------------------------------------------------------------- analisi

    @router.post("/sessions/{session_id}/analyze/stop")
    async def analyze_stop(session_id: int) -> dict:
        """Interrompe l'analisi in corso su questa sessione.

        `analisi_annulla` è l'`Event` che il callback di avanzamento controlla
        fra una fase e l'altra (vedi `server.py`): impostarlo fa fermare il
        lavoro in un thread separato, ma quel controllo avviene solo ai
        confini di fase e può volerci tempo. L'interfaccia non deve aspettare:
        si riporta subito lo stato a fermo e si pubblica l'evento, così chi
        guarda smette di vedere le fasi in corso adesso, non quando il thread
        se ne accorge.
        """
        if (
            not ctx.state.get("analisi_in_corso")
            or ctx.state.get("analisi_session_id") != session_id
        ):
            raise HTTPException(
                status_code=409, detail="nessuna analisi in corso per questa sessione"
            )

        annulla = ctx.state.get("analisi_annulla")
        if annulla is not None:
            annulla.set()

        messaggio = "Interrotta dall'utente."

        def _registra_interruzione() -> None:
            ctx.store.set_session_state(session_id, "error")
            ctx.store.set_analysis_errore(session_id, messaggio)

        await asyncio.to_thread(_registra_interruzione)

        ctx.state["analisi_in_corso"] = False
        ctx.state["analisi_session_id"] = None
        ctx.state["analisi_fasi"] = []
        ctx.state["analisi_annulla"] = None

        ctx.publish(
            {
                "type": "analisi",
                "stato": "errore",
                "session_id": session_id,
                "dettaglio": messaggio,
            }
        )
        return {"session_id": session_id, "stato": "interrotta"}

    # ------------------------------------------------------------ cancellazioni

    @router.post("/sessions/{session_id}/elimina")
    async def elimina_sessione(session_id: int) -> dict:
        if _in_registrazione_su(ctx, session_id):
            # Il recorder ha ancora il file aperto: cancellarlo adesso
            # lascerebbe scrivere su un percorso che non esiste più, e la riga
            # `sessions` sparirebbe sotto una registrazione che la referenzia
            # ancora (transcript_segments è in CASCADE).
            raise HTTPException(
                status_code=409,
                detail="la sessione è in registrazione: fermala prima di eliminarla",
            )

        percorsi = await asyncio.to_thread(ctx.store.elimina_sessione, session_id)
        if percorsi is None:
            raise HTTPException(status_code=404, detail="sessione inesistente")

        await asyncio.to_thread(_elimina_file, [*percorsi["audio"], *percorsi["screenshots"]])
        return {"session_id": session_id, "eliminata": True}

    @router.post("/dati/elimina-audio")
    async def elimina_audio() -> dict:
        # Solo i percorsi audio: trascrizioni, task e prove restano — è quello
        # che questa rotta promette, a differenza di `/sessions/{id}/elimina`.
        # Una sessione in registrazione non ha ancora un percorso audio in
        # database (`set_audio_paths` viene chiamato solo da `Recorder.stop`),
        # quindi non c'è bisogno di escluderla esplicitamente: il suo file
        # aperto non compare fra quelli da cancellare.
        percorsi = await asyncio.to_thread(ctx.store.azzera_percorsi_audio)
        await asyncio.to_thread(_elimina_file, percorsi)
        return {"eliminati": len(percorsi)}

    # ------------------------------------------------------------- dispositivi

    @router.get("/dispositivi")
    async def dispositivi() -> dict:
        try:
            return await asyncio.to_thread(audio_devices.elenco)
        except Exception:
            # `audio_devices.elenco` intercetta già i propri errori per
            # dispositivo: questo è un ulteriore paracadute. Con l'audio rotto
            # l'utente deve poter aprire le impostazioni proprio per capire
            # cosa non va, non restare bloccato da un 500.
            log.exception("Enumerazione dispositivi audio non riuscita")
            return {"microfoni": [], "loopback": []}

    # -------------------------------------------------------------- spazio

    @router.get("/dati")
    async def dati() -> list[dict]:
        cartella_audio = ctx.db_path.parent / "audio"
        cartella_screenshot = ctx.db_path.parent / "screenshots"

        def calcola() -> list[dict]:
            return [
                {
                    "chiave": "audio",
                    "etichetta": "Audio delle registrazioni",
                    "path": str(cartella_audio),
                    "bytes": _dimensione_cartella(cartella_audio),
                },
                {
                    "chiave": "db",
                    "etichetta": "Database",
                    "path": str(ctx.db_path),
                    "bytes": ctx.db_path.stat().st_size if ctx.db_path.exists() else 0,
                },
                {
                    "chiave": "screenshots",
                    "etichetta": "Schermate",
                    "path": str(cartella_screenshot),
                    "bytes": _dimensione_cartella(cartella_screenshot),
                },
            ]

        return await asyncio.to_thread(calcola)

    return router
