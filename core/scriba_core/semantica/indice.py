"""L'indice semantico: costruirlo, tenerlo aggiornato, cercarci dentro.

Niente struttura dati furba. I vettori stanno in una colonna BLOB e la ricerca
è una moltiplicazione di matrici su tutto quello che i filtri hanno lasciato
passare. Un archivio di duecento ore di call fa circa dodicimila passaggi, cioè
18 MB di float: la moltiplicazione dura pochi millisecondi, e un indice
approssimato costerebbe una dipendenza binaria, una struttura da tenere
allineata al database e risultati leggermente diversi da quelli veri — in
cambio di niente, a queste dimensioni.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ..db.store import Store
from .modello import Embedder
from .spezza import in_passaggi

# Quanto può stare sotto al migliore un risultato per essere ancora mostrato.
#
# È una soglia **relativa**, e non poteva essere altrimenti: i punteggi di E5
# stanno tutti fra 0,80 e 0,90 anche fra frasi che non c'entrano niente fra
# loro, quindi «mostra sopra 0,75» mostrerebbe tutto e «sopra 0,90» niente.
#
# Il numero è misurato, non scelto (spikes/bench_semantica.py, 20 passaggi e 18
# domande): a -0,02 restano in media 2,9 passaggi su 20 e la risposta giusta ci
# sta 18 volte su 18; a -0,05 ne restano 12,9 su 20, cioè non si sta più
# filtrando niente. Qui si tiene -0,03 — 5,2 passaggi su 20, ancora 18 su 18 —
# per lasciare un margine a domande più vaghe di quelle della prova.
MARGINE = 0.03

# Per la ricerca contestuale la rete è più larga: lì a scegliere è il modello di
# linguaggio, che legge i passaggi e scarta da sé quelli che non c'entrano.
# Stringere prima vorrebbe dire togliergli materiale su cui ragionare.
MARGINE_LARGO = 0.06


@dataclass(frozen=True)
class Trovato:
    """Un passaggio che somiglia alla domanda, e quanto."""

    session_id: int
    ord: int
    t_start_ms: int
    t_end_ms: int
    testo: str
    punteggio: float


@dataclass(frozen=True)
class Riepilogo:
    """Cos'ha fatto un'indicizzazione."""

    call: int
    passaggi: int
    secondi: float
    interrotta: bool = False


class IndiceVuoto(RuntimeError):
    """Non c'è niente da cercare: nessuna call è stata indicizzata."""


class Indice:
    def __init__(self, store: Store, embedder: Embedder) -> None:
        self.store = store
        self.embedder = embedder

    # ---------------------------------------------------------- costruzione

    def da_fare(self, session_ids: list[int] | None = None) -> list[int]:
        """Le call il cui indice manca o è vecchio."""
        return self.store.da_indicizzare(self.embedder.id, session_ids)

    def aggiorna(
        self,
        session_ids: list[int] | None = None,
        *,
        avanzamento: Callable[[int, int], None] | None = None,
        fermati: Callable[[], bool] | None = None,
    ) -> Riepilogo:
        """Indicizza le call che ne hanno bisogno, una alla volta.

        Una call alla volta e salvata subito: indicizzare un archivio intero
        dura minuti, e se si interrompe a metà — l'applicazione si chiude,
        l'utente preme annulla — quello che è stato fatto deve restare fatto.
        Ricominciare da capo ogni volta significherebbe, su un archivio grande,
        non finire mai.
        """
        partito = time.perf_counter()
        da_fare = self.da_fare(session_ids)
        firme = self.store.firme_trascrizioni(da_fare)
        fatte = totale = 0
        interrotta = False

        for i, sid in enumerate(da_fare):
            if fermati is not None and fermati():
                interrotta = True
                break
            if avanzamento is not None:
                avanzamento(i, len(da_fare))
            firma = firme.get(sid)
            if firma is None:
                # Sparita fra il momento in cui si è deciso cosa fare e adesso:
                # può succedere, non è un errore.
                continue
            totale += self._indicizza(sid, firma)
            fatte += 1

        if avanzamento is not None:
            avanzamento(len(da_fare), len(da_fare))
        return Riepilogo(
            call=fatte,
            passaggi=totale,
            secondi=time.perf_counter() - partito,
            interrotta=interrotta,
        )

    def _indicizza(self, session_id: int, firma: str) -> int:
        segmenti = self.store.segments(session_id, only_final=True)
        passaggi = in_passaggi(segmenti)
        if not passaggi:
            # Nessun parlato utile: si salva comunque lo stato, altrimenti
            # questa call risulterebbe "da fare" a ogni giro, per sempre.
            self.store.salva_passaggi(
                session_id, [], modello=self.embedder.id, dim=self.embedder.dim, firma=firma
            )
            return 0

        vettori = self.embedder.vettori([p.testo for p in passaggi], come="passaggio")
        righe = [
            (p.ord, p.t_start_ms, p.t_end_ms, p.testo, v.astype("<f4").tobytes())
            for p, v in zip(passaggi, vettori, strict=True)
        ]
        return self.store.salva_passaggi(
            session_id, righe, modello=self.embedder.id, dim=self.embedder.dim, firma=firma
        )

    # -------------------------------------------------------------- ricerca

    def cerca(
        self,
        domanda: str,
        *,
        session_ids: list[int] | None = None,
        limite: int = 40,
        margine: float = MARGINE,
    ) -> list[Trovato]:
        """I passaggi più vicini alla domanda, dal più vicino.

        `session_ids` sono le call che i filtri dell'archivio hanno già
        lasciato passare: la ricerca semantica deve rispettare cliente,
        periodo e stato come quella normale, e il modo di farlo è non
        guardare affatto dentro le altre.
        """
        domanda = domanda.strip()
        if not domanda:
            return []
        righe = self.store.passaggi(session_ids)
        if not righe:
            raise IndiceVuoto("Nessuna call è stata ancora indicizzata.")

        matrice = np.frombuffer(b"".join(r["vettore"] for r in righe), dtype="<f4").reshape(
            len(righe), -1
        )
        if matrice.shape[1] != self.embedder.dim:
            # Indice scritto da un altro modello: confrontarlo con questo
            # darebbe punteggi plausibili e senza significato.
            raise IndiceVuoto("L'indice è stato costruito con un altro modello.")

        punteggi = (matrice @ self.embedder.vettori([domanda], come="domanda")[0]).astype(float)
        ordine = np.argsort(-punteggi)[:limite]
        soglia = float(punteggi[ordine[0]]) - margine
        return [
            Trovato(
                session_id=righe[i]["session_id"],
                ord=righe[i]["ord"],
                t_start_ms=righe[i]["t_start_ms"],
                t_end_ms=righe[i]["t_end_ms"],
                testo=righe[i]["testo"],
                punteggio=float(punteggi[i]),
            )
            for i in ordine
            if float(punteggi[i]) >= soglia
        ]

    # --------------------------------------------------------------- stato

    def stato(self) -> dict[str, int | str]:
        """Quanto dell'archivio è indicizzato. Serve a dirlo, non a decidere."""
        firme = self.store.firme_trascrizioni()
        stato = self.store.stato_indice(list(firme) or None)
        aggiornate = sum(
            1
            for sid, firma in firme.items()
            if sid in stato
            and stato[sid]["firma"] == firma
            and stato[sid]["modello"] == self.embedder.id
        )
        return {
            "modello": self.embedder.id,
            "call_con_parlato": len(firme),
            "call_indicizzate": aggiornate,
            "passaggi": sum(int(r["n_passaggi"]) for r in stato.values()),
        }
