"""Connettore HTTP generico: una POST verso un endpoint configurabile, con lo
stesso JSON del formato di export (`json_export.costruisci_payload`).

Serve a chi vuole collegare Scriba a un proprio server o a un MCP senza dover
sapere niente di Notion: basta un indirizzo che accetti JSON. Nessuno stato da
ricordare fra una chiamata e l'altra — a differenza di Notion non c'è niente
da aggiornare invece di duplicare, è una singola richiesta che chi riceve
gestisce come crede.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..db.store import Store
from .json_export import costruisci_payload

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class HttpGenericoError(RuntimeError):
    """L'endpoint configurato non ha accettato l'invio."""


def invia(session_id: int, store: Store, config: dict[str, Any]) -> dict[str, Any]:
    url = (config.get("url") or "").strip()
    if not url:
        raise HttpGenericoError("Manca l'indirizzo a cui mandare l'export.")

    payload = costruisci_payload(store, session_id)

    headers = {"Content-Type": "application/json"}
    if token := config.get("token"):
        # Facoltativo: non tutti gli endpoint la richiedono, ma un MCP o un
        # server proprio spesso vuole un bearer token per non restare aperto
        # a chiunque conosca l'indirizzo.
        headers["Authorization"] = f"Bearer {token}"

    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise HttpGenericoError(f"L'endpoint non ha accettato l'invio: {exc}") from exc

    return {"url": url, "creati": len(payload["task"]), "status_code": r.status_code}
