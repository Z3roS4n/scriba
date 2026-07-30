"""Test dell'elenco dei motori di analisi.

Il punto non è elencarli: è dire quali funzionano *adesso*. Un motore locale
spento e un `claude` non installato sono voci selezionabili ma inutili, e senza
questo controllo lo si scoprirebbe solo a fine call.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.server import create_app  # noqa: E402

TOKEN = "token-di-prova"


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(db_path=tmp_path / "p.sqlite", token=TOKEN, engine_factory=lambda: None)
    with TestClient(app) as c:
        yield c


def auth(path: str) -> str:
    return f"{path}{'&' if '?' in path else '?'}token={TOKEN}"


def test_ci_sono_sia_il_locale_che_l_abbonamento(client: TestClient) -> None:
    ids = {p["id"] for p in client.get(auth("/providers")).json()}
    assert {"local", "claude-cli"} <= ids


def test_ogni_voce_dice_se_e_utilizzabile_adesso(client: TestClient) -> None:
    for p in client.get(auth("/providers")).json():
        assert isinstance(p["disponibile"], bool)


def test_uno_solo_risulta_in_uso(client: TestClient) -> None:
    assert sum(1 for p in client.get(auth("/providers")).json() if p["attivo"]) == 1


def test_cambiare_scelta_si_riflette_subito(client: TestClient) -> None:
    client.post(auth("/settings"), json={"llm": {"provider": "claude-cli", "model": "sonnet"}})
    attivo = next(p for p in client.get(auth("/providers")).json() if p["attivo"])
    assert attivo["id"] == "claude-cli"


def test_ogni_voce_spiega_cosa_comporta(client: TestClient) -> None:
    # La differenza fra le opzioni non e' tecnica ma pratica: quanto ci mette,
    # quanto costa, e se la trascrizione esce dal computer.
    for p in client.get(auth("/providers")).json():
        assert len(p["descrizione"]) > 20

    voci = {p["id"]: p["descrizione"] for p in client.get(auth("/providers")).json()}
    assert "non esce nulla" in voci["local"].lower()
    assert "anthropic" in voci["claude-cli"].lower()


def test_il_locale_spento_risulta_non_disponibile(client: TestClient) -> None:
    # Si punta a una porta dove non c'e' nessuno: sulla macchina di chi sviluppa
    # il modello locale spesso e' acceso, e il test fallirebbe per il motivo
    # sbagliato.
    client.post(auth("/settings"), json={"llm": {"base_url": "http://127.0.0.1:1"}})
    locale = next(p for p in client.get(auth("/providers")).json() if p["id"] == "local")
    assert locale["disponibile"] is False


class TestModelloLocaleInAvvio:
    """Fra «premuto avvia» e «risponde» passano decine di secondi.

    In quella finestra dire «non disponibile» è falso, e il rimedio — «scarica e
    avvia il modello locale» — è quello che l'utente ha appena fatto. È la
    issue #1.
    """

    @staticmethod
    def _spento(client: TestClient) -> None:
        client.post(auth("/settings"), json={"llm": {"base_url": "http://127.0.0.1:1"}})

    @staticmethod
    def _locale(client: TestClient) -> dict:
        return next(p for p in client.get(auth("/providers")).json() if p["id"] == "local")

    def test_mentre_carica_lo_dice_invece_di_dare_un_rimedio_inutile(
        self, client: TestClient
    ) -> None:
        self._spento(client)

        class GestoreFinto:
            def server_in_avvio(self) -> bool:
                return True

        _stato_condiviso(client)["gestore_modelli"] = GestoreFinto()

        locale = self._locale(client)
        assert locale["disponibile"] is False
        assert locale["in_avvio"] is True
        # Niente rimedio: non c'è niente da rimediare, sta arrivando.
        assert locale["rimedio"] is None

    def test_senza_nessun_server_acceso_resta_un_guasto_da_rimediare(
        self, client: TestClient
    ) -> None:
        self._spento(client)
        locale = self._locale(client)
        assert locale["in_avvio"] is False
        assert locale["rimedio"]

    def test_gli_altri_motori_non_sono_mai_in_avvio(self, client: TestClient) -> None:
        # `in_avvio` riguarda un processo che stiamo avviando noi: un'API
        # remota o non c'è o risponde.
        for p in client.get(auth("/providers")).json():
            if p["id"] != "local":
                assert p["in_avvio"] is False


def _stato_condiviso(client: TestClient) -> dict:
    """Lo `state` che `create_app` passa alle rotte.

    Non è esposto sull'app: lo si raggiunge dalla chiusura della rotta, che è
    l'unico appiglio senza cambiare la firma di `create_app` solo per il test.
    """
    for rotta in client.app.routes:
        chiusura = getattr(rotta, "endpoint", None)
        if chiusura is None or not getattr(chiusura, "__closure__", None):
            continue
        for cella in chiusura.__closure__:
            valore = cella.cell_contents
            if isinstance(valore, dict) and "analisi_in_corso" in valore:
                return valore
    raise AssertionError("stato condiviso non trovato")
