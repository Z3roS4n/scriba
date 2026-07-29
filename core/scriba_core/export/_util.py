"""Pezzi comuni ai formati di export: minuti, nome del file.

`markdown.py` non li importa da qui — è il modello di qualità di questo
modulo e non si tocca per non rischiare di regredirlo — quindi la stessa
manciata di righe è duplicata lì. Gli altri formati (testo, JSON) e i
connettori la condividono da qui invece di riscriverla ciascuno per conto suo.
"""

from __future__ import annotations

import re
from datetime import datetime

PRIORITA_SIMBOLO = {"critica": "!!!", "alta": "!!", "media": "!", "bassa": ""}


def mmss(ms: int) -> str:
    minuti, secondi = divmod(max(0, ms) // 1000, 60)
    return f"{minuti:02d}:{secondi:02d}"


def nome_file(titolo: str | None, quando: datetime, session_id: int, estensione: str) -> str:
    base = titolo or f"call-{session_id}"
    # Si tiene solo ciò che è sicuro in un nome di file su qualunque sistema.
    pulito = re.sub(r"[^\w\s-]", "", base, flags=re.UNICODE).strip()
    pulito = re.sub(r"[\s_]+", "-", pulito).lower()[:60] or f"call-{session_id}"
    return f"{quando:%Y-%m-%d}.{pulito}.{estensione}"
