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
