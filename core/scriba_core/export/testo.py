"""Esporta una call in testo semplice: la trascrizione leggibile, coi minuti.

Chi sceglie questo formato la vuole incollare altrove — un verbale, una chat,
un'altra applicazione — non rileggerla dentro Scriba. Per questo non c'è
struttura a sezioni né sintassi da formattare: solo un'intestazione essenziale
e le battute in ordine, una per riga, col minuto davanti a ciascuna così da
poter sempre risalire a quando è stata detta.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..db.store import Store
from ._util import mmss, nome_file


def esporta(store: Store, session_id: int, destinazione: Path | str) -> Path:
    """Scrive il file e restituisce il percorso."""
    sessione = store.conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if sessione is None:
        raise ValueError(f"Sessione {session_id} inesistente.")

    quando = datetime.fromtimestamp(sessione["started_at"] / 1000)
    destinazione = Path(destinazione)
    if destinazione.suffix.lower() != ".txt":
        destinazione.mkdir(parents=True, exist_ok=True)
        destinazione = destinazione / nome_file(sessione["titolo"], quando, session_id, "txt")
    destinazione.parent.mkdir(parents=True, exist_ok=True)

    righe: list[str] = []
    a = righe.append

    a(sessione["titolo"] or f"Call #{session_id}")
    durata = f" - {mmss(sessione['durata_ms'])}" if sessione["durata_ms"] else ""
    piattaforma = f" - {sessione['piattaforma']}" if sessione["piattaforma"] else ""
    a(f"{quando:%d/%m/%Y %H:%M}{durata}{piattaforma}")
    a("")

    for seg in store.segments(session_id, only_final=True):
        chi = "Io" if seg.source == "mic" else "Altri"
        a(f"[{mmss(seg.t_start_ms)}] {chi}: {seg.testo}")

    destinazione.write_text("\n".join(righe), encoding="utf-8")
    return destinazione
