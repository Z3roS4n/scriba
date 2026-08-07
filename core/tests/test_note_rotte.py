"""La nota di lavoro, dal database fino all'interfaccia.

`test_note_correnti.py` copre chi la scrive. Qui si copre il pezzo che
mancava del tutto: che qualcuno la **legga**. Una nota generata, salvata e mai
mostrata, dal punto di vista di chi usa l'applicazione, non è stata scritta.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.server import create_app  # noqa: E402

TOKEN = "token-di-prova"


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(db_path=tmp_path / "n.sqlite", token=TOKEN, engine_factory=lambda: None)
    with TestClient(app) as c:
        yield c


def auth(path: str) -> str:
    return f"{path}{'&' if '?' in path else '?'}token={TOKEN}"


def _nota(client: TestClient, sid: int, inizio: int, fine: int, testo: str, candidati=None) -> None:
    client.app.state.store.add_ai_output(
        sid,
        "running_note",
        testo,
        model="finto",
        provider="local",
        prompt_id="running_note",
        prompt_version="1",
        scope_start_ms=inizio,
        scope_end_ms=fine,
        content_json=json.dumps(candidati) if candidati else None,
    )


@pytest.fixture()
def sessione(client: TestClient) -> int:
    return client.app.state.store.create_session(1_785_000_000_000, titolo="Riunione")


def test_senza_note_non_e_un_errore(client: TestClient, sessione: int) -> None:
    r = client.get(auth(f"/sessions/{sessione}/note"))
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["note"] == []
    assert corpo["ultima"] is None
    # Distingue «non ancora» da «non le vuoi»: senza, l'interfaccia non sa se
    # mostrare un'attesa o niente.
    assert corpo["attive"] is False


def test_le_note_tornano_in_ordine(client: TestClient, sessione: int) -> None:
    _nota(client, sessione, 0, 600_000, "primi dieci minuti")
    _nota(client, sessione, 600_000, 1_200_000, "fino al ventesimo")
    _nota(client, sessione, 1_200_000, 1_800_000, "fino al trentesimo")

    corpo = client.get(auth(f"/sessions/{sessione}/note")).json()
    assert [n["content_md"] for n in corpo["note"]] == [
        "primi dieci minuti",
        "fino al ventesimo",
        "fino al trentesimo",
    ]


def test_l_ultima_e_quella_che_conta(client: TestClient, sessione: int) -> None:
    # Ogni nota riscrive la precedente incorporandola: è l'ultima da mostrare.
    _nota(client, sessione, 0, 600_000, "prima")
    _nota(client, sessione, 600_000, 1_200_000, "seconda, che contiene la prima")

    corpo = client.get(auth(f"/sessions/{sessione}/note")).json()
    assert corpo["ultima"]["content_md"] == "seconda, che contiene la prima"
    assert corpo["ultima"]["scope_end_ms"] == 1_200_000


def test_le_note_non_si_schiacciano_una_sull_altra(client: TestClient, sessione: int) -> None:
    # È il motivo per cui questa rotta esiste invece di passare da
    # /sessions/{id}/analysis: là le righe diventano `{kind: testo}` e le note,
    # tutte `is_current` insieme, collasserebbero in una sola.
    for i in range(4):
        _nota(client, sessione, i * 600_000, (i + 1) * 600_000, f"nota {i}")

    assert len(client.get(auth(f"/sessions/{sessione}/note")).json()["note"]) == 4
    analisi = client.get(auth(f"/sessions/{sessione}/analysis")).json()
    assert isinstance(analisi.get("running_note"), (str, type(None)))


def test_i_candidati_arrivano_gia_decodificati(client: TestClient, sessione: int) -> None:
    _nota(client, sessione, 0, 600_000, "con impegni", candidati=[{"temp_id": "nota1_f0_1"}])
    nota = client.get(auth(f"/sessions/{sessione}/note")).json()["note"][0]
    assert nota["candidati"] == [{"temp_id": "nota1_f0_1"}]
    # Il JSON grezzo non esce: chi legge non deve sapere com'è conservato.
    assert "content_json" not in nota


def test_un_json_rovinato_non_fa_fallire_la_rotta(client: TestClient, sessione: int) -> None:
    store = client.app.state.store
    _nota(client, sessione, 0, 600_000, "nota buona")
    store.conn.execute("UPDATE ai_outputs SET content_json = '{rotto'")
    store.conn.commit()

    corpo = client.get(auth(f"/sessions/{sessione}/note")).json()
    assert corpo["note"][0]["content_md"] == "nota buona"
    assert corpo["note"][0]["candidati"] == []


def test_dice_se_sono_accese(client: TestClient, sessione: int) -> None:
    client.post(auth("/settings"), json={"note_incrementali": True})
    assert client.get(auth(f"/sessions/{sessione}/note")).json()["attive"] is True
