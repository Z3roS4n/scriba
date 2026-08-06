"""Le rotte della rifinitura, viste dall'interfaccia.

`test_rifinitura.py` copre il lavoro vero. Qui si verifica ciò che la logica da
sola non dice: che una richiesta impossibile venga rifiutata con un motivo
utile invece che con un errore generico, e che lo stato sia interrogabile —
un'interfaccia che si fida solo degli eventi resta ferma per sempre quando ne
perde uno.
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
    app = create_app(db_path=tmp_path / "r.sqlite", token=TOKEN, engine_factory=lambda: None)
    with TestClient(app) as c:
        yield c


def auth(path: str) -> str:
    return f"{path}{'&' if '?' in path else '?'}token={TOKEN}"


def _call_con_trascrizione(client: TestClient) -> int:
    store = client.app.state.store
    sid = store.create_session(1_785_000_000_000, titolo="Riunione")
    store.add_segment(sid, "mic", 0, 2_000, "una frase qualunque", is_final=True)
    return sid


def test_stato_a_riposo(client: TestClient) -> None:
    r = client.get(auth("/rifinitura/stato"))
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["in_corso"] is False
    assert corpo["session_id"] is None
    # Dice anche se il modello c'è: senza, l'interfaccia dovrebbe provare a
    # farla partire per scoprire che non si può.
    assert "modello_pronto" in corpo
    # L'evento di annullamento è un oggetto Python: non deve uscire da qui.
    assert "annulla" not in corpo


def test_sessione_inesistente(client: TestClient) -> None:
    assert client.post(auth("/sessions/999/rifinisci")).status_code == 404


def test_senza_trascrizione_non_si_rifinisce(client: TestClient) -> None:
    store = client.app.state.store
    sid = store.create_session(1_785_000_000_000, titolo="Vuota")
    r = client.post(auth(f"/sessions/{sid}/rifinisci"))
    assert r.status_code == 412
    assert "trascrizione" in r.json()["detail"]


def test_senza_il_modello_lo_dice_e_spiega_dove_prenderlo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scriba_core.api.rifinitura as mod

    monkeypatch.setattr(mod, "modello_gestito_installato", lambda _: False)
    sid = _call_con_trascrizione(client)
    r = client.post(auth(f"/sessions/{sid}/rifinisci"))
    assert r.status_code == 412
    # Il rimedio dev'essere nel messaggio: «non si può» senza «ecco come» è
    # un vicolo cieco.
    assert "Modelli locali" in r.json()["detail"]


def test_interrompere_quando_non_c_e_niente_non_e_un_errore(client: TestClient) -> None:
    r = client.post(auth("/rifinitura/interrompi"))
    assert r.status_code == 200
    assert r.json()["stato"] == "ferma"


def test_una_seconda_richiesta_sulla_stessa_call_e_soddisfatta(client: TestClient) -> None:
    # Sta già succedendo quello che si sta chiedendo: rispondere 409 mostrerebbe
    # un errore per un lavoro in corso, e l'interfaccia smetterebbe di aspettarlo.
    sid = _call_con_trascrizione(client)
    _stato_condiviso(client).update({"in_corso": True, "session_id": sid})
    r = client.post(auth(f"/sessions/{sid}/rifinisci"))
    assert r.status_code == 200
    assert r.json()["stato"] == "già_avviata"


def test_su_un_altra_call_invece_rifiuta(client: TestClient) -> None:
    sid = _call_con_trascrizione(client)
    interno = _stato_condiviso(client)
    interno.update({"in_corso": True, "session_id": sid + 100})
    r = client.post(auth(f"/sessions/{sid}/rifinisci"))
    assert r.status_code == 409


def _stato_condiviso(client: TestClient) -> dict:
    """Lo stato che la rotta legge davvero, non una copia."""
    return client.app.state.stato_server["rifinitura"]
