"""Test del rilevamento delle call.

La logica sta tutta nelle regole anti-falso-positivo: qui si verificano quelle,
con l'enumerazione audio sostituita. Il giro vero contro Windows si prova con
`spikes/prova_rilevamento.py`, che richiede di entrare davvero in una riunione.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.detect import call as rilevamento  # noqa: E402
from scriba_core.detect.call import PIATTAFORME, Call, RilevatoreCall  # noqa: E402


@pytest.fixture()
def finto_ambiente(monkeypatch):
    """Controlla cosa 'sta usando il microfono' e cosa 'sta riproducendo'."""
    stato = {"microfono": [], "riproduce": set()}
    monkeypatch.setattr(rilevamento, "in_ascolto", lambda: stato["microfono"])
    monkeypatch.setattr(rilevamento, "sta_riproducendo", lambda pid: pid in stato["riproduce"])
    return stato


def attendi(condizione, timeout: float = 3.0) -> bool:
    scadenza = time.time() + timeout
    while time.time() < scadenza:
        if condizione():
            return True
        time.sleep(0.02)
    return False


class TestRegole:
    def test_una_call_viene_segnalata(self, finto_ambiente) -> None:
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.05)
        r.start()
        try:
            assert attendi(lambda: viste)
        finally:
            r.stop()

        assert viste[0].piattaforma == "Zoom"
        assert viste[0].pid == 100

    def test_il_microfono_da_solo_non_basta(self, finto_ambiente) -> None:
        # Dettatura, messaggio vocale, prova audio: il microfono si accende
        # spesso senza che ci sia una riunione.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = set()

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.05)
        r.start()
        try:
            time.sleep(0.3)
        finally:
            r.stop()
        assert viste == []

    def test_una_situazione_lampo_non_conta(self, finto_ambiente) -> None:
        # La schermata di prova audio prima di entrare accende tutto per un
        # attimo: senza attesa si verrebbe interrotti ogni volta.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=30.0)
        r.start()
        try:
            time.sleep(0.2)
        finally:
            r.stop()
        assert viste == []

    def test_si_avvisa_una_volta_sola(self, finto_ambiente) -> None:
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: viste)
            time.sleep(0.3)
        finally:
            r.stop()
        assert len(viste) == 1

    def test_finita_una_call_la_successiva_viene_segnalata(self, finto_ambiente) -> None:
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: len(viste) == 1)
            finto_ambiente["microfono"] = []          # riunione finita
            finto_ambiente["riproduce"] = set()
            time.sleep(0.1)
            finto_ambiente["microfono"] = [(100, "zoom.exe")]  # riunione nuova
            finto_ambiente["riproduce"] = {100}
            assert attendi(lambda: len(viste) == 2)
        finally:
            r.stop()

    def test_dimentica_fa_riproporre(self, finto_ambiente) -> None:
        # Se l'utente ha detto di no e poi cambia idea, deve poter essere
        # richiesto di nuovo senza uscire dalla riunione.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: len(viste) == 1)
            r.dimentica(100)
            assert attendi(lambda: len(viste) == 2)
        finally:
            r.stop()

    def test_un_applicazione_sconosciuta_viene_comunque_rilevata(self, finto_ambiente) -> None:
        # Il rilevamento non dipende da un elenco di nomi: quello serve solo a
        # dire all'utente cosa si e' riconosciuto.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(7, "riunioni-del-futuro.exe")]
        finto_ambiente["riproduce"] = {7}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: viste)
        finally:
            r.stop()
        assert viste[0].piattaforma == "riunioni-del-futuro"


class TestNomi:
    def test_il_browser_si_annuncia_in_modo_comprensibile(self) -> None:
        c = Call(pid=1, processo="chrome.exe", piattaforma="browser", dal_ms=0)
        assert c.nome == "una riunione nel browser"

    def test_le_piattaforme_note_usano_il_proprio_nome(self) -> None:
        c = Call(pid=1, processo="zoom.exe", piattaforma="Zoom", dal_ms=0)
        assert c.nome == "Zoom"

    def test_teams_e_riconosciuto(self) -> None:
        assert PIATTAFORME["ms-teams.exe"] == "Teams"

    def test_scriba_non_rileva_se_stesso(self) -> None:
        assert "python.exe" in rilevamento.IGNORATE
