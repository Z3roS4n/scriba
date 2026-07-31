"""Test delle rotte di clienti e archivio, viste dall'interfaccia.

`test_clienti.py` copre la logica; qui si verifica quello che la logica da sola
non dice: che l'archivio parli la stessa lingua dell'elenco delle call, e che un
errore prevedibile torni come errore invece che come lista vuota.
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
    app = create_app(db_path=tmp_path / "c.sqlite", token=TOKEN, engine_factory=lambda: None)
    with TestClient(app) as c:
        yield c


def auth(path: str) -> str:
    return f"{path}{'&' if '?' in path else '?'}token={TOKEN}"


def _cliente(client: TestClient, nome: str) -> int:
    r = client.post(auth("/clienti"), json={"nome": nome})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _call(client: TestClient, titolo: str) -> int:
    store = client.app.state.store
    return store.create_session(1_785_000_000_000, titolo=titolo)


def test_elenco_vuoto_all_inizio(client: TestClient) -> None:
    assert client.get(auth("/clienti")).json() == []


def test_crea_ed_elenca(client: TestClient) -> None:
    _cliente(client, "Acme")
    elenco = client.get(auth("/clienti")).json()
    assert [c["nome"] for c in elenco] == ["Acme"]
    assert elenco[0]["n_call"] == 0


def test_nome_vuoto_e_un_errore_non_un_cliente_senza_nome(client: TestClient) -> None:
    r = client.post(auth("/clienti"), json={"nome": "  "})
    assert r.status_code == 400


def test_assegna_a_una_call(client: TestClient) -> None:
    cid = _cliente(client, "Acme")
    sid = _call(client, "Allineamento")

    r = client.patch(auth(f"/sessions/{sid}/cliente"), json={"client_id": cid})
    assert r.status_code == 200

    # Il cliente si vede anche nell'elenco laterale, non solo nell'archivio:
    # sono la stessa call guardata da due posti.
    sessioni = client.get(auth("/sessions")).json()
    assert sessioni[0]["cliente"] == "Acme"


def test_assegnare_un_cliente_inesistente_e_404(client: TestClient) -> None:
    sid = _call(client, "Allineamento")
    r = client.patch(auth(f"/sessions/{sid}/cliente"), json={"client_id": 999})
    assert r.status_code == 404


def test_eliminare_un_cliente_lascia_la_call(client: TestClient) -> None:
    cid = _cliente(client, "Acme")
    sid = _call(client, "Allineamento")
    client.patch(auth(f"/sessions/{sid}/cliente"), json={"client_id": cid})

    assert client.post(auth(f"/clienti/{cid}/elimina")).status_code == 200

    archivio = client.get(auth("/archivio")).json()
    assert [c["titolo"] for c in archivio] == ["Allineamento"]
    assert archivio[0]["cliente"] is None


def test_l_archivio_traduce_lo_stato_come_l_elenco(client: TestClient) -> None:
    """La stessa call non deve risultare in due stati diversi secondo la schermata."""
    sid = _call(client, "Allineamento")
    client.app.state.store.set_session_state(sid, "ready")

    stato_elenco = client.get(auth("/sessions")).json()[0]["stato"]
    stato_archivio = client.get(auth("/archivio")).json()[0]["stato"]
    assert stato_elenco == stato_archivio == "recorded"


def test_filtro_per_stato_mostrato(client: TestClient) -> None:
    a = _call(client, "Pronta")
    b = _call(client, "Fallita")
    client.app.state.store.set_session_state(a, "ready")
    client.app.state.store.set_session_state(b, "error")

    trovate = client.get(auth("/archivio?stato=failed")).json()
    assert [c["titolo"] for c in trovate] == ["Fallita"]


def test_stato_sconosciuto_e_un_errore(client: TestClient) -> None:
    """Meglio dirlo che restituire zero call e lasciar credere che non ce ne siano."""
    assert client.get(auth("/archivio?stato=inventato")).status_code == 400


def test_importa_csv(client: TestClient) -> None:
    r = client.post(auth("/clienti/importa"), json={"csv": "nome,note\nAcme,x\nGlobex,\n"})
    assert r.status_code == 200
    assert r.json() == {"creati": 2, "gia_presenti": 0, "scartati": 0}
    assert len(client.get(auth("/clienti")).json()) == 2


def test_importare_due_volte_non_duplica(client: TestClient) -> None:
    contenuto = "nome\nAcme\nGlobex\n"
    client.post(auth("/clienti/importa"), json={"csv": contenuto})
    r = client.post(auth("/clienti/importa"), json={"csv": contenuto})
    assert r.json() == {"creati": 0, "gia_presenti": 2, "scartati": 0}
    assert len(client.get(auth("/clienti")).json()) == 2


def test_importare_un_file_senza_nomi_e_un_errore(client: TestClient) -> None:
    r = client.post(auth("/clienti/importa"), json={"csv": "\n\n"})
    assert r.status_code == 400
