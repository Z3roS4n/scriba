"""Modelli locali: elenco, scaricamento, verifica, avvio.

Ogni rotta è sottile apposta: la logica — thread di download, controllo dello
spazio, verifica dell'hash, Job Object per non lasciare processi orfani — vive
in `ModelsManager`. Qui si traduce solo fra HTTP e quello.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from . import Contesto
from ..models_manager import ModelsManager


def crea_router(ctx: Contesto) -> APIRouter:
    router = APIRouter(tags=["modelli"])
    # Un'unica istanza per processo: tiene il thread di download attivo e il
    # sottoprocesso di llama-server, che non avrebbe senso duplicare fra una
    # richiesta e l'altra. `crea_router` viene chiamata una sola volta
    # all'avvio, quindi il manager vive quanto il server.
    manager = ModelsManager(ctx.db_path.parent / "models", on_evento=ctx.publish)

    @router.get("/modelli")
    async def elenco() -> list[dict]:
        return manager.elenco_modelli()

    @router.get("/disco")
    async def disco() -> dict:
        return manager.disco()

    @router.post("/modelli/{model_id}/scarica")
    async def scarica(model_id: str) -> dict:
        # Il controllo dello spazio e l'avvio del thread sono rapidi: non c'è
        # vero bisogno di un thread executor qui, ma restare fuori dal loop è
        # la regola per qualunque rotta di questo file, senza eccezioni da
        # ricordare caso per caso.
        try:
            return await asyncio.to_thread(manager.avvia_download, model_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/modelli/{model_id}/sospendi")
    async def sospendi(model_id: str) -> dict:
        try:
            return await asyncio.to_thread(manager.sospendi_download, model_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/modelli/{model_id}/elimina")
    async def elimina(model_id: str) -> dict:
        try:
            return await asyncio.to_thread(manager.elimina_modello, model_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/modelli/{model_id}/avvia")
    async def avvia(model_id: str) -> dict:
        try:
            return await asyncio.to_thread(manager.avvia_server, model_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/modelli/{model_id}/ferma")
    async def ferma(model_id: str) -> dict:
        # `model_id` non serve alla logica — un solo llama-server gira alla
        # volta — ma la rotta lo porta comunque: è così che l'ha definita il
        # contratto, ed è comunque comodo per validare che l'id esista.
        try:
            manager.modello(model_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        risultato = await asyncio.to_thread(manager.ferma_server)
        return risultato or manager.modello(model_id)

    return router
