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
