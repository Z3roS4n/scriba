"""Rotte del server divise per argomento.

`server.py` è cresciuto insieme al prodotto e tiene tutto in una sola funzione
fabbrica. Le parti nuove — gestione dei modelli locali, dispositivi audio,
spazio su disco, cancellazioni — vivono qui in moduli separati, con un
contesto esplicito invece della chiusura lessicale: sono le zone che cambiano
più spesso, e volerle toccare senza rileggere seicento righe è una richiesta
ragionevole.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..db.store import Store
from ..settings import Settings


@dataclass
class Contesto:
    """Ciò che le rotte possono toccare.

    Volutamente stretto: un router non deve poter avviare una registrazione o
    ricaricare il modello di trascrizione. Se serve, si passa dal server.
    """

    store: Store
    settings: Settings
    db_path: Path
    #: Pubblica un evento a tutti i client collegati. Chiamabile da ogni thread.
    publish: Callable[[dict[str, Any]], None]
    #: Stato condiviso del server (`modello`, `analisi_in_corso`, `recorder`).
    state: dict[str, Any]


# ------------------------------------------------------ stato di una sessione
#
# Il database e l'interfaccia chiamano le stesse cose con nomi diversi, e la
# traduzione sta qui perché ora la fanno in due — l'elenco in `server.py` e
# l'archivio in `clienti.py`. Duplicarla significherebbe vedere la stessa call
# in due stati diversi a seconda della schermata da cui la si guarda.

STATO_SESSIONE: dict[str, str] = {
    "recording": "recording",
    "analyzed": "analyzed",
    "error": "failed",
}

#: L'inverso, per chi filtra: quali stati grezzi stanno dietro a uno mostrato.
#: `ready` e `transcribing` finiscono entrambi in "recorded" (vedi il default di
#: `traduci_stato_sessione`), quindi filtrare per "recorded" deve prenderli
#: tutti e due.
STATI_GREZZI: dict[str, tuple[str, ...]] = {
    "recording": ("recording",),
    "recorded": ("ready", "transcribing"),
    "analyzed": ("analyzed",),
    "failed": ("error",),
}


def traduci_stato_sessione(stato_grezzo: str, *, in_analisi: bool) -> str:
    """Un valore di StatoSessione ('recording'|'recorded'|'analyzing'|'analyzed'|'failed').

    `in_analisi` viene da fuori perché il database non sa che un'analisi è in
    corso: quell'informazione vive solo nello stato del processo, non in una
    colonna. Ha la precedenza su tutto il resto: anche una call segnata come
    "analyzed" da un giro precedente sta, in questo momento, rianalizzando.
    """
    if in_analisi:
        return "analyzing"
    return STATO_SESSIONE.get(stato_grezzo, "recorded")
