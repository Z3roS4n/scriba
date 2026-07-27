"""Test della risoluzione delle date dette a voce.

Riferimento fisso: lunedì 27 luglio 2026.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.ai.date_italiane import risolvi  # noqa: E402

LUNEDI = date(2026, 7, 27)


@pytest.mark.parametrize(
    ("detto", "atteso"),
    [
        # Il caso preso da una riunione vera.
        ("entro il quattordici", date(2026, 8, 14)),
        ("entro il 14", date(2026, 8, 14)),
        # Un giorno non ancora passato resta nel mese in corso.
        ("entro il trenta", date(2026, 7, 30)),
        ("oggi", LUNEDI),
        ("domani", date(2026, 7, 28)),
        ("dopodomani", date(2026, 7, 29)),
        ("entro venerdi", date(2026, 7, 31)),
        ("entro venerdì", date(2026, 7, 31)),
        ("venerdì prossimo", date(2026, 7, 31)),
        ("fine mese", date(2026, 7, 31)),
        ("entro fine settimana", date(2026, 7, 31)),
        ("la settimana prossima", date(2026, 8, 3)),
        ("14/08/2026", date(2026, 8, 14)),
        ("14-08", date(2026, 8, 14)),
        ("14 agosto", date(2026, 8, 14)),
    ],
)
def test_espressioni_comuni(detto: str, atteso: date) -> None:
    assert risolvi(detto, LUNEDI) == atteso


@pytest.mark.parametrize("detto", ["", None, "appena possibile", "quando puoi", "piu' avanti"])
def test_cio_che_e_ambiguo_resta_ambiguo(detto: str | None) -> None:
    # Restituire None non e' una sconfitta: significa che l'utente confermera',
    # il che e' meglio di una data inventata finita in un calendario.
    assert risolvi(detto, LUNEDI) is None


def test_una_data_impossibile_non_viene_forzata() -> None:
    assert risolvi("il 31 febbraio", LUNEDI) is None
    assert risolvi("32/13/2026", LUNEDI) is None


def test_lo_stesso_giorno_della_settimana_significa_il_prossimo() -> None:
    # "ci vediamo lunedì" detto di lunedì non significa oggi.
    assert risolvi("entro lunedi", LUNEDI) == date(2026, 8, 3)


def test_a_dicembre_il_mese_dopo_e_gennaio() -> None:
    assert risolvi("entro il 5", date(2026, 12, 20)) == date(2027, 1, 5)


def test_fine_mese_a_dicembre() -> None:
    assert risolvi("fine mese", date(2026, 12, 10)) == date(2026, 12, 31)


def test_gli_accenti_non_contano() -> None:
    assert risolvi("MERCOLEDÌ", LUNEDI) == risolvi("mercoledi", LUNEDI)
