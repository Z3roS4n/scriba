"""Test delle note incrementali durante la call.

Con un modello finto, come in `test_analyze.py`: qui non si giudica quanto sia
brava una nota, si verifica che il ciclo attorno al modello si comporti come
deve — che parta da sola, che non accodi un secondo giro sopra uno ancora
aperto, che `ferma()` sia sempre sicura, e che un modello che fallisce non si
porti dietro la registrazione.

Gli intervalli usati qui sono di pochi centesimi di secondo, non i dieci
minuti veri: `GestoreNote` legge l'intervallo dalle impostazioni a ogni giro,
quindi basta una `FakeSettings` con un valore piccolo per esercitare lo stesso
codice in tempo di test.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.ai.note_correnti import GestoreNote  # noqa: E402
from scriba_core.api import Contesto  # noqa: E402
from scriba_core.api.note import crea_router  # noqa: E402
from scriba_core.db.store import Store  # noqa: E402
from scriba_core.llm.base import Completion  # noqa: E402


class FakeSettings:
    """Sostituisce `Settings`: espone solo `llm()` e `tutto()`, come serve a GestoreNote."""

    def __init__(self, *, intervallo_s: float = 0.03, llm: dict | None = None) -> None:
        self._intervallo_s = intervallo_s
        self._llm = llm or {"provider": "local", "base_url": "http://127.0.0.1:1", "model": "finto"}

    def llm(self) -> dict:
        return dict(self._llm)

    def tutto(self, *, con_segreti: bool = False) -> dict[str, Any]:
        return {"note_incrementali_intervallo_s": self._intervallo_s}


class FakeProvider:
    """Restituisce le risposte date, in ordine. Uguale a quella di test_analyze.py."""

    name = "fake"
    model = "fake-1"

    def __init__(self, risposte: list[dict | str]) -> None:
        self.risposte = list(risposte)
        self.chiamate: list[Any] = []

    def available(self) -> bool:
        return True

    def complete(self, *, system, user, schema=None, max_tokens=2048, temperature=0.2):
        self.chiamate.append((system, schema))
        r = self.risposte.pop(0) if self.risposte else ""
        if isinstance(r, dict):
            return Completion(text="", data=r, model=self.model, provider=self.name,
                              tokens_in=10, tokens_out=5, cost_usd=0.0)
        return Completion(text=r, model=self.model, provider=self.name,
                          tokens_in=10, tokens_out=5, cost_usd=0.0)


class FakeProviderBloccante:
    """Come FakeProvider, ma la prima chiamata resta ferma finché non la si sblocca.

    Serve a simulare una nota ancora in corso di generazione quando scatta il
    giro successivo: senza un modo per tenere occupato il thread di lavoro a
    piacere, non c'è modo di osservare lo "skip" da un test.
    """

    name = "fake"
    model = "fake-1"

    def __init__(self, sblocco: threading.Event, risposte: list[dict | str]) -> None:
        self.sblocco = sblocco
        self.risposte = list(risposte)
        self.chiamate = 0

    def available(self) -> bool:
        return True

    def complete(self, *, system, user, schema=None, max_tokens=2048, temperature=0.2):
        self.chiamate += 1
        if self.chiamate == 1:
            assert self.sblocco.wait(timeout=5.0), "il test non ha sbloccato la chiamata in tempo"
        r = self.risposte.pop(0) if self.risposte else ""
        if isinstance(r, dict):
            return Completion(text="", data=r, model=self.model, provider=self.name)
        return Completion(text=r, model=self.model, provider=self.name)


class FakeProviderConErroreIniziale:
    """Fallisce al primo tentativo, poi risponde normalmente."""

    name = "fake"
    model = "fake-1"

    def __init__(self, risposte_dopo_errore: list[dict | str]) -> None:
        self.risposte = list(risposte_dopo_errore)
        self.tentativi = 0

    def available(self) -> bool:
        return True

    def complete(self, *, system, user, schema=None, max_tokens=2048, temperature=0.2):
        self.tentativi += 1
        if self.tentativi == 1:
            raise RuntimeError("il modello locale non risponde")
        r = self.risposte.pop(0) if self.risposte else ""
        if isinstance(r, dict):
            return Completion(text="", data=r, model=self.model, provider=self.name)
        return Completion(text=r, model=self.model, provider=self.name)


def attendi(condizione, *, timeout: float = 2.0, passo: float = 0.01) -> None:
    """Aspetta che `condizione()` diventi vera, senza un timeout fisso indovinato a caso."""
    scadenza = time.monotonic() + timeout
    while time.monotonic() < scadenza:
        if condizione():
            return
        time.sleep(passo)
    assert condizione(), f"condizione non raggiunta entro {timeout}s"


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "note.sqlite")


def _con_segmenti(store: Store, *, n: int = 3) -> int:
    """Una sessione con qualche segmento finale breve, pronta per una nota."""
    session_id = store.create_session(0)
    for i in range(n):
        store.add_segment(
            session_id, "mic", i * 1000, i * 1000 + 900, f"si parla della task {i}", is_final=True
        )
    return session_id


class TestAvvioAlloScadereDellIntervallo:
    def test_la_nota_parte_da_sola_allo_scadere(
        self, store: Store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session_id = _con_segmenti(store)
        provider = FakeProvider(["nota aggiornata", {"candidati": []}])
        monkeypatch.setattr(
            "scriba_core.ai.note_correnti.costruisci", lambda _config: provider
        )

        eventi: list[dict] = []
        gestore = GestoreNote(store, FakeSettings(intervallo_s=0.03), eventi.append)
        assert gestore.attivo is False

        gestore.avvia(session_id)
        assert gestore.attivo is True
        attendi(lambda: any(e["stato"] == "fatta" for e in eventi))
        gestore.ferma()

        stati = [e["stato"] for e in eventi]
        assert stati == ["in_corso", "fatta"]
        finale = eventi[-1]
        assert finale["session_id"] == session_id
        assert finale["testo"] == "nota aggiornata"
        assert finale["t_ms"] == 2900  # fine dell'ultimo segmento finale

        riga = store.conn.execute(
            "SELECT content_md, kind, is_current FROM ai_outputs WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        assert riga["kind"] == "running_note"
        assert riga["content_md"] == "nota aggiornata"
        assert riga["is_current"] == 1

    def test_senza_segmenti_nuovi_non_genera_nulla(
        self, store: Store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Sessione creata ma nessun segmento finale: non c'e' niente da
        # riassumere, e disturbare il modello per niente e' proprio quello che
        # non deve succedere.
        session_id = store.create_session(0)
        provider = FakeProvider(["non dovrebbe mai essere usata"])
        monkeypatch.setattr(
            "scriba_core.ai.note_correnti.costruisci", lambda _config: provider
        )

        eventi: list[dict] = []
        gestore = GestoreNote(store, FakeSettings(intervallo_s=0.02), eventi.append)
        gestore.avvia(session_id)
        time.sleep(0.15)  # lascia passare piu' di un giro
        gestore.ferma()

        assert eventi == []
        assert provider.chiamate == []


class TestGiroSaltatoSeOccupato:
    def test_non_si_accoda_un_secondo_giro_sopra_uno_in_corso(
        self, store: Store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session_id = _con_segmenti(store)
        sblocco = threading.Event()
        provider = FakeProviderBloccante(sblocco, ["nota aggiornata", {"candidati": []}])
        monkeypatch.setattr(
            "scriba_core.ai.note_correnti.costruisci", lambda _config: provider
        )

        eventi: list[dict] = []
        # Intervallo molto piccolo: in condizioni normali scatterebbero diversi
        # giri mentre il primo e' bloccato. Nessuno di questi deve produrre un
        # secondo evento "in_corso".
        gestore = GestoreNote(store, FakeSettings(intervallo_s=0.02), eventi.append)
        gestore.avvia(session_id)

        attendi(lambda: any(e["stato"] == "in_corso" for e in eventi))
        # Il primo giro e' ora bloccato dentro provider.complete(). Si lascia
        # passare il tempo di diversi intervalli: senza lo skip, ognuno
        # avrebbe tentato di partire.
        time.sleep(0.02 * 6)
        in_corso = [e for e in eventi if e["stato"] == "in_corso"]
        assert len(in_corso) == 1, "un secondo giro e' partito sopra a uno gia' in corso"

        sblocco.set()  # lascia finire il giro bloccato
        attendi(lambda: any(e["stato"] == "fatta" for e in eventi))
        gestore.ferma()

        # Una sola nota scritta, non una per ogni intervallo saltato.
        n_righe = store.conn.execute(
            "SELECT COUNT(*) c FROM ai_outputs WHERE session_id = ? AND kind = 'running_note'",
            (session_id,),
        ).fetchone()["c"]
        assert n_righe == 1


class TestFermaSicura:
    def test_ferma_senza_essere_mai_partita(self, store: Store) -> None:
        gestore = GestoreNote(store, FakeSettings(), lambda _payload: None)
        gestore.ferma()  # non deve sollevare nulla
        assert gestore.attivo is False

    def test_ferma_due_volte_di_fila(self, store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
        session_id = _con_segmenti(store)
        provider = FakeProvider(["nota", {"candidati": []}])
        monkeypatch.setattr(
            "scriba_core.ai.note_correnti.costruisci", lambda _config: provider
        )

        gestore = GestoreNote(store, FakeSettings(intervallo_s=1.0), lambda _payload: None)
        gestore.avvia(session_id)
        gestore.ferma()
        assert gestore.attivo is False
        gestore.ferma()  # di nuovo: deve restare sicura
        assert gestore.attivo is False

    def test_ferma_con_una_nota_a_meta(self, store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
        # ferma() non aspetta che una generazione gia' partita finisca: deve
        # solo restare sicura mentre quella e' ancora in corso.
        session_id = _con_segmenti(store)
        sblocco = threading.Event()
        provider = FakeProviderBloccante(sblocco, ["nota", {"candidati": []}])
        monkeypatch.setattr(
            "scriba_core.ai.note_correnti.costruisci", lambda _config: provider
        )

        eventi: list[dict] = []
        gestore = GestoreNote(store, FakeSettings(intervallo_s=0.02), eventi.append)
        gestore.avvia(session_id)
        attendi(lambda: any(e["stato"] == "in_corso" for e in eventi))

        gestore.ferma()  # la nota e' ancora bloccata dentro provider.complete()
        assert gestore.attivo is False

        sblocco.set()  # si lascia comunque finire il worker, per non lasciare il thread appeso
        attendi(lambda: any(e["stato"] == "fatta" for e in eventi))


class TestErroreDelModello:
    def test_un_errore_non_ferma_la_generazione_successiva(
        self, store: Store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session_id = _con_segmenti(store)
        provider = FakeProviderConErroreIniziale(["nota dopo l'errore", {"candidati": []}])
        monkeypatch.setattr(
            "scriba_core.ai.note_correnti.costruisci", lambda _config: provider
        )

        eventi: list[dict] = []
        gestore = GestoreNote(store, FakeSettings(intervallo_s=0.03), eventi.append)
        gestore.avvia(session_id)

        attendi(lambda: any(e["stato"] == "errore" for e in eventi))
        errore = next(e for e in eventi if e["stato"] == "errore")
        assert errore["session_id"] == session_id
        assert "dettaglio" in errore and errore["dettaglio"]

        # Il gestore resta attivo: l'errore non ha fermato nulla, il giro
        # successivo riprova sulla stessa finestra (il cursore non e' avanzato).
        assert gestore.attivo is True
        attendi(lambda: any(e["stato"] == "fatta" for e in eventi), timeout=3.0)
        gestore.ferma()

        fatta = next(e for e in eventi if e["stato"] == "fatta")
        assert fatta["testo"] == "nota dopo l'errore"
        assert store.conn.execute(
            "SELECT COUNT(*) c FROM ai_outputs WHERE session_id = ? AND kind = 'running_note'",
            (session_id,),
        ).fetchone()["c"] == 1


class TestCandidatiParziali:
    def test_i_candidati_hanno_la_stessa_forma_dell_analisi_finale(
        self, store: Store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Stessi campi prodotti da Analizzatore.candidati: e' quello che li
        # rende riutilizzabili da un passaggio finale, invece di un formato a
        # se stante.
        session_id = _con_segmenti(store)
        provider = FakeProvider([
            "nota con un impegno accennato",
            {"candidati": [
                {"temp_id": "c1", "titolo": "Preparare i mockup", "confidence": 0.7,
                 "righe_titolo": [1], "righe_assignee": [], "righe_scadenza": [],
                 "righe_priorita": []},
            ]},
        ])
        monkeypatch.setattr(
            "scriba_core.ai.note_correnti.costruisci", lambda _config: provider
        )

        eventi: list[dict] = []
        gestore = GestoreNote(store, FakeSettings(intervallo_s=0.02), eventi.append)
        gestore.avvia(session_id)
        attendi(lambda: any(e["stato"] == "fatta" for e in eventi))
        gestore.ferma()

        riga = store.conn.execute(
            "SELECT content_json FROM ai_outputs WHERE session_id = ? AND kind = 'running_note'",
            (session_id,),
        ).fetchone()
        candidati = json.loads(riga["content_json"])
        assert len(candidati) == 1
        assert candidati[0]["titolo"] == "Preparare i mockup"
        # Il temp_id resta riconoscibile ma diventa unico anche fra note diverse.
        assert candidati[0]["temp_id"].startswith("nota1_")

    def test_un_errore_nell_estrazione_non_butta_via_la_nota_gia_buona(
        self, store: Store, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session_id = _con_segmenti(store)

        class ProviderNotaOkEstrazioneKo:
            name = "fake"
            model = "fake-1"

            def __init__(self) -> None:
                self.chiamate = 0

            def available(self) -> bool:
                return True

            def complete(self, *, system, user, schema=None, max_tokens=2048, temperature=0.2):
                self.chiamate += 1
                if schema is not None:
                    # E' la chiamata di estrazione candidati: fallisce.
                    raise RuntimeError("estrazione non disponibile")
                return Completion(text="nota comunque buona", model=self.model, provider=self.name)

        provider = ProviderNotaOkEstrazioneKo()
        monkeypatch.setattr(
            "scriba_core.ai.note_correnti.costruisci", lambda _config: provider
        )

        eventi: list[dict] = []
        gestore = GestoreNote(store, FakeSettings(intervallo_s=0.02), eventi.append)
        gestore.avvia(session_id)
        attendi(lambda: any(e["stato"] == "fatta" for e in eventi))
        gestore.ferma()

        assert not any(e["stato"] == "errore" for e in eventi)
        riga = store.conn.execute(
            "SELECT content_md, content_json FROM ai_outputs WHERE session_id = ? AND kind = 'running_note'",
            (session_id,),
        ).fetchone()
        assert riga["content_md"] == "nota comunque buona"
        assert riga["content_json"] is None


class TestRotta:
    """`GET /sessions/{id}/note`: sola lettura di quanto gia' scritto."""

    def _client(self, store: Store, tmp_path: Path) -> TestClient:
        ctx = Contesto(
            store=store,
            settings=FakeSettings(),
            db_path=tmp_path / "db.sqlite",
            publish=lambda _payload: None,
            state={},
        )
        app = FastAPI()
        app.include_router(crea_router(ctx))
        return TestClient(app)

    def test_nessuna_nota_ancora(self, store: Store, tmp_path: Path) -> None:
        session_id = store.create_session(0)
        client = self._client(store, tmp_path)
        r = client.get(f"/sessions/{session_id}/note")
        assert r.status_code == 200
        assert r.json() == {"note": []}

    def test_le_note_gia_prese_vengono_elencate_in_ordine(
        self, store: Store, tmp_path: Path
    ) -> None:
        session_id = store.create_session(0)
        store.add_ai_output(
            session_id, "running_note", "seconda nota",
            model="m", provider="fake", prompt_id="running_note", prompt_version="v1",
            scope_start_ms=600_000, scope_end_ms=1_200_000,
            content_json=json.dumps([{"titolo": "x"}, {"titolo": "y"}]),
        )
        store.add_ai_output(
            session_id, "running_note", "prima nota",
            model="m", provider="fake", prompt_id="running_note", prompt_version="v1",
            scope_start_ms=0, scope_end_ms=600_000,
        )

        client = self._client(store, tmp_path)
        note = client.get(f"/sessions/{session_id}/note").json()["note"]

        assert [n["testo"] for n in note] == ["prima nota", "seconda nota"]
        assert note[0]["candidati_task"] == 0
        assert note[1]["candidati_task"] == 2
        assert note[1]["t_ms"] == 1_200_000

    def test_una_sessione_diversa_non_vede_le_note_altrui(
        self, store: Store, tmp_path: Path
    ) -> None:
        a = store.create_session(0)
        b = store.create_session(0)
        store.add_ai_output(
            a, "running_note", "nota di a",
            model="m", provider="fake", prompt_id="running_note", prompt_version="v1",
            scope_start_ms=0, scope_end_ms=100,
        )
        client = self._client(store, tmp_path)
        assert client.get(f"/sessions/{b}/note").json() == {"note": []}
