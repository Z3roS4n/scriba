"""Test dell'analisi AI.

Con un provider finto: qui si verifica cosa il codice fa dei risultati del
modello, non quanto il modello sia bravo. In particolare che una risposta
plausibile ma sbagliata — citazioni parafrasate, riferimenti inventati — non
riesca a entrare nel database.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.ai.analyze import (  # noqa: E402
    AnalisiInterrotta,
    Analizzatore,
    finestre,
    formatta_segmenti,
)
from scriba_core.db.store import Store  # noqa: E402
from scriba_core.llm.base import Completion  # noqa: E402
from scriba_core.llm.providers import _estrai_json  # noqa: E402


class FakeProvider:
    """Restituisce le risposte che gli si danno, in ordine."""

    name = "fake"
    model = "fake-1"

    def __init__(self, risposte: list[dict | str]) -> None:
        self.risposte = list(risposte)
        self.chiamate: list[str] = []

    def available(self) -> bool:
        return True

    def complete(self, *, system, user, schema=None, max_tokens=2048, temperature=0.2):
        self.chiamate.append(user)
        r = self.risposte.pop(0) if self.risposte else ""
        if isinstance(r, dict):
            return Completion(text="", data=r, model=self.model, provider=self.name,
                              tokens_in=100, tokens_out=50, cost_usd=0.001)
        return Completion(text=r, model=self.model, provider=self.name,
                          tokens_in=100, tokens_out=50, cost_usd=0.001)


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "ai.sqlite")


@pytest.fixture()
def call_sparsa(store: Store):
    """Una call in cui i dettagli di un impegno sono lontani fra loro."""
    session_id = store.create_session(int(datetime(2026, 7, 27, 10, 0).timestamp() * 1000))
    ids = {
        "titolo": store.add_segment(session_id, "loopback", 300_000, 306_000,
                                    "dovremmo preparare i mockup della dashboard", is_final=True),
        "due": store.add_segment(session_id, "loopback", 1_920_000, 1_924_000,
                                 "diciamo entro il quattordici", is_final=True),
        "chi": store.add_segment(session_id, "mic", 2_880_000, 2_884_000,
                                 "se ne occupa Marco", is_final=True),
    }
    return session_id, ids


class TestFormattazione:
    def test_ogni_riga_porta_l_id(self, store: Store) -> None:
        # E' l'aggancio con cui il modello indica le fonti senza copiarle.
        sid = store.create_session(0)
        seg = store.add_segment(sid, "mic", 65_000, 67_000, "ciao a tutti", is_final=True)
        riga = formatta_segmenti(store.segments(sid))
        assert riga == f"[{seg}] (01:05) io: ciao a tutti"

    def test_la_sorgente_diventa_chi_parla(self, store: Store) -> None:
        sid = store.create_session(0)
        store.add_segment(sid, "loopback", 0, 1000, "parlano gli altri", is_final=True)
        assert "altri:" in formatta_segmenti(store.segments(sid))


class TestFinestre:
    def test_una_call_corta_sta_in_una_finestra(self, store: Store) -> None:
        sid = store.create_session(0)
        for i in range(5):
            store.add_segment(sid, "mic", i * 1000, i * 1000 + 900, f"frase {i}", is_final=True)
        assert len(finestre(store.segments(sid))) == 1

    def test_una_call_lunga_viene_spezzata(self, store: Store) -> None:
        sid = store.create_session(0)
        for i in range(400):
            store.add_segment(sid, "mic", i * 1000, i * 1000 + 900,
                              " ".join(["parola"] * 30), is_final=True)
        assert len(finestre(store.segments(sid))) > 1

    def test_le_finestre_si_sovrappongono(self, store: Store) -> None:
        # Un impegno enunciato a cavallo di un taglio andrebbe altrimenti perso.
        sid = store.create_session(0)
        for i in range(400):
            store.add_segment(sid, "mic", i * 1000, i * 1000 + 900,
                              " ".join(["parola"] * 30), is_final=True)
        f = finestre(store.segments(sid))
        primi = {s.id for s in f[0]}
        secondi = {s.id for s in f[1]}
        assert primi & secondi, "nessuna sovrapposizione fra finestre consecutive"

    def test_nessun_segmento_va_perso(self, store: Store) -> None:
        sid = store.create_session(0)
        for i in range(200):
            store.add_segment(sid, "mic", i * 1000, i * 1000 + 900,
                              " ".join(["parola"] * 30), is_final=True)
        segmenti = store.segments(sid)
        visti = {s.id for f in finestre(segmenti) for s in f}
        assert visti == {s.id for s in segmenti}

    def test_trascrizione_vuota(self) -> None:
        assert finestre([]) == []


class TestEstrazioneTask:
    def test_ricompone_un_impegno_sparso(self, store: Store, call_sparsa) -> None:
        """Il caso per cui il progetto esiste."""
        session_id, ids = call_sparsa
        provider = FakeProvider([
            "## In breve\n- Si parla di dashboard",           # riassunto
            "[05:00] **Mockup** — se ne parla",                # punti salienti
            {"candidati": [                                    # estrazione
                {"temp_id": "c1", "titolo": "Preparare i mockup", "confidence": 0.7,
                 "evidence": [{"segment_id": ids["titolo"], "supports": "titolo"}]},
                {"temp_id": "c2", "titolo": "Scadenza mockup", "confidence": 0.6,
                 "due_raw": "entro il quattordici",
                 "evidence": [{"segment_id": ids["due"], "supports": "due_date"}]},
            ]},
            {"tasks": [                                        # unione
                {"titolo": "Preparare i mockup della dashboard",
                 "assignee": "Marco", "due_date": "2026-08-14",
                 "due_raw": "entro il quattordici", "confidence": 0.85,
                 "needs_review": False,
                 "evidence": [
                     {"segment_id": ids["titolo"], "supports": "titolo"},
                     {"segment_id": ids["due"], "supports": "due_date"},
                     {"segment_id": ids["chi"], "supports": "assignee"},
                 ]},
            ], "scartati": []},
        ])

        analisi = Analizzatore(provider, store).analizza(session_id)

        assert len(analisi.tasks) == 1
        task_id = analisi.tasks[0]["id"]
        evidence = store.task_evidence(task_id)
        assert {e["supports"] for e in evidence} == {"titolo", "due_date", "assignee"}
        # Ogni campo sa da quale minuto della call proviene.
        per_campo = {e["supports"]: e["t_ms"] for e in evidence}
        assert per_campo["titolo"] == 300_000
        assert per_campo["due_date"] == 1_920_000
        assert per_campo["assignee"] == 2_880_000

    def test_le_citazioni_le_rilegge_il_database(self, store: Store, call_sparsa) -> None:
        # Il modello non le scrive mai: cosi' non puo' parafrasarle ne' inventarle.
        session_id, ids = call_sparsa
        provider = FakeProvider([
            "riassunto", "salienti",
            {"candidati": []},
        ])
        Analizzatore(provider, store).analizza(session_id)

        # Nessun candidato: nessuna task, ma riassunto e salienti ci sono.
        assert store.conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"] == 0
        assert store.conn.execute(
            "SELECT COUNT(*) c FROM ai_outputs WHERE kind IN ('summary','highlights')"
        ).fetchone()["c"] == 2

    def test_un_riferimento_inventato_viene_scartato(self, store: Store, call_sparsa) -> None:
        session_id, ids = call_sparsa
        provider = FakeProvider([
            "riassunto", "salienti",
            {"candidati": [{"temp_id": "c1", "titolo": "x", "confidence": 0.9, "evidence": []}]},
            {"tasks": [
                {"titolo": "Task reale", "confidence": 0.9, "needs_review": False,
                 "evidence": [{"segment_id": ids["titolo"], "supports": "titolo"},
                              {"segment_id": 999_999, "supports": "due_date"}]},
                {"titolo": "Task tutta inventata", "confidence": 0.9, "needs_review": False,
                 "evidence": [{"segment_id": 888_888, "supports": "titolo"}]},
            ]},
        ])

        analisi = Analizzatore(provider, store).analizza(session_id)

        # La task senza nemmeno un riferimento verificabile non entra.
        assert len(analisi.tasks) == 1
        assert analisi.tasks[0]["titolo"] == "Task reale"
        # E di quella buona resta solo l'evidence che esiste davvero.
        evidence = store.task_evidence(analisi.tasks[0]["id"])
        assert len(evidence) == 1
        assert evidence[0]["supports"] == "titolo"

    def test_gli_id_provvisori_non_si_scontrano_fra_finestre(self, store: Store) -> None:
        # Ogni finestra numera i candidati da capo: senza un prefisso, il
        # passaggio di unione crederebbe che c1 della prima e c1 della seconda
        # siano lo stesso impegno.
        sid = store.create_session(0)
        for i in range(400):
            store.add_segment(sid, "mic", i * 1000, i * 1000 + 900,
                              " ".join(["parola"] * 30), is_final=True)

        n = len(finestre(store.segments(sid)))
        assert n > 1, "servono piu' finestre perche' il test abbia senso"
        # Ogni finestra restituisce un candidato chiamato "c1", come farebbe un
        # modello vero che numera da capo ogni volta.
        provider = FakeProvider(
            [
                {"candidati": [{"temp_id": "c1", "titolo": "t", "confidence": 0.9, "evidence": []}]}
                for _ in range(n)
            ]
        )
        candidati, _ = Analizzatore(provider, store).candidati(store.segments(sid))
        assert len({c["temp_id"] for c in candidati}) == n

    def test_i_costi_vengono_sommati(self, store: Store, call_sparsa) -> None:
        session_id, _ = call_sparsa
        provider = FakeProvider(["r", "s", {"candidati": []}])
        analisi = Analizzatore(provider, store).analizza(session_id)
        # Tre chiamate: riassunto, salienti, una finestra di estrazione.
        assert analisi.tokens_in == 300
        assert analisi.costo_usd == pytest.approx(0.003)

    def test_una_call_senza_trascrizione(self, store: Store) -> None:
        sid = store.create_session(0)
        provider = FakeProvider([])
        analisi = Analizzatore(provider, store).analizza(sid)
        assert analisi.tasks == []
        assert provider.chiamate == [], "nessuna chiamata su una call vuota"

    def test_la_sessione_viene_marcata_analizzata(self, store: Store, call_sparsa) -> None:
        session_id, _ = call_sparsa
        Analizzatore(FakeProvider(["r", "s", {"candidati": []}]), store).analizza(session_id)
        stato = store.conn.execute(
            "SELECT stato FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()["stato"]
        assert stato == "analyzed"

    def test_solo_i_segmenti_definitivi_finiscono_nell_analisi(self, store: Store) -> None:
        # I provvisori cambiano ancora: analizzarli significa ragionare su testo
        # che fra un secondo sara' diverso.
        sid = store.create_session(0)
        store.add_segment(sid, "mic", 0, 1000, "definitivo", is_final=True)
        store.add_segment(sid, "mic", 1000, 2000, "ancora provvisorio", is_final=False)
        provider = FakeProvider(["r", "s", {"candidati": []}])
        Analizzatore(provider, store).analizza(sid)
        assert "definitivo" in provider.chiamate[0]
        assert "provvisorio" not in provider.chiamate[0]


class TestCompletamentoDaiCandidati:
    """Il modello raggruppa, il codice compila i campi.

    Emerso provando un modello vero su una riunione con i dettagli sparsi: il
    raggruppamento gli riesce, il travaso dei valori nei campi no.
    """

    def test_i_campi_vuoti_si_riempiono_dai_candidati(self) -> None:
        candidati = [
            {"temp_id": "c1", "titolo": "Mockup", "evidence": [{"segment_id": 1, "supports": "titolo"}]},
            {"temp_id": "c2", "titolo": "Scadenza", "due_raw": "entro il quattordici",
             "evidence": [{"segment_id": 2, "supports": "due_date"}]},
            {"temp_id": "c3", "titolo": "Chi", "assignee": "Marco",
             "evidence": [{"segment_id": 3, "supports": "assignee"}]},
        ]
        # Il modello ha raggruppato bene ma ha lasciato i campi vuoti.
        tasks = [{"titolo": "Preparare i mockup", "merged_from": ["c1", "c2", "c3"],
                  "evidence": [{"segment_id": 1, "supports": "descrizione"}]}]

        unita = Analizzatore.completa_da_candidati(tasks, candidati)[0]
        assert unita["assignee"] == "Marco"
        assert unita["due_raw"] == "entro il quattordici"

    def test_gli_elenchi_per_campo_diventano_prove_etichettate(self) -> None:
        # Il formato prodotto dall'estrazione: un elenco di righe per ciascun
        # campo, invece di un elenco unico da etichettare voce per voce.
        candidati = [
            {"temp_id": "c1", "titolo": "Mockup", "righe_titolo": [12]},
            {"temp_id": "c2", "titolo": "Scadenza", "due_raw": "entro il quattordici",
             "righe_scadenza": [88]},
            {"temp_id": "c3", "titolo": "Chi", "assignee": "Marco", "righe_assignee": [140]},
        ]
        tasks = [{"titolo": "Preparare i mockup", "merged_from": ["c1", "c2", "c3"]}]

        unita = Analizzatore.completa_da_candidati(tasks, candidati)[0]
        per_campo = {p["supports"]: p["segment_id"] for p in unita["evidence"]}
        assert per_campo == {"titolo": 12, "due_date": 88, "assignee": 140}
        assert unita["assignee"] == "Marco"
        assert unita["due_raw"] == "entro il quattordici"

    def test_le_prove_tornano_etichettate_per_campo(self) -> None:
        # Il modello le rietichettava tutte "descrizione": si ricostruiscono
        # dai candidati, dove erano gia' corrette.
        candidati = [
            {"temp_id": "c1", "titolo": "x", "evidence": [{"segment_id": 1, "supports": "titolo"}]},
            {"temp_id": "c2", "titolo": "y", "evidence": [{"segment_id": 2, "supports": "assignee"}]},
        ]
        tasks = [{"titolo": "z", "merged_from": ["c1", "c2"],
                  "evidence": [{"segment_id": 1, "supports": "descrizione"}]}]

        prove = Analizzatore.completa_da_candidati(tasks, candidati)[0]["evidence"]
        assert {p["supports"] for p in prove} == {"titolo", "assignee"}

    def test_un_valore_gia_presente_non_viene_sovrascritto(self) -> None:
        candidati = [{"temp_id": "c1", "titolo": "x", "assignee": "Luca", "evidence": []}]
        tasks = [{"titolo": "y", "assignee": "Marco", "merged_from": ["c1"]}]
        assert Analizzatore.completa_da_candidati(tasks, candidati)[0]["assignee"] == "Marco"

    def test_a_parita_vince_quanto_detto_dopo(self) -> None:
        # Le decisioni successive sovrascrivono le precedenti.
        candidati = [
            {"temp_id": "c1", "titolo": "x", "assignee": "Luca", "evidence": []},
            {"temp_id": "c2", "titolo": "x", "assignee": "Marco", "evidence": []},
        ]
        tasks = [{"titolo": "x", "merged_from": ["c1", "c2"]}]
        assert Analizzatore.completa_da_candidati(tasks, candidati)[0]["assignee"] == "Marco"

    def test_le_prove_duplicate_si_contano_una_volta(self) -> None:
        candidati = [
            {"temp_id": "c1", "titolo": "x", "evidence": [{"segment_id": 1, "supports": "titolo"}]},
            {"temp_id": "c2", "titolo": "x", "evidence": [{"segment_id": 1, "supports": "titolo"}]},
        ]
        tasks = [{"titolo": "x", "merged_from": ["c1", "c2"]}]
        assert len(Analizzatore.completa_da_candidati(tasks, candidati)[0]["evidence"]) == 1

    def test_un_riferimento_a_un_candidato_inesistente_non_rompe(self) -> None:
        tasks = [{"titolo": "x", "merged_from": ["mai-visto"], "evidence": []}]
        assert Analizzatore.completa_da_candidati(tasks, [])[0]["titolo"] == "x"

    def test_senza_merged_from_la_task_resta_com_e(self) -> None:
        tasks = [{"titolo": "x", "assignee": "Marco",
                  "evidence": [{"segment_id": 1, "supports": "titolo"}]}]
        unita = Analizzatore.completa_da_candidati(tasks, [])[0]
        assert unita["assignee"] == "Marco"
        assert len(unita["evidence"]) == 1


class TestEstrazioneJson:
    def test_json_puro(self) -> None:
        assert _estrai_json('{"a": 1}') == {"a": 1}

    def test_json_in_un_blocco_markdown(self) -> None:
        # Capita che le API incorniciino la risposta nonostante le istruzioni.
        assert _estrai_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_json_preceduto_da_chiacchiere(self) -> None:
        assert _estrai_json('Ecco il risultato:\n{"a": 1}') == {"a": 1}

    def test_senza_json_si_solleva(self) -> None:
        from scriba_core.llm.base import LLMError

        with pytest.raises(LLMError):
            _estrai_json("non c'e' nulla qui")


class TestTroncamento:
    """Una risposta incompleta e una malformata sono guasti diversi.

    Confonderli fa perdere tempo: un JSON tagliato a meta' perche' sono finiti
    i token somiglia a un JSON scritto male, ma si risolve alzando un numero.
    """

    def test_il_troncamento_viene_riconosciuto(self) -> None:
        from scriba_core.llm.base import LLMError
        from scriba_core.llm.providers import _controlla_troncamento

        with pytest.raises(LLMError, match="limite di token"):
            _controlla_troncamento("length")
        with pytest.raises(LLMError, match="limite di token"):
            _controlla_troncamento("max_tokens")

    def test_una_risposta_completa_passa(self) -> None:
        from scriba_core.llm.providers import _controlla_troncamento

        _controlla_troncamento("stop")
        _controlla_troncamento(None)

class TestStopInRitardo:
    """Lo stop che arriva all'ultimo confine non butta via il lavoro.

    L'interruzione si controlla fra una fase e l'altra. L'ultimo confine è
    l'annuncio che l'unione è **finita**, e a quel punto riassunto, punti
    salienti e task sono già scritti nel database: fermarsi lì non risparmia
    niente, cancella dieci minuti di lavoro già fatto e pagato.

    È successo su una call di due ore (#97): quindici task salvate, e la
    sessione segnata «non riuscita».
    """

    @staticmethod
    def _analizzatore() -> Analizzatore:
        def annulla_sempre(chiave, stato, nota=None, nota_chiave=None, nota_valori=None):
            raise AnalisiInterrotta("interrotta dall'utente")

        return Analizzatore(FakeProvider([]), None, on_fase=annulla_sempre)  # type: ignore[arg-type]

    def test_l_ultimo_annuncio_non_ferma(self) -> None:
        # Non solleva: il lavoro è già scritto.
        self._analizzatore()._fine_unione("3 task", "task_n", {"n": 3})

    def test_i_confini_prima_fermano_ancora(self) -> None:
        # Dove c'è ancora qualcosa da risparmiare, lo stop vale.
        with pytest.raises(AnalisiInterrotta):
            self._analizzatore()._avvisa("riassunto", "in_corso")
