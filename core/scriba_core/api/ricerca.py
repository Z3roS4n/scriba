"""Le tre ricerche dell'archivio, e l'indice che ne regge due.

Normale è quella che c'era: parole esatte, `/archivio` in `clienti.py`, e non
si tocca. Qui ci sono le altre due.

**Semantica** cerca per significato e restituisce le stesse call che
restituirebbe l'archivio, nella stessa forma, ordinate per vicinanza invece che
per data. È di proposito: chi passa da una modalità all'altra deve ritrovare la
stessa schermata, non impararne una nuova.

**Contestuale** fa una domanda al modello di linguaggio e riporta la risposta
con dentro le call da cui viene.

I filtri valgono per tutte e tre. Cliente, periodo e stato non sono un
accessorio della ricerca normale: si applicano prima, e le altre due guardano
soltanto dentro le call che quei filtri hanno lasciato passare.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..ai.contesto import IndiceMancante, RicercaContestuale
from ..i18n import LinguaUI
from ..semantica import ErroreSemantica, Indice, IndiceVuoto, installato
from . import STATI_GREZZI, Contesto, traduci_stato_sessione

log = logging.getLogger(__name__)


class Filtri(BaseModel):
    """Gli stessi di `/archivio`, perché sono la stessa domanda."""

    client_id: int | None = None
    senza_cliente: bool = False
    da_ms: int | None = None
    a_ms: int | None = None
    stato: str | None = None
    limit: int = 200


class RicercaRequest(Filtri):
    testo: str


class DomandaRequest(Filtri):
    domanda: str
    # Le call dello stesso cliente vicine nel tempo si leggono come un discorso
    # solo. Attivo di default: è il motivo per cui questa ricerca esiste, e chi
    # non lo vuole ha l'interruttore sotto gli occhi.
    unisci_catene: bool = True


class IndicizzaRequest(BaseModel):
    #: Vuoto = tutto l'archivio.
    session_ids: list[int] = []


def _fermo() -> dict[str, Any]:
    return {"in_corso": False, "fatte": 0, "totale": 0, "annulla": None, "errore": None}


def crea_router(ctx: Contesto) -> APIRouter:
    router = APIRouter(tags=["ricerca"])
    ctx.state.setdefault("indice_semantico", _fermo())

    # ------------------------------------------------------------- il modello

    def _embedder():
        """Il modello, caricato una volta sola e tenuto lì.

        Caricarlo costa un secondo e mezzo e mezzo gigabyte di RAM: rifarlo a
        ogni ricerca vorrebbe dire una ricerca che va a scatti senza motivo.
        """
        gia = ctx.state.get("embedder")
        if gia is not None:
            return gia
        if not installato():
            # Scaricare mezzo gigabyte non è una cosa che debba partire da sé
            # in mezzo a una ricerca: si dice dov'è il pulsante.
            raise HTTPException(
                status_code=412,
                detail="Il modello per la ricerca semantica non è ancora installato. "
                "Si scarica dalle impostazioni, alla voce Modelli.",
            )
        from ..semantica import carica

        try:
            ctx.state["embedder"] = carica()
        except ErroreSemantica as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return ctx.state["embedder"]

    async def _indice() -> Indice:
        return Indice(ctx.store, await asyncio.to_thread(_embedder))

    # -------------------------------------------------------------- i filtri

    def _filtrate(f: Filtri) -> list[Any]:
        grezzi = STATI_GREZZI.get(f.stato) if f.stato else None
        if f.stato and not grezzi:
            raise HTTPException(status_code=400, detail=f"Stato sconosciuto: {f.stato}")
        return ctx.store.cerca_call(
            client_id=f.client_id,
            senza_cliente=f.senza_cliente,
            da_ms=f.da_ms,
            a_ms=f.a_ms,
            stati=grezzi,
            limit=f.limit,
        )

    def _in_analisi() -> int | None:
        return ctx.state.get("analisi_session_id") if ctx.state.get("analisi_in_corso") else None

    def _voce(riga: Any, analisi: int | None) -> dict[str, Any]:
        voce = dict(riga)
        voce["stato"] = traduci_stato_sessione(voce["stato"], in_analisi=voce["id"] == analisi)
        return voce

    # --------------------------------------------------------------- lo stato

    @router.get("/ricerca/stato")
    async def stato() -> dict[str, Any]:
        """Quanto dell'archivio è indicizzato, e se il modello c'è.

        Non carica il modello: chi guarda le impostazioni non deve pagare mezzo
        gigabyte di RAM per sapere che manca un pulsante da premere.
        """
        lavoro = ctx.state.get("indice_semantico", _fermo())
        c_è = installato()
        firme = await asyncio.to_thread(ctx.store.firme_trascrizioni)
        salvato = await asyncio.to_thread(ctx.store.stato_indice, list(firme) or None)
        aggiornate = sum(
            1 for sid, firma in firme.items() if sid in salvato and salvato[sid]["firma"] == firma
        )
        return {
            "modello_installato": c_è,
            "call_con_parlato": len(firme),
            "call_indicizzate": aggiornate,
            "passaggi": sum(int(r["n_passaggi"]) for r in salvato.values()),
            "in_corso": bool(lavoro["in_corso"]),
            "fatte": lavoro["fatte"],
            "totale": lavoro["totale"],
            "errore": lavoro["errore"],
        }

    # --------------------------------------------------------- indicizzazione

    @router.post("/ricerca/indicizza")
    async def indicizza(req: IndicizzaRequest) -> dict[str, Any]:
        lavoro = ctx.state.get("indice_semantico", _fermo())
        if lavoro["in_corso"]:
            return {"stato": "già_avviata", "totale": lavoro["totale"]}
        if ctx.state.get("recorder") is not None:
            # Indicizzare prende metà dei core per qualche minuto. Farlo mentre
            # si sta registrando vorrebbe dire rischiare la trascrizione dal
            # vivo per un lavoro che può aspettare la fine della call.
            raise HTTPException(
                status_code=409,
                detail="C'è una registrazione in corso: l'indice si aggiorna dopo.",
            )

        indice = await _indice()
        annulla = threading.Event()
        ctx.state["indice_semantico"] = {
            "in_corso": True,
            "fatte": 0,
            "totale": 0,
            "annulla": annulla,
            "errore": None,
        }

        def _avanzamento(fatte: int, totale: int) -> None:
            s = ctx.state["indice_semantico"]
            s["fatte"], s["totale"] = fatte, totale
            ctx.publish(
                {"type": "indice_semantico", "stato": "in_corso", "fatte": fatte, "totale": totale}
            )

        async def lavora() -> None:
            try:
                riepilogo = await asyncio.to_thread(
                    lambda: indice.aggiorna(
                        req.session_ids or None,
                        avanzamento=_avanzamento,
                        fermati=annulla.is_set,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - va riportato, non nascosto
                log.exception("Indicizzazione semantica non riuscita")
                fine = _fermo()
                fine["errore"] = str(exc)
                ctx.state["indice_semantico"] = fine
                ctx.publish(
                    {"type": "indice_semantico", "stato": "errore", "dettaglio": str(exc)}
                )
                return

            ctx.state["indice_semantico"] = _fermo()
            ctx.publish(
                {
                    "type": "indice_semantico",
                    "stato": "interrotta" if riepilogo.interrotta else "finita",
                    "call": riepilogo.call,
                    "passaggi": riepilogo.passaggi,
                    "secondi": round(riepilogo.secondi, 1),
                }
            )

        asyncio.get_running_loop().create_task(lavora())
        return {"stato": "avviata"}

    async def _indicizza_una(session_id: int) -> None:
        """Mette in indice una call appena finita, se ha senso farlo.

        Ogni condizione mancante fa uscire in silenzio, come per la rifinitura
        automatica: è un di più, e non deve poter far sembrare rotta una call
        registrata bene.

        Le condizioni sono due, e la seconda è la più importante. Il modello
        dev'essere già scaricato, e **l'archivio dev'essere già indicizzato**:
        senza la seconda, la prima riunione dopo l'aggiornamento farebbe
        caricare mezzo giga di pesi per una funzione che chi usa Scriba non ha
        mai chiesto. Indicizzare una volta è il gesto con cui la si chiede.

        Una call sola costa meno di un secondo — sono le prime, tutte insieme,
        a durare minuti — quindi qui non c'è niente da rimandare o da spezzare.
        """
        # «Già caricato» conta quanto «installato»: se il modello è in memoria
        # è utilizzabile, e chiedere al disco se c'è sarebbe una domanda a cui
        # si è già risposto.
        if ctx.state.get("embedder") is None and not installato():
            return
        if ctx.state.get("indice_semantico", {}).get("in_corso"):
            return
        if not await asyncio.to_thread(lambda: ctx.store.stato_indice()):
            return
        try:
            indice = await _indice()
            await asyncio.to_thread(lambda: indice.aggiorna([session_id]))
        except Exception:
            log.exception("Indicizzazione automatica non riuscita per la sessione %s", session_id)

    # Come `avvia_rifinitura`: il server chiama questa a fine call senza dover
    # sapere né dove sta il modello né come si costruisce un indice.
    ctx.state["indicizza_call"] = _indicizza_una

    @router.post("/ricerca/indicizza/ferma")
    async def ferma() -> dict[str, Any]:
        lavoro = ctx.state.get("indice_semantico", _fermo())
        annulla = lavoro.get("annulla")
        if annulla is not None:
            annulla.set()
        return {"stato": "fermata" if annulla is not None else "ferma"}

    @router.post("/ricerca/dimentica")
    async def dimentica() -> dict[str, Any]:
        quante = await asyncio.to_thread(ctx.store.dimentica_indice)
        return {"call": quante}

    # ------------------------------------------------------------- semantica

    @router.post("/ricerca/semantica")
    async def semantica(req: RicercaRequest) -> dict[str, Any]:
        righe = await asyncio.to_thread(_filtrate, req)
        if not righe or not req.testo.strip():
            return {"call": [], "indicizzate": 0, "da_indicizzare": 0}

        per_id = {r["id"]: r for r in righe}
        indice = await _indice()
        try:
            trovati = await asyncio.to_thread(
                lambda: indice.cerca(req.testo, session_ids=list(per_id))
            )
        except IndiceVuoto:
            # Zero risultati sarebbe indistinguibile da «non c'è niente»:
            # l'interfaccia deve poter dire che manca l'indice, non la risposta.
            trovati = []

        analisi = _in_analisi()
        # Una call vale il suo passaggio migliore: mostrarla una volta per
        # passaggio riempirebbe l'elenco di righe uguali con dentro pezzi
        # diversi della stessa conversazione.
        migliori: dict[int, Any] = {}
        for t in trovati:
            if t.session_id not in migliori:
                migliori[t.session_id] = t

        call = []
        for sid, t in migliori.items():
            voce = _voce(per_id[sid], analisi)
            # Gli stessi marcatori della ricerca normale (`\x02`/`\x03`): qui
            # non c'è una parola da evidenziare — è il passaggio intero a
            # somigliare — quindi il frammento arriva senza, e l'interfaccia lo
            # mostra con lo stesso codice.
            voce["frammento"] = t.testo
            voce["quando_ms"] = t.t_start_ms
            call.append(voce)

        da_fare = await asyncio.to_thread(indice.da_fare, list(per_id))
        return {"call": call, "indicizzate": len(per_id) - len(da_fare), "da_indicizzare": len(da_fare)}

    # ------------------------------------------------------------ contestuale

    @router.post("/ricerca/contestuale")
    async def contestuale(req: DomandaRequest, lingua: LinguaUI) -> dict[str, Any]:
        if not req.domanda.strip():
            raise HTTPException(status_code=400, detail="La domanda è vuota.")

        from ..llm.providers import costruisci

        provider = costruisci(ctx.settings.llm())
        if not await asyncio.to_thread(provider.available):
            raise HTTPException(
                status_code=412,
                detail="Il modello di analisi non è raggiungibile. Se usi quello locale, "
                "avvia llama-server; se usi l'abbonamento Claude, rifai l'accesso con "
                "`claude auth login`; se usi un'API, controlla la chiave nelle impostazioni.",
            )

        righe = await asyncio.to_thread(_filtrate, req)
        if not righe:
            return {"risposta": "", "call": [], "catene": [], "passaggi_letti": 0}
        per_id = {r["id"]: r for r in righe}

        cerca = RicercaContestuale(ctx.store, await _indice(), provider)
        try:
            risposta = await asyncio.to_thread(
                lambda: cerca.rispondi(
                    req.domanda,
                    session_ids=list(per_id),
                    unisci_catene=req.unisci_catene,
                    lingua=lingua,
                )
            )
        except IndiceMancante as exc:
            raise HTTPException(
                status_code=412,
                detail="La ricerca contestuale ha bisogno dell'indice semantico, "
                "che non è ancora stato costruito.",
            ) from exc

        analisi = _in_analisi()
        return {
            "risposta": risposta.testo,
            "call": [
                {
                    **_voce(per_id[c.session_id], analisi),
                    "perche": c.perche,
                    "passaggi": [
                        {"testo": p.testo, "quando_ms": p.t_start_ms} for p in c.passaggi
                    ],
                }
                for c in risposta.call
                if c.session_id in per_id
            ],
            # Una lista di coppie e non due liste parallele: `session_ids` e
            # `titoli` affiancati si disallineano al primo filtro che tolga di
            # mezzo un elemento dell'una e non dell'altra, e il risultato — una
            # catena mostrata con i titoli sfalsati — è indistinguibile da una
            # catena vera.
            "catene": [
                {
                    "call": [
                        {"id": s, "titolo": per_id[s]["titolo"] if s in per_id else None}
                        for s in c.session_ids
                    ]
                }
                for c in risposta.catene
            ],
            "passaggi_letti": risposta.passaggi_letti,
            "modello": risposta.modello,
            "provider": risposta.provider,
            "costo_usd": risposta.costo_usd,
        }

    return router
