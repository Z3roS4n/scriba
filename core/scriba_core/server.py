"""Server locale del core.

L'interfaccia grafica è un processo separato e parla con il core da qui. Due
scelte per non esporre le call di lavoro a qualunque programma in esecuzione
sulla macchina:

- si ascolta **solo** su 127.0.0.1 e su una **porta effimera**, decisa dal
  sistema all'avvio, quindi non indovinabile;
- ogni richiesta porta un **token** generato all'avvio e comunicato al processo
  padre sullo standard output.

Un server su porta fissa senza token sarebbe raggiungibile da qualsiasi pagina
web aperta nel browser.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import threading
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .db.store import Store
from .recorder import Recorder
from .stt.base import TranscriptEvent


class StartRequest(BaseModel):
    titolo: str | None = None
    piattaforma: str | None = None
    lingua: str = "it"
    # L'utente ha confermato di aver avvisato i partecipanti. Non è un
    # tecnicismo: senza, la sessione resta marcata come non confermata.
    consenso_confermato: bool = False


class ScreenshotRequest(BaseModel):
    path: str
    nota_utente: str | None = None
    width: int | None = None
    height: int | None = None


class Broadcaster:
    """Recapita gli eventi ai client collegati.

    Gli eventi nascono nei thread di trascrizione, che non sono asincroni: il
    passaggio al loop asyncio va fatto in modo esplicito, altrimenti si
    corrompe lo stato interno del loop in modi che si manifestano molto dopo.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        with self._lock:
            self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        with self._lock:
            self._clients.discard(ws)

    def publish(self, message: dict[str, Any]) -> None:
        """Chiamabile da qualunque thread."""
        if self._loop is None:
            return
        with suppress(RuntimeError):  # loop già chiuso durante lo spegnimento
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._fanout(message))
            )

    async def _fanout(self, message: dict[str, Any]) -> None:
        with self._lock:
            clients = list(self._clients)
        payload = json.dumps(message, ensure_ascii=False)
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                # Un client che se n'è andato non deve impedire agli altri di
                # ricevere: si rimuove e si prosegue.
                self.disconnect(ws)


def _lifespan(broadcaster: Broadcaster, state: dict[str, Any]):
    """Aggancia il broadcaster al loop e chiude ciò che resta aperto."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        broadcaster.bind_loop(asyncio.get_running_loop())
        try:
            yield
        finally:
            recorder = state.get("recorder")
            if recorder is not None and recorder.is_recording:
                # Meglio una sessione chiusa male che una registrazione orfana
                # che tiene occupato il microfono finché non si riavvia il PC.
                recorder.stop()

    return lifespan


def create_app(
    *,
    db_path: Path,
    token: str,
    engine_factory=None,
    recorder_factory=None,
) -> FastAPI:
    """Costruisce l'applicazione.

    Le due factory sono iniettabili perché caricare il modello vero costa
    secondi e aprire i device audio veri legherebbe i test all'hardware.
    """
    app = FastAPI(title="Scriba core", docs_url=None, redoc_url=None)
    broadcaster = Broadcaster()
    store = Store(db_path)

    state: dict[str, Any] = {"engine": None, "recorder": None}

    def get_engine():
        if state["engine"] is None:
            if engine_factory is not None:
                state["engine"] = engine_factory()
            else:
                from .stt.parakeet import ParakeetEngine

                state["engine"] = ParakeetEngine(quantization="int8")
        return state["engine"]

    def get_recorder() -> Recorder:
        if state["recorder"] is None:
            if recorder_factory is not None:
                state["recorder"] = recorder_factory(get_engine(), store, _publish_event)
            else:
                state["recorder"] = Recorder(get_engine(), store, on_event=_publish_event)
        return state["recorder"]

    def _publish_event(ev: TranscriptEvent) -> None:
        broadcaster.publish(
            {
                "type": "transcript",
                "source": ev.source,
                "t_start_ms": ev.t_start_ms,
                "t_end_ms": ev.t_end_ms,
                "text": ev.text,
                "is_final": ev.is_final,
            }
        )

    def check_token(token_param: str = Query(..., alias="token")) -> None:
        # `compare_digest` invece di `==`: il confronto normale esce al primo
        # byte diverso e i tempi di risposta rivelano il token un carattere
        # alla volta.
        if not secrets.compare_digest(token_param, token):
            raise HTTPException(status_code=401, detail="token non valido")

    app.router.lifespan_context = _lifespan(broadcaster, state)

    # ------------------------------------------------------------------- stato

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Senza token: serve al processo padre per sapere quando il core è su."""
        recorder = state.get("recorder")
        return {
            "ok": True,
            "modello_caricato": state["engine"] is not None,
            "in_registrazione": bool(recorder and recorder.is_recording),
        }

    @app.get("/session/state", dependencies=[Depends(check_token)])
    async def session_state() -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None or not recorder.is_recording:
            return {"in_registrazione": False}
        return {
            "in_registrazione": True,
            "session_id": recorder.session_id,
            "now_ms": recorder.now_ms(),
            "stato": recorder.clock.state.value if recorder.clock else None,
        }

    # ------------------------------------------------------------ registrazione

    @app.post("/session/start", dependencies=[Depends(check_token)])
    async def session_start(req: StartRequest) -> dict[str, Any]:
        recorder = get_recorder()
        if recorder.is_recording:
            raise HTTPException(status_code=409, detail="registrazione già in corso")

        import time

        try:
            info = await asyncio.to_thread(
                recorder.start,
                titolo=req.titolo,
                piattaforma=req.piattaforma,
                lingua=req.lingua,
                consenso_confermato_at=int(time.time() * 1000) if req.consenso_confermato else None,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        payload = {
            "session_id": info.session_id,
            "started_at_ms": info.started_at_ms,
            "devices": {s: d.name for s, d in info.devices.items()},
        }
        broadcaster.publish({"type": "session_started", **payload})
        return payload

    @app.post("/session/stop", dependencies=[Depends(check_token)])
    async def session_stop() -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None or not recorder.is_recording:
            raise HTTPException(status_code=409, detail="nessuna registrazione in corso")
        session_id = await asyncio.to_thread(recorder.stop)
        broadcaster.publish({"type": "session_stopped", "session_id": session_id})
        return {"session_id": session_id}

    @app.post("/session/pause", dependencies=[Depends(check_token)])
    async def session_pause() -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None or not recorder.is_recording:
            raise HTTPException(status_code=409, detail="nessuna registrazione in corso")
        recorder.pause()
        return {"stato": "paused"}

    @app.post("/session/resume", dependencies=[Depends(check_token)])
    async def session_resume() -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None:
            raise HTTPException(status_code=409, detail="nessuna registrazione in corso")
        recorder.resume()
        return {"stato": "recording"}

    @app.post("/session/screenshot", dependencies=[Depends(check_token)])
    async def session_screenshot(req: ScreenshotRequest) -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None or not recorder.is_recording:
            raise HTTPException(status_code=409, detail="nessuna registrazione in corso")
        shot_id, t_ms = recorder.add_screenshot(
            req.path, nota_utente=req.nota_utente, width=req.width, height=req.height
        )
        payload = {"type": "screenshot", "id": shot_id, "t_ms": t_ms, "path": req.path}
        broadcaster.publish(payload)
        return {"id": shot_id, "t_ms": t_ms}

    # ---------------------------------------------------------------- lettura

    @app.get("/sessions", dependencies=[Depends(check_token)])
    async def sessions(limit: int = 50) -> list[dict[str, Any]]:
        rows = store.conn.execute(
            """
            SELECT id, uuid, titolo, piattaforma, started_at, ended_at, durata_ms,
                   stato, lingua, stt_model
              FROM sessions ORDER BY started_at DESC LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in rows]

    @app.get("/sessions/{session_id}/segments", dependencies=[Depends(check_token)])
    async def segments(session_id: int) -> list[dict[str, Any]]:
        return [
            {
                "id": s.id,
                "source": s.source,
                "t_start_ms": s.t_start_ms,
                "t_end_ms": s.t_end_ms,
                "testo": s.testo,
                "is_final": s.is_final,
                "revision": s.revision,
            }
            for s in store.segments(session_id)
        ]

    @app.get("/search", dependencies=[Depends(check_token)])
    async def search(q: str, limit: int = 50) -> list[dict[str, Any]]:
        return [dict(r) for r in store.search(q, limit=limit)]

    # -------------------------------------------------------------- websocket

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket, token_param: str = Query(..., alias="token")) -> None:
        if not secrets.compare_digest(token_param, token):
            await ws.close(code=4401)
            return
        await broadcaster.connect(ws)
        try:
            while True:
                # Non si aspettano comandi dal client — i comandi passano dalle
                # rotte HTTP. Leggere serve solo ad accorgersi della chiusura.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.disconnect(ws)

    app.state.store = store
    app.state.token = token
    return app


def _exit_when_orphaned() -> None:
    """Si spegne quando il processo padre sparisce.

    Se l'interfaccia viene chiusa male o va in crash, questo processo resterebbe
    vivo tenendo occupato il microfono: alla registrazione successiva il device
    risulta in uso e non si capisce perché. Il canale è lo standard input, che il
    sistema chiude quando il padre muore — funziona anche se il padre non ha
    fatto in tempo a terminarci.
    """
    import os
    import sys

    def watch() -> None:
        try:
            while sys.stdin.readline():
                pass
        except Exception:
            pass
        # Uscita brutale di proposito: a questo punto non c'è più nessuno a cui
        # rispondere, e uno spegnimento ordinato potrebbe restare appeso.
        os._exit(0)

    if sys.stdin is not None and not sys.stdin.closed:
        threading.Thread(target=watch, name="orphan-watch", daemon=True).start()


def run(db_path: Path | str = "data/scriba.sqlite", host: str = "127.0.0.1") -> None:
    """Avvia il core e annuncia al processo padre dove trovarlo.

    La porta la sceglie il sistema: si stampa su stdout una riga JSON con porta
    e token, che è il modo in cui la shell Electron scopre come collegarsi.
    """
    import socket

    import uvicorn

    _exit_when_orphaned()
    token = secrets.token_urlsafe(32)

    # Si apre il socket qui, così la porta è nota prima dell'avvio e si può
    # annunciare subito. Il socket viene poi passato a uvicorn già aperto:
    # chiuderlo e ridare solo il numero lascerebbe una finestra in cui un altro
    # processo può prendersi quella porta.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, 0))
    # `listen` qui e non solo dentro uvicorn: fra l'annuncio della porta e il
    # momento in cui uvicorn e' pronto passa quasi un secondo, e in quella
    # finestra le richieste verrebbero rifiutate con "connection refused".
    # Mettendosi in ascolto subito, restano in coda finche' non c'e' chi
    # risponde.
    sock.listen(128)
    port = sock.getsockname()[1]

    print(json.dumps({"port": port, "token": token}), flush=True)

    app = create_app(db_path=Path(db_path), token=token)
    # `sockets=[...]` e non `fd=`: quest'ultimo in uvicorn passa da
    # `socket.fromfd(..., AF_UNIX)`, che su Windows non esiste.
    uvicorn.Server(
        uvicorn.Config(app, log_level="warning", access_log=False)
    ).run(sockets=[sock])


if __name__ == "__main__":  # pragma: no cover
    import sys

    run(sys.argv[1] if len(sys.argv) > 1 else "data/scriba.sqlite")
