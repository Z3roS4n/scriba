"""Test del server locale.

Con motore e cattura finti: qui si verifica il contratto verso l'interfaccia —
chi può parlare col core, cosa succede se si preme due volte "registra", che
gli eventi arrivino davvero al websocket.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.recorder import Recorder  # noqa: E402
from scriba_core.server import create_app  # noqa: E402
from scriba_core.stt.base import TranscriptEvent  # noqa: E402

TOKEN = "token-di-prova"


class FakeEngine:
    name = "fake"

    def transcribe(self, audio: np.ndarray, *, language: str | None = None) -> str:
        return "testo"

    def has_speech(self, audio: np.ndarray) -> bool:
        return True


class FakeCapture:
    """Finta scheda audio: non apre nessun device, ma si comporta come tale."""

    def __init__(self, clock, on_audio) -> None:
        self.clock = clock
        self.on_audio = on_audio
        self.started = False

    def start(self):
        from scriba_core.audio.capture import DeviceInfo

        self.started = True
        return {
            "mic": DeviceInfo(0, "Mic finto", 1, 16_000),
            "loopback": DeviceInfo(1, "Loopback finto", 1, 16_000),
        }

    def stop(self) -> None:
        self.started = False


@pytest.fixture()
def client(tmp_path: Path):
    def recorder_factory(engine, store, on_event):
        return Recorder(engine, store, on_event=on_event, capture_factory=FakeCapture)

    app = create_app(
        db_path=tmp_path / "server.sqlite",
        token=TOKEN,
        engine_factory=FakeEngine,
        recorder_factory=recorder_factory,
    )
    with TestClient(app) as c:
        yield c


def auth(path: str) -> str:
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}token={TOKEN}"


class TestAccesso:
    def test_health_non_richiede_token(self, client: TestClient) -> None:
        # Il processo padre deve poter sapere quando il core e' pronto, prima
        # ancora di avere qualcosa da chiedergli.
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_senza_token_si_viene_respinti(self, client: TestClient) -> None:
        assert client.get("/sessions").status_code == 422

    def test_con_token_sbagliato_si_viene_respinti(self, client: TestClient) -> None:
        assert client.get("/sessions?token=sbagliato").status_code == 401

    def test_il_websocket_rifiuta_un_token_sbagliato(self, client: TestClient) -> None:
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws?token=sbagliato") as ws:
                ws.receive_text()


class TestRegistrazione:
    def test_ciclo_completo(self, client: TestClient) -> None:
        r = client.post(auth("/session/start"), json={"titolo": "Riunione"})
        assert r.status_code == 200
        session_id = r.json()["session_id"]
        assert r.json()["devices"]["mic"] == "Mic finto"

        stato = client.get(auth("/session/state")).json()
        assert stato["in_registrazione"] is True
        assert stato["session_id"] == session_id

        assert client.post(auth("/session/stop")).json()["session_id"] == session_id
        assert client.get(auth("/session/state")).json()["in_registrazione"] is False

    def test_lo_stato_basta_a_ricostruire_la_schermata(self, client: TestClient) -> None:
        """Chi arriva a registrazione già iniziata deve poter ricostruire tutto.

        L'interfaccia imparava che si stava registrando **solo** dall'evento
        `session_started`: una finestra che non c'era quando è passato restava
        convinta che non stesse succedendo niente, mostrava «Registra» e
        premerlo era la cosa sbagliata. Adesso all'avvio chiede qui, e questa
        risposta deve bastarle: se sta registrando, quale call, e da quanto.
        """
        session_id = client.post(auth("/session/start"), json={}).json()["session_id"]

        stato = client.get(auth("/session/state")).json()
        assert stato["in_registrazione"] is True
        assert stato["session_id"] == session_id
        # Senza, il cronometro ripartirebbe da zero a ogni riapertura.
        assert isinstance(stato["now_ms"], int)

    def test_due_avvii_non_si_sovrappongono(self, client: TestClient) -> None:
        # Un doppio clic su "registra" non deve aprire due sessioni che
        # litigano per il microfono.
        client.post(auth("/session/start"), json={})
        assert client.post(auth("/session/start"), json={}).status_code == 409

    def test_stop_senza_registrazione(self, client: TestClient) -> None:
        assert client.post(auth("/session/stop")).status_code == 409

    def test_il_consenso_viene_registrato(self, client: TestClient) -> None:
        r = client.post(auth("/session/start"), json={"consenso_confermato": True})
        session_id = r.json()["session_id"]
        client.post(auth("/session/stop"))

        store = client.app.state.store
        row = store.conn.execute(
            "SELECT consenso_confermato_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        assert row["consenso_confermato_at"] is not None

    def test_senza_conferma_non_si_finge_il_consenso(self, client: TestClient) -> None:
        r = client.post(auth("/session/start"), json={"consenso_confermato": False})
        session_id = r.json()["session_id"]
        client.post(auth("/session/stop"))

        store = client.app.state.store
        row = store.conn.execute(
            "SELECT consenso_confermato_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        assert row["consenso_confermato_at"] is None


class TestScreenshot:
    def test_l_istante_lo_decide_il_core(self, client: TestClient) -> None:
        # Chi chiama non manda un timestamp: lo prende il core dalla propria
        # timeline, che e' la stessa della trascrizione.
        client.post(auth("/session/start"), json={})
        r = client.post(auth("/session/screenshot"), json={"path": "C:/shot/1.png"})
        assert r.status_code == 200
        assert "t_ms" in r.json()
        assert r.json()["t_ms"] >= 0
        client.post(auth("/session/stop"))

    def test_fuori_da_una_registrazione_viene_rifiutato(self, client: TestClient) -> None:
        r = client.post(auth("/session/screenshot"), json={"path": "C:/shot/1.png"})
        assert r.status_code == 409


class TestEventi:
    def test_gli_eventi_arrivano_al_websocket(self, client: TestClient) -> None:
        with client.websocket_connect(auth("/ws")) as ws:
            client.post(auth("/session/start"), json={"titolo": "Con websocket"})
            msg = ws.receive_json()
            assert msg["type"] == "session_started"
            assert msg["devices"]["loopback"] == "Loopback finto"

    def test_lo_screenshot_arriva_al_websocket(self, client: TestClient) -> None:
        with client.websocket_connect(auth("/ws")) as ws:
            client.post(auth("/session/start"), json={})
            ws.receive_json()  # session_started

            client.post(auth("/session/screenshot"), json={"path": "x.png"})
            msg = ws.receive_json()
            assert msg["type"] == "screenshot"
            assert msg["t_ms"] >= 0

    def test_lo_stop_viene_annunciato(self, client: TestClient) -> None:
        with client.websocket_connect(auth("/ws")) as ws:
            client.post(auth("/session/start"), json={})
            ws.receive_json()
            client.post(auth("/session/stop"))
            assert ws.receive_json()["type"] == "session_stopped"


class TestAnalisiNonBlocca:
    """L'analisi dura minuti: la richiesta non può restare aperta ad aspettarla.

    Tenendo aperta la risposta HTTP, il client la chiudeva molto prima della
    fine e l'interfaccia — che aspettava proprio quella per sapere che il lavoro
    era finito — restava ferma per sempre. Successo davvero: due ore a mostrare
    "analisi in corso" per un lavoro concluso da un pezzo.
    """

    def test_la_rotta_risponde_subito(self, client: TestClient, monkeypatch) -> None:
        import scriba_core.ai.analyze as modulo_analisi
        from scriba_core.llm.providers import LocalProvider

        # Qui si misura solo che la rotta non aspetti la fine del lavoro. Senza
        # questo, il test misurava anche se su questa macchina c'e' un
        # llama-server acceso: falliva a seconda di cosa era in esecuzione, che
        # e' il modo piu' rapido di far smettere di guardare i test rossi.
        monkeypatch.setattr(LocalProvider, "available", lambda self: True)

        partita = threading.Event()
        libera = threading.Event()

        def analisi_lenta(self, session_id):  # noqa: ANN001, ARG001
            partita.set()
            libera.wait(timeout=10)
            return modulo_analisi.Analisi()

        monkeypatch.setattr(modulo_analisi.Analizzatore, "analizza", analisi_lenta)

        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        client.app.state.store.add_segment(session_id, "mic", 0, 1000, "qualcosa", is_final=True)
        client.post(auth("/session/stop"))

        inizio = time.perf_counter()
        r = client.post(auth(f"/sessions/{session_id}/analyze"))
        durata = time.perf_counter() - inizio

        assert r.status_code == 200
        assert r.json()["stato"] == "avviata"
        assert durata < 2.0, "la rotta ha aspettato la fine dell'analisi"

        assert partita.wait(timeout=5), "il lavoro non e' partito"
        assert client.get(auth("/analisi/stato")).json()["in_corso"] is True
        libera.set()

    def test_lo_stato_si_puo_sempre_richiedere(self, client: TestClient) -> None:
        # E' la rete di sicurezza dell'interfaccia: fidarsi solo degli eventi
        # significa restare fermi per sempre quando se ne perde uno.
        assert client.get(auth("/analisi/stato")).json()["in_corso"] is False


class TestExport:
    def test_esporta_una_call(self, client: TestClient, tmp_path: Path) -> None:
        client.post(auth("/session/start"), json={"titolo": "Da esportare"})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        client.app.state.store.add_segment(
            session_id, "mic", 0, 1000, "una frase detta", is_final=True
        )
        client.post(auth("/session/stop"))

        r = client.post(
            auth(f"/sessions/{session_id}/export/markdown"),
            json={"destinazione": str(tmp_path / "export")},
        )
        assert r.status_code == 200
        percorso = Path(r.json()["percorso"])
        assert percorso.exists()
        assert "una frase detta" in percorso.read_text(encoding="utf-8")

    def test_una_sessione_inesistente_da_404(self, client: TestClient, tmp_path: Path) -> None:
        r = client.post(
            auth("/sessions/9999/export/markdown"),
            json={"destinazione": str(tmp_path)},
        )
        assert r.status_code == 404


class TestLettura:
    def test_elenco_sessioni(self, client: TestClient) -> None:
        client.post(auth("/session/start"), json={"titolo": "Prima"})
        client.post(auth("/session/stop"))
        client.post(auth("/session/start"), json={"titolo": "Seconda"})
        client.post(auth("/session/stop"))

        sessioni = client.get(auth("/sessions")).json()
        assert [s["titolo"] for s in sessioni] == ["Seconda", "Prima"]

    def test_ricerca_full_text(self, client: TestClient) -> None:
        client.post(auth("/session/start"), json={})
        store = client.app.state.store
        session_id = client.get(auth("/session/state")).json()["session_id"]
        store.add_segment(session_id, "mic", 0, 1000, "parliamo di fatturazione elettronica")
        client.post(auth("/session/stop"))

        risultati = client.get(auth("/search?q=fatturazione")).json()
        assert len(risultati) == 1
        assert "fatturazione" in risultati[0]["testo"]


class TestAnalisi:
    def test_senza_modello_raggiungibile_si_spiega_perche(self, client: TestClient) -> None:
        # Si punta a una porta dove non c'e' nessuno invece di dare per scontato
        # che il modello locale non sia in ascolto: sulla macchina di chi
        # sviluppa spesso lo e', e il test fallirebbe per il motivo sbagliato.
        client.post(auth("/settings"), json={"llm": {"base_url": "http://127.0.0.1:1"}})

        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        client.post(auth("/session/stop"))

        r = client.post(auth(f"/sessions/{session_id}/analyze"))
        assert r.status_code == 412
        assert "llama-server" in r.json()["detail"]

    def test_analisi_vuota_di_una_call_mai_analizzata(self, client: TestClient) -> None:
        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        client.post(auth("/session/stop"))

        body = client.get(auth(f"/sessions/{session_id}/analysis")).json()
        # Il confronto e' esatto di proposito: la forma di questa risposta e' il
        # contratto con l'interfaccia (ui/renderer/tipi.ts, `Analisi`), e un
        # campo che compare o sparisce senza che nessuno se ne accorga e' un
        # pannello che smette di mostrare qualcosa.
        assert body == {
            "riassunto": None,
            "punti_salienti": None,
            "riassunto_gruppi": [],
            "salienti": [],
            "tasks": [],
            "meta": None,
            "errore": None,
        }

    def test_modificare_una_task_toglie_il_da_rivedere(self, client: TestClient) -> None:
        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        store = client.app.state.store
        seg = store.add_segment(session_id, "mic", 0, 1000, "faccio io", is_final=True)
        task_id = store.add_task(
            session_id, "Una task", needs_review=True,
            evidence=[{"segment_id": seg, "supports": "titolo"}],
        )
        client.post(auth("/session/stop"))

        r = client.post(auth(f"/tasks/{task_id}"), json={"stato": "confirmed"})
        assert r.status_code == 200
        assert r.json()["stato"] == "confirmed"
        assert r.json()["needs_review"] == 0

    def test_le_evidence_accompagnano_le_task(self, client: TestClient) -> None:
        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        store = client.app.state.store
        seg = store.add_segment(session_id, "loopback", 42_000, 44_000,
                                "entro venerdi", is_final=True)
        store.add_task(session_id, "Consegnare",
                       evidence=[{"segment_id": seg, "supports": "due_date"}])
        client.post(auth("/session/stop"))

        tasks = client.get(auth(f"/sessions/{session_id}/analysis")).json()["tasks"]
        assert tasks[0]["evidence"][0]["quote"] == "entro venerdi"
        assert tasks[0]["evidence"][0]["t_ms"] == 42_000


class TestImpostazioni:
    def test_la_chiave_non_torna_indietro(self, client: TestClient) -> None:
        client.post(auth("/settings"), json={"llm": {"api_key": "segreto"}})
        body = client.get(auth("/settings")).json()
        assert "api_key" not in body["llm"]
        assert body["llm"]["api_key_presente"] is True


class TestRecorder:
    def test_lo_stop_ferma_prima_la_cattura(self, tmp_path: Path) -> None:
        """L'ordine di spegnimento non e' un dettaglio.

        Se si fermassero prima i trascrittori, la frase che l'utente stava
        pronunciando quando ha premuto stop andrebbe persa — ed e' proprio
        quella a cui teneva.
        """
        from scriba_core.db.store import Store

        ordine: list[str] = []

        class TracciaCapture(FakeCapture):
            def stop(self) -> None:
                ordine.append("capture")
                super().stop()

        store = Store(tmp_path / "ordine.sqlite")
        rec = Recorder(FakeEngine(), store, capture_factory=TracciaCapture)
        rec.start()
        for t in rec._transcribers.values():
            original = t.stop

            def stop_tracciato(*a, _o=original, **k):
                ordine.append("transcriber")
                return _o(*a, **k)

            t.stop = stop_tracciato  # type: ignore[method-assign]

        rec.stop()
        assert ordine[0] == "capture"
        assert "transcriber" in ordine

    def test_gli_eventi_finiscono_nel_database(self, tmp_path: Path) -> None:
        from scriba_core.db.store import Store

        store = Store(tmp_path / "eventi.sqlite")
        rec = Recorder(FakeEngine(), store, capture_factory=FakeCapture)
        info = rec.start()

        # Un parziale seguito dal definitivo deve aggiornare LO STESSO record,
        # altrimenti i riferimenti delle task punterebbero a segmenti morti.
        rec._handle_event(TranscriptEvent("mic", 0, 1000, "provvisorio", is_final=False))
        rec._handle_event(TranscriptEvent("mic", 0, 1200, "definitivo", is_final=True))

        segmenti = store.segments(info.session_id)
        assert len(segmenti) == 1
        assert segmenti[0].testo == "definitivo"
        assert segmenti[0].is_final
        assert segmenti[0].revision == 1
        rec.stop()
