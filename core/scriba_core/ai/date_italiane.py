"""Risolve le date dette a voce in una riunione.

"entro il quattordici", "venerdì prossimo", "fine mese": in una call le scadenze
si dicono così, quasi mai in formato calendario.

Questo lavoro non si chiede al modello. Tradurre "il quattordici" nella data
giusta è aritmetica sul calendario, e un modello da 12 miliardi di parametri la
sbaglia in modi silenziosi — nella prova su una riunione finta ha lasciato il
campo vuoto pur avendo capito benissimo la frase. Il codice, invece, o la
risolve o dice che non ci riesce.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

GIORNI = {
    "lunedi": 0, "martedi": 1, "mercoledi": 2, "giovedi": 3,
    "venerdi": 4, "sabato": 5, "domenica": 6,
}

MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

NUMERI = {
    "uno": 1, "primo": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6,
    "sette": 7, "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12,
    "tredici": 13, "quattordici": 14, "quindici": 15, "sedici": 16, "diciassette": 17,
    "diciotto": 18, "diciannove": 19, "venti": 20, "ventuno": 21, "ventidue": 22,
    "ventitre": 23, "ventiquattro": 24, "venticinque": 25, "ventisei": 26,
    "ventisette": 27, "ventotto": 28, "ventinove": 29, "trenta": 30, "trentuno": 31,
}


def _normalizza(testo: str) -> str:
    """Toglie accenti e maiuscole: 'Venerdì' e 'venerdi' devono coincidere."""
    senza_accenti = unicodedata.normalize("NFD", testo.lower())
    return "".join(c for c in senza_accenti if unicodedata.category(c) != "Mn")


def _fine_mese(riferimento: date) -> date:
    if riferimento.month == 12:
        return date(riferimento.year, 12, 31)
    return date(riferimento.year, riferimento.month + 1, 1) - timedelta(days=1)


def _giorno_del_mese(giorno: int, riferimento: date) -> date | None:
    """Interpreta 'il quattordici' come la prossima occorrenza di quel giorno.

    Se il giorno è già passato nel mese in corso, si intende il mese successivo:
    in una riunione nessuno fissa una scadenza nel passato.
    """
    try:
        candidata = riferimento.replace(day=giorno)
    except ValueError:
        return None
    if candidata >= riferimento:
        return candidata

    mese, anno = riferimento.month + 1, riferimento.year
    if mese > 12:
        mese, anno = 1, anno + 1
    try:
        return date(anno, mese, giorno)
    except ValueError:
        return None


def risolvi(espressione: str | None, riferimento: date) -> date | None:
    """Traduce un'espressione in una data, o restituisce None se è ambigua.

    Restituire None non è una sconfitta: significa che l'utente dovrà
    confermare, il che è meglio di una data inventata messa in un calendario.
    """
    if not espressione:
        return None

    testo = _normalizza(espressione)

    # Data già scritta per esteso: 14/08/2026, 14-08, 14 agosto
    if m := re.search(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b", testo):
        giorno, mese = int(m.group(1)), int(m.group(2))
        anno = int(m.group(3) or riferimento.year)
        if anno < 100:
            anno += 2000
        try:
            return date(anno, mese, giorno)
        except ValueError:
            return None

    if m := re.search(r"\b(\d{1,2})\s+(" + "|".join(MESI) + r")\b", testo):
        try:
            return date(riferimento.year, MESI[m.group(2)], int(m.group(1)))
        except ValueError:
            return None

    if "dopodomani" in testo:
        return riferimento + timedelta(days=2)
    if "domani" in testo:
        return riferimento + timedelta(days=1)
    if "oggi" in testo or "in giornata" in testo:
        return riferimento

    prossimo = "prossim" in testo or "venturo" in testo

    if "fine mese" in testo or "fine del mese" in testo:
        return _fine_mese(riferimento)
    if "fine settimana" in testo:
        return riferimento + timedelta(days=(4 - riferimento.weekday()) % 7)
    if "settimana prossima" in testo or "prossima settimana" in testo:
        return riferimento + timedelta(days=7 - riferimento.weekday())

    # Giorno della settimana: "entro venerdì", "venerdì prossimo"
    for nome, indice in GIORNI.items():
        if re.search(rf"\b{nome}\b", testo):
            avanti = (indice - riferimento.weekday()) % 7
            if avanti == 0:
                avanti = 7  # "venerdì" detto di venerdì significa il prossimo
            if prossimo and avanti < 7:
                avanti += 7 if indice <= riferimento.weekday() else 0
            return riferimento + timedelta(days=avanti)

    # Giorno del mese, in cifre o in lettere: "entro il 14", "entro il quattordici"
    if m := re.search(r"\b(?:il|entro il|per il)\s+(\d{1,2})\b", testo):
        return _giorno_del_mese(int(m.group(1)), riferimento)

    for parola, valore in NUMERI.items():
        if re.search(rf"\b(?:il|entro il|per il)\s+{parola}\b", testo):
            return _giorno_del_mese(valore, riferimento)

    return None
