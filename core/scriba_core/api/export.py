"""Rotte di export e dei connettori (Notion, HTTP generico).

Stesso schema di `modelli.py`: rotte sottili, la logica vera vive nei moduli
di `export/`. `server.py` monta questo router (lo sta riscrivendo un altro
agente in parallelo): qui non si tocca altro.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import Contesto
from ..export import esporta
from ..export.http_generico import HttpGenericoError
from ..export.http_generico import invia as invia_http
from ..export.notion import NotionError
from ..export.notion import collega as notion_collega
from ..export.notion import invia as invia_notion
from ..export.notion import scollega as notion_scollega
from ..export.notion import stato as notion_stato


class EsportaRequest(BaseModel):
    # None = si usano le impostazioni salvate (export.formato/export.cartella).
    formato: str | None = None
    destinazione: str | None = None


class NotionCollegaRequest(BaseModel):
    # Vuoto = non cambiare: stesso comportamento di llm.api_key in settings.py,
    # dato che l'interfaccia non rimanda mai indietro il token già salvato.
    token: str = ""
    database_id: str = ""


class HttpGenericoRequest(BaseModel):
    url: str
    token: str | None = None


def crea_router(ctx: Contesto) -> APIRouter:
    router = APIRouter(tags=["export"])

    @router.post("/sessions/{session_id}/export")
    async def esporta_call(session_id: int, req: EsportaRequest) -> dict[str, Any]:
        destinazione = Path(req.destinazione) if req.destinazione else None
        try:
            percorso = await asyncio.to_thread(
                esporta, session_id, ctx.store, formato=req.formato, destinazione=destinazione
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"percorso": str(percorso)}

    # ------------------------------------------------------------------ notion

    @router.get("/export/notion/stato")
    async def notion_stato_rotta() -> dict[str, Any]:
        return await asyncio.to_thread(notion_stato, ctx.store)

    @router.post("/export/notion/collega")
    async def notion_collega_rotta(req: NotionCollegaRequest) -> dict[str, Any]:
        return await asyncio.to_thread(
            notion_collega, ctx.store, token=req.token, database_id=req.database_id
        )

    @router.post("/export/notion/scollega")
    async def notion_scollega_rotta() -> dict[str, Any]:
        return await asyncio.to_thread(notion_scollega, ctx.store)

    @router.post("/sessions/{session_id}/export/notion")
    async def esporta_notion(session_id: int) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(invia_notion, session_id, ctx.store, {})
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except NotionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ------------------------------------------------------------ http generico

    @router.post("/sessions/{session_id}/export/http")
    async def esporta_http(session_id: int, req: HttpGenericoRequest) -> dict[str, Any]:
        config = {"url": req.url, "token": req.token}
        try:
            return await asyncio.to_thread(invia_http, session_id, ctx.store, config)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except HttpGenericoError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
