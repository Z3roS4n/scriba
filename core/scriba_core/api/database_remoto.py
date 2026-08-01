"""Rotte del database remoto.

Rotte sottili come gli altri moduli di `api/`: la logica sta in
`export/sql/`. L'unica regola che vive qui è quella di sempre — il segreto
entra, non esce mai.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import Contesto
from ..export import sql
from ..export.sql import modello
from ..export.sql.postgres import ErroreSql


class Connessione(BaseModel):
    # Vuoto = quello già salvato. L'interfaccia non lo rimanda mai indietro,
    # perché non gliel'abbiamo mai mostrato.
    url: str = ""
    modalita: str = ""


class SchemaRequest(Connessione):
    schema_remoto: str


class TabellaRequest(SchemaRequest):
    tabella: str
    per: str


class CreaRequest(SchemaRequest):
    prefisso: str = sql.PREFISSO_PREDEFINITO
    tabelle: list[str] = []


class AnteprimaRequest(BaseModel):
    schema_remoto: str
    prefisso: str = sql.PREFISSO_PREDEFINITO
    tabelle: list[str] = []


class CollegaRequest(Connessione):
    schema_remoto: str = ""
    prefisso: str = ""
    # None = non cambiare la mappatura.
    tabelle: dict[str, Any] | None = None
    automatico: bool | None = None


def crea_router(ctx: Contesto) -> APIRouter:
    router = APIRouter(tags=["database-remoto"])

    def _in_thread(fn, *args, **kwargs):
        # Ogni chiamata al database remoto va fuori dal loop: durante una
        # registrazione un server lento non deve fermare la trascrizione.
        return asyncio.to_thread(fn, *args, **kwargs)

    @router.get("/database-remoto/stato")
    async def stato() -> dict[str, Any]:
        return await _in_thread(sql.stato, ctx.store)

    @router.get("/database-remoto/modello")
    async def modello_dati() -> list[dict[str, Any]]:
        """Cosa Scriba sa mandare. Non tocca la rete."""
        return modello.descrivi()

    @router.post("/database-remoto/prova")
    async def prova(req: Connessione) -> dict[str, Any]:
        try:
            return await _in_thread(sql.prova, ctx.store, url=req.url, modalita=req.modalita)
        except ErroreSql as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/database-remoto/tabelle")
    async def tabelle(req: SchemaRequest) -> list[str]:
        try:
            return await _in_thread(
                sql.tabelle_esistenti,
                ctx.store,
                url=req.url,
                modalita=req.modalita,
                schema=req.schema_remoto,
            )
        except ErroreSql as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/database-remoto/colonne")
    async def colonne(req: TabellaRequest) -> dict[str, Any]:
        try:
            return await _in_thread(
                sql.colonne_di,
                ctx.store,
                url=req.url,
                modalita=req.modalita,
                schema=req.schema_remoto,
                tabella=req.tabella,
                per=req.per,
            )
        except ErroreSql as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/database-remoto/anteprima")
    async def anteprima(req: AnteprimaRequest) -> list[dict[str, str]]:
        """Il DDL che verrebbe eseguito. Nessuna connessione: è solo testo."""
        return sql.anteprima_ddl(
            schema=req.schema_remoto, prefisso=req.prefisso, tabelle=req.tabelle
        )

    @router.post("/database-remoto/crea")
    async def crea(req: CreaRequest) -> dict[str, Any]:
        try:
            return await _in_thread(
                sql.crea,
                ctx.store,
                url=req.url,
                modalita=req.modalita,
                schema=req.schema_remoto,
                prefisso=req.prefisso,
                tabelle=req.tabelle,
            )
        except ErroreSql as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/database-remoto/collega")
    async def collega(req: CollegaRequest) -> dict[str, Any]:
        try:
            return await _in_thread(
                sql.collega,
                ctx.store,
                url=req.url,
                modalita=req.modalita,
                schema=req.schema_remoto,
                prefisso=req.prefisso,
                tabelle=req.tabelle,
                automatico=req.automatico,
            )
        except ErroreSql as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/database-remoto/scollega")
    async def scollega() -> dict[str, Any]:
        return await _in_thread(sql.scollega, ctx.store)

    @router.post("/sessions/{session_id}/database-remoto")
    async def sincronizza(session_id: int) -> dict[str, Any]:
        try:
            return await _in_thread(sql.invia, session_id, ctx.store)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ErroreSql as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/database-remoto/sincronizza-tutto")
    async def tutto() -> dict[str, Any]:
        try:
            return await _in_thread(sql.sincronizza_tutto, ctx.store)
        except ErroreSql as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
