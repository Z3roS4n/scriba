"""Cosa succede agli eventi di trascrizione fra il modello e il database.

Il pezzo delicato è uno solo: quando una frase si chiude e quando no. Un
segmento provvisorio che resta aperto viene rifinito dalla frase successiva —
che ne prende il posto tenendosi l'istante sbagliato — e della frase precedente
non resta traccia. È testo trascritto bene e perso dopo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.db.store import Store  # noqa: E402
from scriba_core.recorder import Recorder  # noqa: E402
from scriba_core.stt.base import TranscriptEvent  # noqa: E402


class MotoreFinto:
    """Il recorder ne usa solo il nome: la trascrizione qui arriva già fatta."""

    name = "finto"


@pytest.fixture()
def recorder(tmp_path: Path) -> Recorder:
    store = Store(tmp_path / "prova.sqlite")
    rec = Recorder(engine=MotoreFinto(), store=store, audio_dir=tmp_path / "audio")
    rec.session_id = store.create_session(0, titolo="Riunione di prova")
    return rec


def righe(rec: Recorder) -> list[tuple[int, str]]:
    return [(s.t_start_ms, s.testo) for s in rec.store.segments(rec.session_id)]


def test_una_frase_rifinita_resta_una_riga_sola(recorder: Recorder) -> None:
    recorder._handle_event(TranscriptEvent("mic", 1_000, 3_000, "il preventivo", is_final=False))
    recorder._handle_event(
        TranscriptEvent("mic", 1_000, 4_000, "il preventivo di Clotilde", is_final=True)
    )
    assert righe(recorder) == [(1_000, "il preventivo di Clotilde")]


def test_due_frasi_restano_due_righe(recorder: Recorder) -> None:
    recorder._handle_event(TranscriptEvent("mic", 1_000, 4_000, "il preventivo", is_final=True))
    recorder._handle_event(TranscriptEvent("mic", 30_000, 33_000, "passiamo oltre", is_final=True))
    assert righe(recorder) == [(1_000, "il preventivo"), (30_000, "passiamo oltre")]


def test_un_definitivo_vuoto_toglie_il_provvisorio(recorder: Recorder) -> None:
    # Il trascrittore ha aperto una frase su un rumore e poi si è accorto che
    # dentro non c'era parlato. Meglio nessuna riga che una riga vuota.
    recorder._handle_event(TranscriptEvent("mic", 1_000, 3_000, "eh", is_final=False))
    recorder._handle_event(TranscriptEvent("mic", 1_000, 3_000, "", is_final=True))
    assert righe(recorder) == []


def test_un_definitivo_vuoto_senza_provvisorio_non_scrive_niente(recorder: Recorder) -> None:
    recorder._handle_event(TranscriptEvent("mic", 1_000, 3_000, "", is_final=True))
    assert righe(recorder) == []


def test_una_frase_rimasta_aperta_non_viene_mangiata_da_quella_dopo(
    recorder: Recorder, caplog: pytest.LogCaptureFixture
) -> None:
    # È il difetto della issue #40, visto dal lato del recorder: il definitivo
    # della prima frase non arriva mai. Prima si perdeva la frase e la seconda
    # ne ereditava l'istante di inizio; adesso la prima si chiude com'era.
    recorder._handle_event(
        TranscriptEvent("mic", 1_000, 4_000, "il preventivo di Clotilde", is_final=False)
    )
    recorder._handle_event(
        TranscriptEvent("mic", 30_000, 33_000, "passiamo al punto due", is_final=False)
    )
    recorder._handle_event(
        TranscriptEvent("mic", 30_000, 33_000, "passiamo al punto due.", is_final=True)
    )

    assert righe(recorder) == [
        (1_000, "il preventivo di Clotilde"),
        (30_000, "passiamo al punto due."),
    ]
    # Non dovrebbe succedere: se succede si vuole trovarlo nel log, non
    # dedurlo da una trascrizione con dei buchi.
    assert any("rimasta aperta" in r.message for r in caplog.records)


class TestEco:
    """Quando il microfono riprende l'altoparlante (#59).

    Il difetto non era il criterio, era il momento: la frase dell'altoparlante
    entrava nel filtro solo chiudendosi, e l'eco sul microfono si chiude prima.
    """

    def test_l_ipotesi_provvisoria_dell_altro_basta_a_riconoscerlo(
        self, recorder: Recorder
    ) -> None:
        # L'altro sta ancora parlando: la sua frase non si chiudera' prima di
        # venti secondi. Aspettarla vuol dire giudicare al buio.
        recorder._handle_event(
            TranscriptEvent(
                "loopback", 157_200, 160_000, "Ok, quindi ora io devo dividere,", is_final=False
            )
        )
        recorder._handle_event(
            TranscriptEvent("mic", 158_400, 160_800, "Quindi ora io devo dividere.", is_final=True)
        )
        # Resta la riga dell'altoparlante, che e' di chi l'ha detta. Quella del
        # microfono no: e' la stessa frase, tornata indietro.
        assert [s.source for s in recorder.store.segments(recorder.session_id)] == ["loopback"]

    def test_la_riga_resta_scritta_ma_marcata(self, recorder: Recorder) -> None:
        # Una riga su tre e' eco: cancellarne una su tre in silenzio vorrebbe
        # dire che un giudizio sbagliato non lo vede piu' nessuno.
        recorder._handle_event(
            TranscriptEvent("loopback", 1_000, 4_000, "il preventivo di Clotilde", is_final=True)
        )
        recorder._handle_event(
            TranscriptEvent("mic", 2_000, 5_000, "il preventivo di Clotilde", is_final=True)
        )
        tutte = recorder.store.segments(recorder.session_id, includi_eco=True)
        assert [(s.source, s.eco) for s in tutte] == [("loopback", False), ("mic", True)]

    def test_il_ripasso_prende_quello_che_dal_vivo_era_impossibile(
        self, recorder: Recorder
    ) -> None:
        # Nessun provvisorio dall'altoparlante: il microfono chiude per primo e
        # dal vivo non c'e' modo di saperlo. A call finita invece si sa.
        recorder._handle_event(
            TranscriptEvent("mic", 158_400, 160_800, "Quindi ora io devo dividere.", is_final=True)
        )
        recorder._handle_event(
            TranscriptEvent(
                "loopback", 157_200, 183_100, "Ok. Quindi ora io devo dividere, poi vediamo.",
                is_final=True,
            )
        )
        assert len(righe(recorder)) == 2

        marcate = recorder._ripassa_eco(recorder.session_id)
        assert marcate == 1
        assert [s.source for s in recorder.store.segments(recorder.session_id)] == ["loopback"]

    def test_il_ripasso_non_tocca_una_conversazione_vera(self, recorder: Recorder) -> None:
        recorder._handle_event(
            TranscriptEvent(
                "loopback", 1_000, 5_000,
                "secondo me dovremmo rimandare la migrazione a settembre", is_final=True,
            )
        )
        recorder._handle_event(
            TranscriptEvent(
                "mic", 6_000, 9_000,
                "non sono d'accordo, settembre e' troppo tardi per il cliente", is_final=True,
            )
        )
        assert recorder._ripassa_eco(recorder.session_id) == 0
        assert len(righe(recorder)) == 2


def test_le_due_tracce_non_si_disturbano(recorder: Recorder) -> None:
    # Microfono e loopback hanno ognuno la propria frase in corso: il
    # provvisorio dell'uno non deve chiudere quello dell'altro.
    recorder._handle_event(TranscriptEvent("mic", 1_000, 3_000, "secondo me", is_final=False))
    recorder._handle_event(TranscriptEvent("loopback", 2_000, 4_000, "certo", is_final=False))
    recorder._handle_event(TranscriptEvent("mic", 1_000, 3_500, "secondo me sì", is_final=True))
    recorder._handle_event(TranscriptEvent("loopback", 2_000, 4_000, "certo.", is_final=True))

    assert sorted(righe(recorder)) == [(1_000, "secondo me sì"), (2_000, "certo.")]
