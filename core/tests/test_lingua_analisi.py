"""L'analisi esce nella lingua della call, non in quella di chi ha scritto i prompt.

Il difetto #61: `SYSTEM_ESTRAZIONE` diceva «trascrizioni di riunioni di lavoro in
italiano» e `SYSTEM_REDAZIONE` diceva «Scrivi in italiano», sempre. Una call in
inglese usciva riassunta in italiano, e al modello veniva affermata una cosa
falsa sulla trascrizione che stava leggendo.

Qui non si giudica la qualità di quello che il modello scrive — quella dipende
dal modello. Si controlla che **gli si chieda la lingua giusta**, che è l'unica
parte di cui questo codice risponde.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.ai import lingue  # noqa: E402
from scriba_core.ai.analyze import Analizzatore  # noqa: E402
from scriba_core.db.store import Segment, Store  # noqa: E402
from scriba_core.llm.base import Completion  # noqa: E402

TOKEN = "token-di-prova"


class MotoreFinto:
    name = "finto"

    def transcribe(self, audio: np.ndarray, *, language: str | None = None) -> str:
        return "testo"

    def has_speech(self, audio: np.ndarray) -> bool:
        return False


class CatturaFinta:
    """Nessun device vero: la lingua non dipende dalla scheda audio."""

    def __init__(self, clock, on_audio) -> None:
        self.clock, self.on_audio = clock, on_audio

    def start(self):
        from scriba_core.audio.capture import DeviceInfo

        return {
            "mic": DeviceInfo(0, "Mic finto", 1, 16_000),
            "loopback": DeviceInfo(1, "Loopback finto", 1, 16_000),
        }

    def stop(self) -> None:
        pass


class ProviderCheAnnota:
    """Non risponde: registra cosa gli è stato chiesto."""

    def __init__(self) -> None:
        self.chiamate: list[dict] = []

    def complete(self, *, system, user, schema=None, max_tokens=2048) -> Completion:
        self.chiamate.append({"system": system, "user": user})
        return Completion(text="", data={"candidati": [], "tasks": []}, model="finto", provider="finto")


def segmento(id: int, testo: str) -> Segment:
    return Segment(
        id=id,
        session_id=1,
        source="mic",
        t_start_ms=id * 1000,
        t_end_ms=id * 1000 + 900,
        testo=testo,
        is_final=True,
        revision=0,
    )


@pytest.fixture()
def pezzi(tmp_path: Path):
    store = Store(tmp_path / "prova.sqlite")
    provider = ProviderCheAnnota()
    return Analizzatore(provider, store), provider, store


class TestLaLinguaArrivaAlModello:
    def test_una_call_inglese_chiede_di_scrivere_in_inglese(self, pezzi) -> None:
        analizzatore, provider, _ = pezzi
        analizzatore.riassumi([segmento(1, "we should ship on friday")], lingua="en")
        sistema = provider.chiamate[-1]["system"]
        assert "in inglese" in sistema
        assert "in italiano" not in sistema

    def test_i_titoli_del_riassunto_seguono_la_lingua(self, pezzi) -> None:
        # Sono le uniche parole del prompt che finiscono sotto gli occhi di chi
        # legge: un riassunto inglese con "## In breve" sopra è mezzo tradotto.
        analizzatore, provider, _ = pezzi
        analizzatore.riassumi([segmento(1, "we should ship on friday")], lingua="en")
        testo = provider.chiamate[-1]["user"]
        assert "## In short" in testo
        assert "## In breve" not in testo

    def test_l_estrazione_non_dichiara_una_lingua_sbagliata(self, pezzi) -> None:
        analizzatore, provider, _ = pezzi
        analizzatore.candidati([segmento(1, "Marc takes the mockups")], lingua="en")
        sistema = provider.chiamate[-1]["system"]
        assert "riunioni di lavoro in inglese" in sistema

    def test_senza_lingua_resta_l_italiano(self, pezzi) -> None:
        # Il comportamento di sempre per chi non ha mai toccato l'impostazione.
        analizzatore, provider, _ = pezzi
        analizzatore.riassumi([segmento(1, "il preventivo")])
        assert "in italiano" in provider.chiamate[-1]["system"]


class TestDallaSessione:
    def test_analizza_legge_la_lingua_della_call(self, pezzi) -> None:
        # È il collegamento che mancava: il dato c'era in tabella e non lo
        # leggeva nessuno.
        analizzatore, provider, store = pezzi
        sid = store.create_session(0, titolo="Sprint review", lingua="en")
        store.add_segment(sid, "mic", 0, 2_000, "we should ship on friday", is_final=True)
        analizzatore.analizza(sid)
        assert provider.chiamate, "l'analisi non ha chiesto niente al modello"
        assert all("in inglese" in c["system"] for c in provider.chiamate)


class TestLaLinguaScelta:
    """Quella in Impostazioni deve arrivare nella call, non fermarsi lì.

    Era il difetto sotto il difetto: `stt.lingua` la leggeva solo la rifinitura.
    La registrazione partiva sempre con "it", quindi `sessions.lingua` diceva
    "italiano" su ogni call e ogni correzione a valle sarebbe stata inerte.
    """

    def test_la_registrazione_parte_nella_lingua_delle_impostazioni(
        self, tmp_path: Path
    ) -> None:
        import sqlite3

        from fastapi.testclient import TestClient

        from scriba_core.recorder import Recorder
        from scriba_core.server import create_app

        db = tmp_path / "server.sqlite"
        app = create_app(
            db_path=db,
            token=TOKEN,
            engine_factory=MotoreFinto,
            recorder_factory=lambda engine, store, on_event: Recorder(
                engine, store, on_event=on_event, capture_factory=CatturaFinta
            ),
        )

        with TestClient(app) as client:
            client.post(f"/settings?token={TOKEN}", json={"stt": {"lingua": "en"}})
            avvio = client.post(f"/session/start?token={TOKEN}", json={"titolo": "Sprint"})
            assert avvio.status_code == 200
            session_id = avvio.json()["session_id"]
            client.post(f"/session/stop?token={TOKEN}")

        conn = sqlite3.connect(db)
        (lingua,) = conn.execute(
            "SELECT lingua FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        conn.close()
        assert lingua == "en"


class TestNormalizzazione:
    def test_le_forme_regionali_valgono(self) -> None:
        # `en-GB` è inglese. Rifiutarlo vorrebbe dire far uscire in italiano una
        # call che la sua lingua l'aveva dichiarata.
        assert lingue.nome("en-GB") == "inglese"
        assert lingue.nome("pt_BR") == "portoghese"

    def test_una_lingua_che_non_conosciamo_ripiega(self) -> None:
        assert lingue.nome("zz") == "italiano"
        assert lingue.nome(None) == "italiano"

    def test_ogni_lingua_ha_i_suoi_titoli(self) -> None:
        # Una lingua elencata senza titoli manderebbe in errore il riassunto
        # solo per quella, e solo quando qualcuno la sceglie.
        for codice in lingue.NOMI:
            assert len(lingue.titoli_riassunto(codice)) == 5
            assert all(t.strip() for t in lingue.titoli_riassunto(codice))
