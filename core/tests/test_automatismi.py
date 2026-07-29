"""Test degli automatismi di `server.py`.

Quattro cose che erano scritte nelle impostazioni ma non succedevano davvero:
l'analisi che parte da sola a fine call, il rispetto delle sue eccezioni (motore
irraggiungibile, analisi già in corso, nessuna trascrizione), le note correnti
che seguono `note_incrementali`, e il minuto che non deve più comparire due
volte nel riassunto. Ogni pezzo qui verifica uno di questi, non il
funzionamento interno di `Analizzatore` o di `GestoreNote`, che hanno già i
propri test.
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

import scriba_core.server as server_mod  # noqa: E402
from scriba_core.recorder import Recorder  # noqa: E402
from scriba_core.server import (  # noqa: E402
    _riassunto_a_gruppi,
    _salienti_da_markdown,
    create_app,
)

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


def auth(path: str) -> str:
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}token={TOKEN}"


def _aspetta(condizione, timeout: float = 3.0) -> bool:
    """Polling con timeout: gli automatismi girano in un task a parte, non
    nella richiesta HTTP che li osserva, quindi non c'è un istante preciso in
    cui interrogarli — solo una finestra entro cui devono essersi mossi."""
    scadenza = time.time() + timeout
    while time.time() < scadenza:
        if condizione():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture()
def client(tmp_path: Path):
    def recorder_factory(engine, store, on_event):
        return Recorder(engine, store, on_event=on_event, capture_factory=FakeCapture)

    app = create_app(
        db_path=tmp_path / "automatismi.sqlite",
        token=TOKEN,
        engine_factory=FakeEngine,
        recorder_factory=recorder_factory,
    )
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------- analisi automatica


class TestAnalisiAutomatica:
    def test_parte_da_sola_a_fine_call(self, client: TestClient, monkeypatch) -> None:
        import scriba_core.ai.analyze as modulo_analisi
        from scriba_core.llm.providers import LocalProvider

        # Il ritardo prima dei controlli serve solo a lasciare la precedenza a
        # una richiesta esplicita nel frattempo (vedi RITARDO_ANALISI_AUTOMATICA_S):
        # qui non c'è nessuna richiesta esplicita in corsa, e aspettare due
        # secondi veri per ogni test sarebbe solo tempo perso.
        monkeypatch.setattr(server_mod, "RITARDO_ANALISI_AUTOMATICA_S", 0.0)
        monkeypatch.setattr(LocalProvider, "available", lambda self: True)
        monkeypatch.setattr(
            modulo_analisi.Analizzatore,
            "analizza",
            lambda self, session_id: modulo_analisi.Analisi(riassunto="fatta da sola"),
        )

        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        client.app.state.store.add_segment(
            session_id, "mic", 0, 1000, "qualcosa da analizzare", is_final=True
        )
        client.post(auth("/session/stop"))

        # Nessuno ha chiamato /analyze: se compare un risultato, è partita da sola.
        def _pronta() -> bool:
            corpo = client.get(auth(f"/sessions/{session_id}/analysis")).json()
            return corpo["meta"] is not None

        assert _aspetta(_pronta), "l'analisi automatica non è mai partita"
        corpo = client.get(auth(f"/sessions/{session_id}/analysis")).json()
        # Il mock sostituisce `analizza` di netto e non scrive in `ai_outputs`
        # (lo fa `Analizzatore` per davvero, testato altrove): qui la prova che
        # è partita da sola è `meta`, valorizzato solo a lavoro finito.
        assert corpo["errore"] is None
        assert corpo["meta"]["provider"] == "local"

    def test_non_parte_se_la_chiave_e_spenta(self, client: TestClient, monkeypatch) -> None:
        from scriba_core.llm.providers import LocalProvider

        monkeypatch.setattr(server_mod, "RITARDO_ANALISI_AUTOMATICA_S", 0.0)
        monkeypatch.setattr(LocalProvider, "available", lambda self: True)
        client.post(auth("/settings"), json={"analisi_automatica": False})

        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        client.app.state.store.add_segment(session_id, "mic", 0, 1000, "qualcosa", is_final=True)
        client.post(auth("/session/stop"))

        time.sleep(0.3)
        corpo = client.get(auth(f"/sessions/{session_id}/analysis")).json()
        assert corpo["meta"] is None

    def test_motore_irraggiungibile_non_marca_la_call_come_fallita(
        self, client: TestClient, monkeypatch
    ) -> None:
        # Nessun mock su LocalProvider.available: si punta a una porta dove non
        # c'è nessuno, così il motore è per davvero irraggiungibile, non solo
        # nella finzione del test.
        monkeypatch.setattr(server_mod, "RITARDO_ANALISI_AUTOMATICA_S", 0.0)
        client.post(auth("/settings"), json={"llm": {"base_url": "http://127.0.0.1:1"}})

        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        client.app.state.store.add_segment(session_id, "mic", 0, 1000, "qualcosa", is_final=True)
        client.post(auth("/session/stop"))

        # Tempo perché il task automatico provi e rinunci: non c'è un evento da
        # aspettare per un tentativo che non parte nemmeno, quindi si aspetta e
        # basta invece di interrogare una condizione che non cambierà mai.
        time.sleep(0.3)

        assert client.get(auth("/analisi/stato")).json()["in_corso"] is False
        sessioni = {s["id"]: s for s in client.get(auth("/sessions")).json()}
        # Non "failed": una call registrata bene non deve sembrare rotta per
        # un'analisi che nessuno ha chiesto esplicitamente.
        assert sessioni[session_id]["stato"] != "failed"

        corpo = client.get(auth(f"/sessions/{session_id}/analysis")).json()
        assert corpo["errore"] is None
        assert corpo["meta"] is None

    def test_senza_trascrizione_non_si_analizza(self, client: TestClient, monkeypatch) -> None:
        from scriba_core.llm.providers import LocalProvider

        monkeypatch.setattr(server_mod, "RITARDO_ANALISI_AUTOMATICA_S", 0.0)
        monkeypatch.setattr(LocalProvider, "available", lambda self: True)

        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        # Nessun segmento aggiunto: la call finisce senza una parola trascritta.
        client.post(auth("/session/stop"))

        time.sleep(0.3)
        corpo = client.get(auth(f"/sessions/{session_id}/analysis")).json()
        assert corpo["meta"] is None
        assert corpo["errore"] is None

    def test_non_si_accavalla_a_una_gia_in_corso(self, client: TestClient, monkeypatch) -> None:
        import scriba_core.ai.analyze as modulo_analisi
        from scriba_core.llm.providers import LocalProvider

        monkeypatch.setattr(server_mod, "RITARDO_ANALISI_AUTOMATICA_S", 0.0)
        monkeypatch.setattr(LocalProvider, "available", lambda self: True)

        partita = threading.Event()
        libera = threading.Event()

        def analisi_lenta(self, session_id):  # noqa: ANN001, ARG001
            partita.set()
            libera.wait(timeout=10)
            return modulo_analisi.Analisi()

        monkeypatch.setattr(modulo_analisi.Analizzatore, "analizza", analisi_lenta)

        # Prima call: la si lascia analizzare da sola e la si tiene occupata,
        # bloccata dentro `libera.wait`.
        client.post(auth("/session/start"), json={})
        prima_id = client.get(auth("/session/state")).json()["session_id"]
        client.app.state.store.add_segment(prima_id, "mic", 0, 1000, "prima", is_final=True)
        client.post(auth("/session/stop"))

        assert _aspetta(partita.is_set), "la prima analisi automatica non è mai partita"
        assert client.get(auth("/analisi/stato")).json()["session_id"] == prima_id
        partita.clear()

        # Seconda call: finisce mentre la prima è ancora occupata. L'automatismo
        # deve accorgersi che lo stato è già occupato e rinunciare in silenzio,
        # non accodare un secondo lavoro sopra al primo.
        client.post(auth("/session/start"), json={})
        seconda_id = client.get(auth("/session/state")).json()["session_id"]
        client.app.state.store.add_segment(seconda_id, "mic", 0, 1000, "seconda", is_final=True)
        client.post(auth("/session/stop"))

        time.sleep(0.3)
        assert not partita.is_set(), "una seconda analisi è partita sopra a una già in corso"
        assert client.get(auth("/analisi/stato")).json()["session_id"] == prima_id

        libera.set()
        assert _aspetta(lambda: client.get(auth("/analisi/stato")).json()["in_corso"] is False)

        # La seconda non è mai stata presa in carico da sola: resta "registrata",
        # pronta per essere chiesta esplicitamente quando lo stato si libera.
        corpo = client.get(auth(f"/sessions/{seconda_id}/analysis")).json()
        assert corpo["meta"] is None


# ------------------------------------------------------------- note correnti


class FakeGestoreNote:
    """Sostituisce `ai.note_correnti.GestoreNote`: qui si verifica solo il
    cablaggio in `server.py` — quando chiama `avvia`/`ferma` — non cosa fa
    davvero una nota, che ha i suoi test in `test_note_correnti.py`."""

    ultima_istanza: "FakeGestoreNote | None" = None

    def __init__(self, store, settings, publish) -> None:
        self.store = store
        self.settings = settings
        self.publish = publish
        self.sessioni_avviate: list[int] = []
        self.numero_ferma = 0
        self._attivo = False
        FakeGestoreNote.ultima_istanza = self

    def avvia(self, session_id: int) -> None:
        self.sessioni_avviate.append(session_id)
        self._attivo = True

    def ferma(self) -> None:
        self.numero_ferma += 1
        self._attivo = False

    @property
    def attivo(self) -> bool:
        return self._attivo


@pytest.fixture()
def client_note(tmp_path: Path, monkeypatch):
    FakeGestoreNote.ultima_istanza = None
    monkeypatch.setattr(server_mod, "GestoreNote", FakeGestoreNote)

    def recorder_factory(engine, store, on_event):
        return Recorder(engine, store, on_event=on_event, capture_factory=FakeCapture)

    app = create_app(
        db_path=tmp_path / "note.sqlite",
        token=TOKEN,
        engine_factory=FakeEngine,
        recorder_factory=recorder_factory,
    )
    with TestClient(app) as c:
        yield c


class TestNoteCorrenti:
    def test_si_avviano_solo_con_la_chiave_accesa(self, client_note: TestClient) -> None:
        client_note.post(auth("/settings"), json={"note_incrementali": True})

        client_note.post(auth("/session/start"), json={})
        session_id = client_note.get(auth("/session/state")).json()["session_id"]

        fake = FakeGestoreNote.ultima_istanza
        assert fake is not None
        assert fake.sessioni_avviate == [session_id]
        assert fake.attivo is True

        client_note.post(auth("/session/stop"))
        assert fake.numero_ferma == 1
        assert fake.attivo is False

    def test_non_si_avviano_con_la_chiave_spenta(self, client_note: TestClient) -> None:
        # note_incrementali è False di default: nessuna modifica alle impostazioni.
        client_note.post(auth("/session/start"), json={})

        fake = FakeGestoreNote.ultima_istanza
        assert fake is not None
        assert fake.sessioni_avviate == []
        assert fake.attivo is False

        client_note.post(auth("/session/stop"))
        # `ferma()` è sicura anche se `avvia()` non è mai partita: server.py la
        # chiama comunque a ogni fine registrazione, per contratto.
        assert fake.numero_ferma == 1


# --------------------------------------------------- il minuto non si ripete


class TestRiassuntoSenzaMinutoDuplicato:
    def test_il_marcatore_finale_viene_tolto_dal_testo(self) -> None:
        testo = "## Sezione\n- Abbiamo parlato con soggetti terzi [03:45].\n"
        gruppi = _riassunto_a_gruppi(testo)
        assert len(gruppi) == 1
        voce = gruppi[0]["voci"][0]
        assert voce["t_ms"] == (3 * 60 + 45) * 1000
        assert voce["testo"] == "Abbiamo parlato con soggetti terzi."
        assert "[03:45]" not in voce["testo"]
        assert "03:45" not in voce["testo"]

    def test_il_marcatore_in_testa_viene_tolto_senza_lasciare_lo_spazio(self) -> None:
        testo = "## Sezione\n- [03:45] Abbiamo iniziato la call.\n"
        gruppi = _riassunto_a_gruppi(testo)
        voce = gruppi[0]["voci"][0]
        assert voce["testo"] == "Abbiamo iniziato la call."

    def test_una_riga_di_solo_marcatore_viene_scartata(self) -> None:
        testo = "## Sezione\n- Testo buono\n- [03:45]\n"
        gruppi = _riassunto_a_gruppi(testo)
        assert len(gruppi[0]["voci"]) == 1
        assert gruppi[0]["voci"][0]["testo"] == "Testo buono"

    def test_senza_marcatore_il_testo_non_si_tocca(self) -> None:
        testo = "## Sezione\n- Una voce senza orario.\n"
        gruppi = _riassunto_a_gruppi(testo)
        voce = gruppi[0]["voci"][0]
        assert voce["testo"] == "Una voce senza orario."
        assert voce["t_ms"] is None


class TestSalientiSenzaMinutoDuplicato:
    def test_il_corpo_non_ripete_il_marcatore_iniziale(self) -> None:
        testo = "[03:45] **Rischio** — [03:45] soggetti terzi coinvolti"
        punti = _salienti_da_markdown(testo)
        assert punti[0]["corpo"] == "soggetti terzi coinvolti"

    def test_il_corpo_normale_non_viene_toccato(self) -> None:
        testo = "[03:45] **Rischio** — soggetti terzi coinvolti"
        punti = _salienti_da_markdown(testo)
        assert punti[0]["corpo"] == "soggetti terzi coinvolti"


class TestRichiestaSullaStessaCallInCorso:
    """Chiedere l'analisi di una call che si sta già analizzando non è un errore.

    A fine registrazione l'analisi parte da sola. Chi preme «Rianalizza» un
    attimo dopo vuole esattamente quello che sta già succedendo: rifiutarlo
    gli mostrerebbe un guasto inesistente, e l'interfaccia a quel punto
    smetterebbe anche di aspettare il risultato che sta per arrivare.
    """

    def test_la_stessa_call_risponde_gia_avviata(self, client: TestClient, monkeypatch) -> None:
        import scriba_core.ai.analyze as modulo_analisi
        from scriba_core.llm.providers import LocalProvider

        monkeypatch.setattr(server_mod, "RITARDO_ANALISI_AUTOMATICA_S", 0.0)
        monkeypatch.setattr(LocalProvider, "available", lambda self: True)

        libera = threading.Event()

        def analisi_lenta(self, session_id):  # noqa: ANN001, ARG001
            libera.wait(timeout=10)
            return modulo_analisi.Analisi()

        monkeypatch.setattr(modulo_analisi.Analizzatore, "analizza", analisi_lenta)

        client.post(auth("/session/start"), json={})
        session_id = client.get(auth("/session/state")).json()["session_id"]
        client.app.state.store.add_segment(session_id, "mic", 0, 1000, "testo", is_final=True)
        client.post(auth(f"/sessions/{session_id}/analyze"))
        assert _aspetta(lambda: client.get(auth("/analisi/stato")).json()["in_corso"])

        r = client.post(auth(f"/sessions/{session_id}/analyze"))
        assert r.status_code == 200
        assert r.json()["stato"] == "già_avviata"
        libera.set()

    def test_un_altra_call_viene_ancora_rifiutata(self, client: TestClient, monkeypatch) -> None:
        import scriba_core.ai.analyze as modulo_analisi
        from scriba_core.llm.providers import LocalProvider

        monkeypatch.setattr(server_mod, "RITARDO_ANALISI_AUTOMATICA_S", 0.0)
        monkeypatch.setattr(LocalProvider, "available", lambda self: True)

        libera = threading.Event()

        def analisi_lenta(self, session_id):  # noqa: ANN001, ARG001
            libera.wait(timeout=10)
            return modulo_analisi.Analisi()

        monkeypatch.setattr(modulo_analisi.Analizzatore, "analizza", analisi_lenta)

        client.post(auth("/session/start"), json={})
        prima = client.get(auth("/session/state")).json()["session_id"]
        client.app.state.store.add_segment(prima, "mic", 0, 1000, "testo", is_final=True)
        client.post(auth("/session/stop"))
        client.post(auth(f"/sessions/{prima}/analyze"))
        assert _aspetta(lambda: client.get(auth("/analisi/stato")).json()["in_corso"])

        # Una call diversa non c'entra niente con quella in corso: il rifiuto
        # resta, altrimenti si perderebbe la richiesta senza dirlo a nessuno.
        r = client.post(auth(f"/sessions/{prima + 999}/analyze"))
        assert r.status_code == 409
        libera.set()


class TestSessioniAppese:
    """Una sessione lasciata 'recording' da un core morto male non resta tale.

    Senza questo, l'elenco mostra per sempre una call in corso che non esiste,
    e la trascrizione che l'utente aspetta non arriverà mai.
    """

    def test_allavvio_la_sessione_appesa_viene_richiusa(self, tmp_path: Path) -> None:
        from scriba_core.db.store import Store

        db = tmp_path / "appese.sqlite"
        store = Store(db)
        session_id = store.create_session(1_000_000, titolo="interrotta")
        store.add_segment(session_id, "mic", 0, 12_000, "qualcosa", is_final=True)
        riga = store.conn.execute(
            "SELECT stato, ended_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        assert riga["stato"] == "recording" and riga["ended_at"] is None

        # È quello che fa create_app all'avvio.
        assert store.chiudi_sessioni_appese() == [session_id]

        riga = store.conn.execute(
            "SELECT stato, ended_at, durata_ms FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        assert riga["stato"] == "ready"
        assert riga["ended_at"] is not None
        # La durata viene dall'ultimo segmento, non dall'ora del riavvio: fra il
        # guasto e il riavvio possono passare giorni.
        assert riga["durata_ms"] == 12_000

    def test_senza_segmenti_la_durata_e_zero_invece_che_inventata(self, tmp_path: Path) -> None:
        from scriba_core.db.store import Store

        store = Store(tmp_path / "vuota.sqlite")
        session_id = store.create_session(1_000_000, titolo="persa")
        store.chiudi_sessioni_appese()

        riga = store.conn.execute(
            "SELECT durata_ms, stato FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        assert riga["durata_ms"] == 0
        assert riga["stato"] == "ready"

    def test_una_sessione_gia_chiusa_non_viene_toccata(self, tmp_path: Path) -> None:
        from scriba_core.db.store import Store

        store = Store(tmp_path / "chiusa.sqlite")
        session_id = store.create_session(1_000_000, titolo="regolare")
        store.add_segment(session_id, "mic", 0, 5_000, "detto", is_final=True)
        store.end_session(session_id, 1_009_999)
        store.set_session_state(session_id, "analyzed")

        assert store.chiudi_sessioni_appese() == []
        riga = store.conn.execute(
            "SELECT stato, ended_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        assert riga["stato"] == "analyzed"
        assert riga["ended_at"] == 1_009_999
