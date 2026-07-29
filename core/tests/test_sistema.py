"""Test delle rotte di sistema: dispositivi, spazio occupato, cancellazioni.

Il filo conduttore del brief è che le cancellazioni sono irreversibili e
devono fare esattamente quello che promettono: `/dati/elimina-audio` toglie i
file audio ma lascia intatte trascrizioni, task e prove; `/sessions/{id}/
elimina` toglie tutto, file compresi, ma si rifiuta se la sessione è quella in
registrazione. I dispositivi, invece, non devono mai impedire di aprire le
impostazioni: un'enumerazione che esplode deve tornare liste vuote, non un
errore HTTP.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.recorder import Recorder  # noqa: E402
from scriba_core.server import create_app  # noqa: E402

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


# --------------------------------------------------------------- dispositivi


class TestDispositivi:
    def test_la_forma_e_quella_attesa(self, client: TestClient) -> None:
        r = client.get(auth("/dispositivi"))
        assert r.status_code == 200
        corpo = r.json()
        assert set(corpo.keys()) == {"microfoni", "loopback"}
        assert isinstance(corpo["microfoni"], list)
        assert isinstance(corpo["loopback"], list)

    def test_un_enumerazione_che_esplode_non_rompe_la_rotta(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Driver assenti, COM che esplode: con l'audio rotto l'utente deve
        # poter entrare comunque nelle impostazioni per capire cosa non va.
        import scriba_core.api.sistema as modulo

        def esplode():
            raise OSError("il servizio audio di Windows non risponde")

        monkeypatch.setattr(modulo.audio_devices, "elenco", esplode)

        r = client.get(auth("/dispositivi"))
        assert r.status_code == 200
        assert r.json() == {"microfoni": [], "loopback": []}


# --------------------------------------------------------------------- dati


class TestSpazioOccupato:
    def test_le_tre_voci_e_i_percorsi_reali(self, client: TestClient, tmp_path: Path) -> None:
        cartella_audio = tmp_path / "audio"
        cartella_audio.mkdir()
        (cartella_audio / "sessione-00001").mkdir()
        (cartella_audio / "sessione-00001" / "mic.wav").write_bytes(b"x" * 1000)

        cartella_shot = tmp_path / "screenshots"
        cartella_shot.mkdir()
        (cartella_shot / "1.png").write_bytes(b"y" * 500)

        r = client.get(auth("/dati"))
        assert r.status_code == 200
        voci = {v["chiave"]: v for v in r.json()}

        assert set(voci.keys()) == {"audio", "db", "screenshots"}
        assert voci["audio"]["bytes"] == 1000
        assert voci["audio"]["path"] == str(cartella_audio)
        assert voci["screenshots"]["bytes"] == 500
        assert voci["db"]["path"] == str(tmp_path / "server.sqlite")
        assert voci["db"]["bytes"] > 0  # lo schema e' gia' scritto nel file

    def test_cartelle_assenti_non_falliscono(self, client: TestClient) -> None:
        # Prima di qualunque registrazione le cartelle audio/screenshot non
        # esistono ancora: deve restare 0, non un errore.
        r = client.get(auth("/dati"))
        assert r.status_code == 200
        voci = {v["chiave"]: v for v in r.json()}
        assert voci["audio"]["bytes"] == 0
        assert voci["screenshots"]["bytes"] == 0


# ----------------------------------------------------------------- screenshot


class TestScreenshots:
    def test_elenco_nella_forma_di_scatto(self, client: TestClient) -> None:
        store = client.app.state.store
        session_id = store.create_session(1_700_000_000_000)
        store.add_screenshot(
            session_id, 5_000, "C:/shot/1.png", width=1920, height=1080, nota_utente="slide budget"
        )

        r = client.get(auth(f"/sessions/{session_id}/screenshots"))
        assert r.status_code == 200
        corpo = r.json()
        assert len(corpo) == 1
        voce = corpo[0]
        assert set(voce.keys()) == {"id", "t_ms", "path", "width", "height", "nota_utente"}
        assert voce["t_ms"] == 5_000
        assert voce["path"] == "C:/shot/1.png"
        assert voce["nota_utente"] == "slide budget"

    def test_sessione_senza_scatti_da_lista_vuota(self, client: TestClient) -> None:
        store = client.app.state.store
        session_id = store.create_session(1_700_000_000_000)
        assert client.get(auth(f"/sessions/{session_id}/screenshots")).json() == []


# -------------------------------------------------------------- analyze/stop


class TestInterrompiAnalisi:
    def test_senza_analisi_in_corso_da_409(self, client: TestClient) -> None:
        r = client.post(auth("/sessions/1/analyze/stop"))
        assert r.status_code == 409

    def test_su_una_sessione_diversa_da_quella_in_analisi_da_409(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scriba_core.ai.analyze as modulo_analisi
        from scriba_core.llm.providers import LocalProvider

        # Nessun llama-server gira davvero durante i test: senza questo il
        # provider locale risulterebbe indisponibile e la rotta /analyze
        # rifiuterebbe con 412 prima ancora di partire.
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

        client.post(auth(f"/sessions/{session_id}/analyze"))
        assert partita.wait(timeout=5)

        r = client.post(auth(f"/sessions/{session_id + 999}/analyze/stop"))
        assert r.status_code == 409

        libera.set()

    def test_interrompere_riporta_subito_lo_stato_a_fermo(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import scriba_core.ai.analyze as modulo_analisi
        from scriba_core.llm.providers import LocalProvider

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

        with client.websocket_connect(auth("/ws")) as ws:
            client.post(auth(f"/sessions/{session_id}/analyze"))
            assert partita.wait(timeout=5), "l'analisi non e' partita"
            ws.receive_json()  # evento "in_corso"

            r = client.post(auth(f"/sessions/{session_id}/analyze/stop"))
            assert r.status_code == 200
            assert r.json()["session_id"] == session_id

            evento = ws.receive_json()
            assert evento["type"] == "analisi"
            assert evento["stato"] == "errore"
            assert evento["session_id"] == session_id

        # L'interfaccia non deve restare a mostrare "in corso" per sempre.
        stato = client.get(auth("/analisi/stato")).json()
        assert stato["in_corso"] is False

        analisi = client.get(auth(f"/sessions/{session_id}/analysis")).json()
        assert analisi["errore"] is not None

        sessioni = {s["id"]: s for s in client.get(auth("/sessions")).json()}
        assert sessioni[session_id]["stato"] == "failed"

        libera.set()


# ---------------------------------------------------------------- elimina-audio


class TestEliminaAudio:
    def test_toglie_i_file_ma_non_task_e_prove(self, client: TestClient, tmp_path: Path) -> None:
        store = client.app.state.store
        session_id = store.create_session(1_700_000_000_000)

        mic_path = tmp_path / "mic.wav"
        loop_path = tmp_path / "loopback.wav"
        mic_path.write_bytes(b"audio finto")
        loop_path.write_bytes(b"audio finto")
        store.set_audio_paths(session_id, str(mic_path), str(loop_path))

        seg_id = store.add_segment(session_id, "mic", 0, 1000, "portiamo i mockup", is_final=True)
        task_id = store.add_task(
            session_id,
            "Portare i mockup",
            evidence=[{"segment_id": seg_id, "supports": "esistenza"}],
        )

        r = client.post(auth("/dati/elimina-audio"))
        assert r.status_code == 200
        assert r.json()["eliminati"] == 2

        assert not mic_path.exists()
        assert not loop_path.exists()

        riga = store.conn.execute(
            "SELECT audio_mic_path, audio_loop_path FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        assert riga["audio_mic_path"] is None
        assert riga["audio_loop_path"] is None

        # Le task e le loro prove restano: puntano a un segmento di
        # trascrizione, non a un file audio.
        prove = store.task_evidence(task_id)
        assert len(prove) == 1
        assert prove[0]["segment_id"] == seg_id
        tasks = client.get(auth(f"/sessions/{session_id}/analysis")).json()["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["evidence"][0]["segment_id"] == seg_id

    def test_senza_audio_da_cancellare_non_fallisce(self, client: TestClient) -> None:
        r = client.post(auth("/dati/elimina-audio"))
        assert r.status_code == 200
        assert r.json()["eliminati"] == 0


# --------------------------------------------------------- elimina sessione


class TestEliminaSessione:
    def test_toglie_tutto_file_compresi(self, client: TestClient, tmp_path: Path) -> None:
        store = client.app.state.store
        session_id = store.create_session(1_700_000_000_000)

        mic_path = tmp_path / "mic.wav"
        mic_path.write_bytes(b"audio finto")
        store.set_audio_paths(session_id, str(mic_path), None)

        shot_path = tmp_path / "shot.png"
        shot_path.write_bytes(b"immagine finta")
        store.add_screenshot(session_id, 1_000, str(shot_path))

        seg_id = store.add_segment(session_id, "mic", 0, 1000, "qualcosa", is_final=True)
        store.add_task(
            session_id, "Una task",
            evidence=[{"segment_id": seg_id, "supports": "esistenza"}],
        )

        r = client.post(auth(f"/sessions/{session_id}/elimina"))
        assert r.status_code == 200

        assert not mic_path.exists()
        assert not shot_path.exists()
        assert store.conn.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone() is None

    def test_una_sessione_inesistente_da_404(self, client: TestClient) -> None:
        r = client.post(auth("/sessions/999999/elimina"))
        assert r.status_code == 404

    def test_rifiuta_la_sessione_che_si_sta_registrando(self, client: TestClient) -> None:
        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]

        r = client.post(auth(f"/sessions/{session_id}/elimina"))
        assert r.status_code == 409

        # Non deve aver toccato nulla: la sessione e' ancora li'.
        stato = client.get(auth("/session/state")).json()
        assert stato["in_registrazione"] is True

        client.post(auth("/session/stop"))
        assert client.post(auth(f"/sessions/{session_id}/elimina")).status_code == 200

    def test_eliminare_una_sessione_diversa_da_quella_in_registrazione_e_permesso(
        self, client: TestClient
    ) -> None:
        store = client.app.state.store
        altra_sessione = store.create_session(1_700_000_000_000)

        client.post(auth("/session/start"), json={})

        r = client.post(auth(f"/sessions/{altra_sessione}/elimina"))
        assert r.status_code == 200

        client.post(auth("/session/stop"))
