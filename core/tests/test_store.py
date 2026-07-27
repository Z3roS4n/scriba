"""Test del layer dati.

Si concentrano su ciò che romperebbe la funzione più importante dell'app:
ricomporre una task dai dettagli sparsi lungo la call, sapendo da dove viene
ogni pezzo.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.db.store import Store  # noqa: E402
from scriba_core.session import SessionClock, State  # noqa: E402


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "test.sqlite")


@pytest.fixture()
def session_id(store: Store) -> int:
    return store.create_session(1_700_000_000_000, titolo="Riunione di prova")


def test_sessione_nasce_con_entrambi_i_ruoli(store: Store, session_id: int) -> None:
    # I ruoli derivano dalla sorgente audio, non da un'inferenza: devono esistere
    # da subito, senza aspettare che qualcuno parli.
    ruoli = {r["ruolo"] for r in store.conn.execute(
        "SELECT ruolo FROM speakers WHERE session_id = ?", (session_id,)
    )}
    assert ruoli == {"me", "them"}


def test_sorgente_determina_il_parlante(store: Store, session_id: int) -> None:
    mic = store.add_segment(session_id, "mic", 0, 1000, "ci penso io")
    loop = store.add_segment(session_id, "loopback", 1000, 2000, "perfetto grazie")

    ruoli = {
        r["id"]: r["ruolo"]
        for r in store.conn.execute(
            """
            SELECT s.id, sp.ruolo FROM transcript_segments s
              JOIN speakers sp ON sp.id = s.speaker_id
             WHERE s.session_id = ?
            """,
            (session_id,),
        )
    }
    assert ruoli[mic] == "me"
    assert ruoli[loop] == "them"


def test_rifinire_un_segmento_non_ne_cambia_l_identita(store: Store, session_id: int) -> None:
    # Il testo provvisorio viene sostituito da quello definitivo, ma l'id resta:
    # è quello che tiene in piedi i riferimenti delle task.
    seg = store.add_segment(session_id, "mic", 0, 3000, "prepariamo il mock", is_final=False)
    store.refine_segment(seg, "prepariamo il mockup della dashboard", t_end_ms=3200)

    row = store.conn.execute(
        "SELECT testo, is_final, revision, t_end_ms FROM transcript_segments WHERE id = ?",
        (seg,),
    ).fetchone()
    assert row["testo"] == "prepariamo il mockup della dashboard"
    assert row["is_final"] == 1
    assert row["revision"] == 1
    assert row["t_end_ms"] == 3200


def test_ricerca_full_text_segue_le_revisioni(store: Store, session_id: int) -> None:
    seg = store.add_segment(session_id, "mic", 0, 1000, "parliamo di fatturazione")
    assert len(store.search("fatturazione")) == 1

    store.refine_segment(seg, "parliamo di contrattualistica")
    # Se l'indice non seguisse l'aggiornamento, la ricerca troverebbe testo che
    # non esiste più.
    assert store.search("fatturazione") == []
    assert len(store.search("contrattualistica")) == 1


def test_ricerca_ignora_accenti_e_maiuscole(store: Store, session_id: int) -> None:
    store.add_segment(session_id, "loopback", 0, 1000, "serve la Città entro lunedì")
    assert len(store.search("citta")) == 1


def test_task_ricomposta_da_momenti_diversi(store: Store, session_id: int) -> None:
    """Il caso che il progetto esiste per risolvere.

    Il lavoro si nomina al minuto 5, la scadenza si concorda al 32, il
    responsabile si decide al 48. Deve venirne fuori una task sola, che sa
    quale campo viene da quale momento.
    """
    titolo_seg = store.add_segment(session_id, "loopback", 300_000, 306_000,
                                   "dovremmo preparare i mockup della dashboard")
    due_seg = store.add_segment(session_id, "loopback", 1_920_000, 1_924_000,
                                "diciamo entro il quattordici")
    who_seg = store.add_segment(session_id, "mic", 2_880_000, 2_884_000,
                                "se ne occupa Marco")

    task = store.add_task(
        session_id,
        "Preparare i mockup della dashboard",
        due_date="2026-08-14",
        due_raw="entro il quattordici",
        assignee_text="Marco",
        confidence=0.81,
        evidence=[
            {"segment_id": titolo_seg, "supports": "titolo"},
            {"segment_id": due_seg, "supports": "due_date"},
            {"segment_id": who_seg, "supports": "assignee"},
        ],
    )

    evidence = store.task_evidence(task)
    assert len(evidence) == 3
    per_campo = {e["supports"]: e for e in evidence}
    assert per_campo["titolo"]["t_ms"] == 300_000
    assert per_campo["due_date"]["t_ms"] == 1_920_000
    assert per_campo["assignee"]["t_ms"] == 2_880_000
    # Le evidence arrivano ordinate: la UI le mostra in ordine di call.
    assert [e["t_ms"] for e in evidence] == sorted(e["t_ms"] for e in evidence)


def test_le_citazioni_vengono_dal_db_non_da_chi_chiama(store: Store, session_id: int) -> None:
    # Il modello indica solo *quale* segmento: il testo lo mette il database.
    # Così una citazione parafrasata o inventata non può entrare.
    seg = store.add_segment(session_id, "loopback", 5_000, 6_000, "il budget è quarantamila")
    task = store.add_task(
        session_id,
        "Confermare il budget",
        evidence=[{"segment_id": seg, "supports": "descrizione", "quote": "il budget è centomila"}],
    )
    assert store.task_evidence(task)[0]["quote"] == "il budget è quarantamila"


def test_evidence_su_segmento_inesistente_viene_scartata(store: Store, session_id: int) -> None:
    seg = store.add_segment(session_id, "mic", 0, 1000, "reale")
    task = store.add_task(
        session_id,
        "Task con un riferimento inventato",
        evidence=[
            {"segment_id": seg, "supports": "titolo"},
            {"segment_id": 999_999, "supports": "due_date"},
        ],
    )
    evidence = store.task_evidence(task)
    assert len(evidence) == 1
    assert evidence[0]["supports"] == "titolo"


def test_la_citazione_resta_stabile_se_il_segmento_cambia(store: Store, session_id: int) -> None:
    # Se la trascrizione viene rifinita dopo che l'utente ha già visto la task,
    # la citazione mostrata non deve cambiargli sotto gli occhi. Il testo
    # aggiornato resta comunque consultabile.
    seg = store.add_segment(session_id, "loopback", 1_000, 2_000, "entro venerd")
    task = store.add_task(session_id, "Consegnare",
                          evidence=[{"segment_id": seg, "supports": "due_date"}])
    store.refine_segment(seg, "entro venerdì prossimo")

    ev = store.task_evidence(task)[0]
    assert ev["quote"] == "entro venerd"
    assert ev["testo_corrente"] == "entro venerdì prossimo"
    assert ev["revision"] == 1


def test_rigenerare_un_output_ritira_il_precedente(store: Store, session_id: int) -> None:
    comune = {"model": "gemma-4-12b", "provider": "local", "prompt_id": "summary"}
    store.add_ai_output(session_id, "summary", "prima stesura", prompt_version="v1", **comune)
    store.add_ai_output(session_id, "summary", "seconda stesura", prompt_version="v2", **comune)

    correnti = store.conn.execute(
        "SELECT content_md, version FROM ai_outputs WHERE session_id = ? AND is_current = 1",
        (session_id,),
    ).fetchall()
    assert len(correnti) == 1
    assert correnti[0]["content_md"] == "seconda stesura"
    assert correnti[0]["version"] == 2
    # Lo storico resta: serve a confrontare le versioni di prompt.
    assert store.conn.execute(
        "SELECT COUNT(*) c FROM ai_outputs WHERE session_id = ?", (session_id,)
    ).fetchone()["c"] == 2


def test_running_note_diverse_convivono(store: Store, session_id: int) -> None:
    # Ogni finestra della call ha la sua nota: non devono ritirarsi a vicenda.
    comune = {"model": "gemma-4-12b", "provider": "local",
              "prompt_id": "running", "prompt_version": "v1"}
    store.add_ai_output(session_id, "running_note", "primi 10 minuti",
                        scope_start_ms=0, scope_end_ms=600_000, **comune)
    store.add_ai_output(session_id, "running_note", "secondi 10 minuti",
                        scope_start_ms=600_000, scope_end_ms=1_200_000, **comune)

    assert store.conn.execute(
        "SELECT COUNT(*) c FROM ai_outputs WHERE session_id = ? AND is_current = 1",
        (session_id,),
    ).fetchone()["c"] == 2


def test_cancellare_la_sessione_porta_via_tutto(store: Store, session_id: int) -> None:
    seg = store.add_segment(session_id, "mic", 0, 1000, "qualcosa")
    store.add_task(session_id, "Una task", evidence=[{"segment_id": seg, "supports": "titolo"}])
    store.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    for tabella in ("transcript_segments", "tasks", "speakers", "task_evidence"):
        assert store.conn.execute(f"SELECT COUNT(*) c FROM {tabella}").fetchone()["c"] == 0


def test_scritture_da_thread_diversi(store: Store, session_id: int) -> None:
    # Durante una call scrivono due trascrittori in parallelo, uno per traccia.
    errori: list[Exception] = []

    def scrivi(source: str, base: int) -> None:
        try:
            for i in range(40):
                store.add_segment(session_id, source, base + i * 100, base + i * 100 + 90, f"{source} {i}")
        except Exception as exc:  # pragma: no cover
            errori.append(exc)

    threads = [
        threading.Thread(target=scrivi, args=("mic", 0)),
        threading.Thread(target=scrivi, args=("loopback", 50)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errori == []
    assert len(store.segments(session_id)) == 80


class TestSessionClock:
    def test_parte_da_zero(self) -> None:
        assert SessionClock().now_ms() < 50

    def test_la_pausa_non_scorre(self) -> None:
        clock = SessionClock()
        clock.pause()
        prima = clock.now_ms()
        time_sleep(0.15)
        assert clock.now_ms() - prima < 20
        assert clock.state is State.PAUSED

        clock.resume()
        assert clock.state is State.RECORDING

    def test_converte_un_istante_gia_preso(self) -> None:
        # Chi cattura l'audio marca i chunk quando arrivano; quel valore va
        # tradotto sulla stessa timeline anche molto dopo.
        import time as _time

        clock = SessionClock()
        t = _time.perf_counter()
        time_sleep(0.1)
        assert clock.to_ms(t) < 30

    def test_stop_restituisce_la_durata(self) -> None:
        clock = SessionClock()
        time_sleep(0.05)
        durata = clock.stop()
        assert durata >= 40
        assert clock.state is State.STOPPED


def time_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
