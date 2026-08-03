"""Punto d'ingresso dell'export: sceglie formato e destinazione e gira al
modulo giusto.

La firma è quella fissata in `.claude/project/contratto-moduli.md` (sezione
Export) — non cambia, perché altri moduli ci chiamano contro di essa senza
aspettarsi a vicenda. `formato` e `destinazione` accettano `None` in più
rispetto a come li mostra il contratto solo per poter essere omessi da chi
chiama (l'API, quando l'utente non ha scelto niente per quella singola
esportazione): passarli esplicitamente si comporta esattamente come prima.

`export.cartella`/`export.formato` sono le due chiavi di `contratto-moduli.md`
che questo file deve leggere. Non arrivano già caricate — chi chiama passa
solo `store` — quindi si rilegge `settings.json` da sé, dallo stesso percorso
che usa il server per costruirlo (accanto al database).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..db.store import Store
from ..settings import Settings
from . import contesto, json_export, markdown, testo

_ESPORTATORI = {
    "markdown": markdown.esporta,
    "testo": testo.esporta,
    "json": json_export.esporta,
    # Per un modello linguistico: le citazioni accanto a cio' che sostengono,
    # invece di id da incrociare. Qui c'e' la variante a una call sola; per
    # esportarne piu' d'una insieme c'e' `POST /export/contesto`.
    "contesto": contesto.esporta_sessione,
}


def _impostazioni_export(store: Store) -> dict[str, Any]:
    percorso_settings = Path(store.path).with_name("settings.json")
    return Settings(percorso_settings).tutto().get("export") or {}


def esporta(
    session_id: int,
    store: Store,
    *,
    formato: str | None = None,
    destinazione: Path | str | None = None,
) -> Path:
    if formato is None or destinazione is None:
        impostazioni = _impostazioni_export(store)
    else:
        impostazioni = {}

    formato = formato or impostazioni.get("formato") or "markdown"
    esportatore = _ESPORTATORI.get(formato)
    if esportatore is None:
        raise ValueError(f"Formato di export sconosciuto: {formato}")

    if destinazione is None:
        # None = accanto al database, com'era già il comportamento di
        # /export/markdown quando non gli si passava una destinazione.
        destinazione = impostazioni.get("cartella") or Path(store.path).parent / "export"

    return esportatore(store, session_id, destinazione)
