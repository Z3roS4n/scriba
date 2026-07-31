"""Rotte dei clienti e dell'archivio delle call.

Stesso schema degli altri moduli di `api/`: rotte sottili, la logica sta in
`db/store.py`. L'unica cosa che vive davvero qui è la lettura del CSV — è un
formato, non un modello dati, e non ha motivo di stare nello store.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import STATI_GREZZI, Contesto, traduci_stato_sessione

# Come si chiama la colonna del nome, nei file che la gente ha davvero.
# L'ordine conta: si prende la prima che si trova.
_INTESTAZIONI_NOME = ("nome", "cliente", "ragione sociale", "azienda", "name", "client", "company")
_INTESTAZIONI_NOTE = ("note", "nota", "descrizione", "notes", "description")


class ClienteRequest(BaseModel):
    nome: str = ""
    note: str | None = None
    archiviato: bool | None = None


class AssegnaClienteRequest(BaseModel):
    # None = togli il cliente da questa call, che è diverso da "non cambiare".
    client_id: int | None = None


class ImportaClientiRequest(BaseModel):
    #: Il contenuto del file, non un percorso: il core non deve leggere dal
    #: disco per conto del renderer.
    csv: str


def _colonna(intestazioni: list[str], candidate: tuple[str, ...]) -> str | None:
    normalizzate = {h.strip().casefold(): h for h in intestazioni if h}
    for c in candidate:
        if c in normalizzate:
            return normalizzate[c]
    return None


def leggi_csv(testo: str) -> list[tuple[str, str | None]]:
    """Estrae (nome, note) da un CSV, indovinando il separatore e le colonne.

    Tre cose che i file veri hanno e un parser ingenuo no:

    - il separatore può essere `,` o `;` (Excel italiano usa il secondo), e si
      lascia decidere a `csv.Sniffer` invece di imporne uno;
    - l'intestazione può mancare del tutto — in quel caso la prima colonna è il
      nome, che è l'unica interpretazione sensata di un elenco di nomi;
    - l'intestazione può chiamarsi in molti modi, e sbagliare colonna è peggio
      che chiedere.

    Che ci sia un'intestazione lo decide il riconoscimento di un nome di
    colonna, non `csv.Sniffer().has_header()`: quello indovina dai tipi delle
    celle e su file corti sbaglia in silenzio, mangiandosi la prima riga o
    trattandola come un cliente di nome "nome". Qui la regola è esplicita — se
    la prima riga contiene una colonna che sappiamo leggere, è
    un'intestazione — e sbaglia solo su un cliente che si chiami davvero
    "Nome".
    """
    testo = testo.lstrip("﻿").strip()
    if not testo:
        return []

    campione = testo[:4096]
    try:
        dialetto = csv.Sniffer().sniff(campione, delimiters=",;\t")
    except csv.Error:
        # Una colonna sola: non c'è nessun separatore da riconoscere, e
        # Sniffer solleva invece di dire "nessuno".
        dialetto = csv.excel

    righe = list(csv.reader(io.StringIO(testo), dialetto))
    if not righe:
        return []

    intestazioni = [c.strip() for c in righe[0]]
    col_nome = _colonna(intestazioni, _INTESTAZIONI_NOME)
    if col_nome is not None:
        col_note = _colonna(intestazioni, _INTESTAZIONI_NOTE)
        i_nome = intestazioni.index(col_nome)
        i_note = intestazioni.index(col_note) if col_note is not None else None
        corpo = righe[1:]
    else:
        # Nessuna colonna che sappiamo leggere: è un elenco di nomi, e il nome
        # sta nella prima colonna.
        i_nome, i_note, corpo = 0, None, righe

    voci: list[tuple[str, str | None]] = []
    for riga in corpo:
        if not riga or i_nome >= len(riga):
            continue
        nome = riga[i_nome].strip()
        if not nome:
            continue
        note = riga[i_note].strip() if i_note is not None and i_note < len(riga) else None
        voci.append((nome, note or None))
    return voci


def crea_router(ctx: Contesto) -> APIRouter:
    router = APIRouter(tags=["clienti"])

    @router.get("/clienti")
    async def elenca(includi_archiviati: bool = False) -> list[dict[str, Any]]:
        return [dict(r) for r in ctx.store.clienti(includi_archiviati=includi_archiviati)]

    @router.post("/clienti")
    async def crea(req: ClienteRequest) -> dict[str, Any]:
        client_id = ctx.store.crea_cliente(req.nome, note=req.note)
        if client_id is None:
            raise HTTPException(status_code=400, detail="Il nome del cliente non può essere vuoto.")
        return {"id": client_id}

    @router.patch("/clienti/{client_id}")
    async def aggiorna(client_id: int, req: ClienteRequest) -> dict[str, Any]:
        # `nome` vuoto qui vuol dire "non lo sto cambiando", come per le chiavi
        # API in settings.py: l'interfaccia manda l'oggetto intero anche quando
        # tocca un campo solo.
        riuscito = ctx.store.aggiorna_cliente(
            client_id,
            nome=req.nome or None,
            note=req.note,
            archiviato=req.archiviato,
        )
        if not riuscito:
            raise HTTPException(
                status_code=400,
                detail="Cliente non aggiornato: non esiste, oppure quel nome è già di un altro.",
            )
        return {"ok": True}

    # POST e non DELETE: è la forma che il progetto usa già per le sessioni e
    # per i modelli, ed è anche l'unica che il ponte del renderer sa mandare
    # (`preload.ts` espone get/post/patch e basta).
    @router.post("/clienti/{client_id}/elimina")
    async def elimina(client_id: int) -> dict[str, Any]:
        if not ctx.store.elimina_cliente(client_id):
            raise HTTPException(status_code=404, detail="Cliente inesistente.")
        return {"ok": True}

    @router.post("/clienti/importa")
    async def importa(req: ImportaClientiRequest) -> dict[str, int]:
        voci = leggi_csv(req.csv)
        if not voci:
            raise HTTPException(
                status_code=400,
                detail="Nessun nome trovato nel file: serve almeno una colonna con i nomi.",
            )
        return ctx.store.importa_clienti(voci)

    @router.patch("/sessions/{session_id}/cliente")
    async def assegna(session_id: int, req: AssegnaClienteRequest) -> dict[str, Any]:
        if not ctx.store.assegna_cliente(session_id, req.client_id):
            raise HTTPException(status_code=404, detail="Call o cliente inesistente.")
        return {"ok": True}

    @router.get("/archivio")
    async def archivio(
        testo: str | None = None,
        client_id: int | None = None,
        senza_cliente: bool = False,
        da_ms: int | None = None,
        a_ms: int | None = None,
        stato: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Le call che rispondono ai filtri, con dentro il nome del cliente.

        `stato` è quello che si vede nell'interfaccia, non quello del database:
        chi filtra sceglie da un elenco di etichette, e non deve sapere che
        dietro "registrata" ce ne sono due.
        """
        grezzi = STATI_GREZZI.get(stato) if stato else None
        if stato and not grezzi:
            raise HTTPException(status_code=400, detail=f"Stato sconosciuto: {stato}")

        righe = ctx.store.cerca_call(
            testo=testo,
            client_id=client_id,
            senza_cliente=senza_cliente,
            da_ms=da_ms,
            a_ms=a_ms,
            stati=grezzi,
            limit=limit,
        )

        in_analisi = ctx.state.get("analisi_session_id") if ctx.state.get("analisi_in_corso") else None
        risultato = []
        for r in righe:
            voce = dict(r)
            voce["stato"] = traduci_stato_sessione(
                voce["stato"], in_analisi=voce["id"] == in_analisi
            )
            risultato.append(voce)
        return risultato

    return router
