"""Test della trascrizione in tempo reale.

Usano un motore finto: la logica da verificare è quando si emette e cosa si
congela, non quanto capisce il modello. Con un motore vero questi test
durerebbero minuti e fallirebbero per motivi che non c'entrano.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.stt.base import TranscriptEvent  # noqa: E402
from scriba_core.stt.streaming import (  # noqa: E402
    SAMPLE_RATE,
    StreamingConfig,
    StreamingTranscriber,
    common_prefix,
)


class FakeEngine:
    """Motore controllabile: restituisce le ipotesi che gli si danno, in ordine.

    `speech` può essere un bool fisso oppure una sequenza consumata a ogni
    interrogazione del VAD: serve a costruire lo scenario "qui qualcuno inizia a
    parlare, poi si ferma" senza audio vero.
    """

    def __init__(self, hypotheses: list[str], *, speech: bool | list[bool] = True) -> None:
        self.hypotheses = list(hypotheses)
        self.calls = 0
        self.speech = speech
        self.speech_calls = 0

    def transcribe(self, audio: np.ndarray, *, language: str | None = None) -> str:
        idx = min(self.calls, len(self.hypotheses) - 1)
        self.calls += 1
        return self.hypotheses[idx]

    def has_speech(self, audio: np.ndarray) -> bool:
        if isinstance(self.speech, bool):
            return self.speech
        idx = min(self.speech_calls, len(self.speech) - 1)
        self.speech_calls += 1
        return self.speech[idx]


def audio(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def apri_frase(t: StreamingTranscriber, seconds: float = 2.0, t_ms: int = 0):
    """Porta il trascrittore ad avere una frase aperta.

    L'audio non arriva mai al modello finché il VAD non dichiara che qualcuno
    sta parlando: i test che vogliono verificare cosa succede *dopo* devono
    passare da qui.
    """
    t.feed(audio(seconds), t_ms)
    t._drain()
    t._open_if_speech()
    return t._utt


class TestCommonPrefix:
    def test_prefisso_condiviso(self) -> None:
        assert common_prefix(["il", "budget", "e", "quaranta"], ["il", "budget", "sono"]) == [
            "il",
            "budget",
        ]

    def test_nessun_accordo(self) -> None:
        assert common_prefix(["ciao"], ["salve"]) == []

    def test_una_ipotesi_vuota(self) -> None:
        assert common_prefix([], ["qualcosa"]) == []


class TestLocalAgreement:
    """Il congelamento del testo: la parte che decide se la UI sfarfalla."""

    def _run(self, hypotheses: list[str]) -> tuple[StreamingTranscriber, list[TranscriptEvent]]:
        events: list[TranscriptEvent] = []
        t = StreamingTranscriber(
            FakeEngine(hypotheses),
            "mic",
            events.append,
            StreamingConfig(hop_s=0.01, min_utterance_s=0.1),
        )
        return t, events

    def test_congela_solo_cio_su_cui_due_ipotesi_concordano(self) -> None:
        # La prima ipotesi non ha con cosa concordare: niente viene congelato.
        # Dalla seconda in poi si congela il prefisso comune.
        t, _ = self._run(["prepariamo il mock", "prepariamo il mockup della"])
        utt = apri_frase(t)
        t._emit_partial(utt)
        assert utt.committed == []

        t._emit_partial(utt)
        assert utt.committed == ["prepariamo", "il"]

    def test_una_parola_che_cambia_non_viene_congelata(self) -> None:
        # "mock" -> "mockup": il modello ha cambiato idea avendo più contesto.
        # Quella parola non deve finire fra quelle stabili.
        t, _ = self._run(["il mock", "il mockup"])
        utt = apri_frase(t)
        t._emit_partial(utt)
        t._emit_partial(utt)
        assert utt.committed == ["il"]

    def test_il_congelato_non_torna_indietro(self) -> None:
        t, _ = self._run(["a b c", "a b c", "a x"])
        utt = apri_frase(t)
        for _ in range(3):
            t._emit_partial(utt)
        assert utt.committed == ["a", "b", "c"]

    def test_non_riemette_testo_identico(self) -> None:
        t, events = self._run(["stesso testo"])
        utt = apri_frase(t)
        t._emit_partial(utt)
        t._emit_partial(utt)
        assert len(events) == 1


class TestCancelloVAD:
    """Nessun audio raggiunge il modello se prima il VAD non sente una voce.

    Senza questo filtro il modello riceve silenzio e rumore di fondo e li
    trasforma in parole: su una traccia muta produce a raffica "Yeah.", "Okay.",
    "Mm-hmm.". Emerso in una prova end-to-end reale.
    """

    def test_il_silenzio_non_arriva_mai_al_modello(self) -> None:
        events: list[TranscriptEvent] = []
        engine = FakeEngine(["Yeah.", "Okay.", "Mm-hmm."], speech=False)
        t = StreamingTranscriber(
            engine, "mic", events.append, StreamingConfig(hop_s=0.01, min_utterance_s=0.1)
        )
        for _ in range(10):
            t.feed(audio(1.0), 0)
            t._drain()
            t._step()

        assert engine.calls == 0, "il modello e' stato interrogato su audio senza voce"
        assert events == []

    def test_una_voce_apre_la_frase(self) -> None:
        t = StreamingTranscriber(
            FakeEngine(["ciao"], speech=True), "mic", lambda e: None,
            StreamingConfig(hop_s=0.01, min_utterance_s=0.1),
        )
        assert apri_frase(t) is not None

    def test_il_buffer_in_attesa_non_cresce_all_infinito(self) -> None:
        # Durante i silenzi lunghi di una call si accumulerebbero minuti di
        # audio inutile in memoria.
        t = StreamingTranscriber(
            FakeEngine(["x"], speech=False), "mic", lambda e: None,
            StreamingConfig(hop_s=0.01, preroll_s=0.4, endpoint_window_s=1.0),
        )
        for _ in range(60):
            t.feed(audio(1.0), 0)
            t._drain()
        assert t._idle_samples <= int(3.0 * SAMPLE_RATE)

    def test_l_inizio_della_frase_non_viene_tagliato(self) -> None:
        # Il VAD si accorge del parlato con un attimo di ritardo: senza pre-roll
        # la prima sillaba di ogni frase sparirebbe.
        t = StreamingTranscriber(
            FakeEngine(["x"], speech=True), "mic", lambda e: None,
            StreamingConfig(hop_s=0.01, preroll_s=0.4, endpoint_window_s=1.0),
        )
        utt = apri_frase(t, seconds=1.5)
        assert utt.duration_s >= 1.3


class TestFinalizzazione:
    def test_il_silenzio_chiude_la_frase(self) -> None:
        events: list[TranscriptEvent] = []
        # Voce all'apertura, silenzio subito dopo: la frase si chiude.
        engine = FakeEngine(["testo definitivo"], speech=[True, False, True])
        t = StreamingTranscriber(
            engine, "mic", events.append, StreamingConfig(hop_s=0.01, min_utterance_s=0.1)
        )
        utt = apri_frase(t, seconds=2.0, t_ms=5_000)
        t._step()

        assert len(events) == 1
        assert events[0].is_final
        # La frase non parte dall'inizio del buffer in attesa ma da dove il
        # pre-roll l'ha tagliata: l'istante deve corrispondere a quello.
        assert events[0].t_start_ms == utt.t_start_ms
        assert events[0].t_start_ms >= 5_000
        assert t._utt is None  # pronta per la frase successiva

    def test_una_frase_troppo_lunga_viene_chiusa_comunque(self) -> None:
        # Chi parla senza pause nette non deve mandare il modello oltre il suo
        # limite: si chiude d'ufficio.
        events: list[TranscriptEvent] = []
        t = StreamingTranscriber(
            FakeEngine(["monologo"], speech=True),
            "mic",
            events.append,
            StreamingConfig(hop_s=0.01, max_utterance_s=2.0, min_utterance_s=0.1),
        )
        apri_frase(t, seconds=1.0)
        # Continua a parlare senza mai fermarsi: la frase supera il limite.
        t.feed(audio(3.0), 0)
        t._drain()
        t._step()

        assert [e.is_final for e in events] == [True]

    def test_frasi_troppo_corte_vengono_ignorate(self) -> None:
        events: list[TranscriptEvent] = []
        t = StreamingTranscriber(
            FakeEngine(["ah"], speech=True),
            "mic",
            events.append,
            StreamingConfig(hop_s=0.01, min_utterance_s=1.0),
        )
        t.feed(audio(0.2), 0)
        t._drain()
        t._step()
        assert events == []

    def test_una_trascrizione_vuota_non_produce_eventi(self) -> None:
        events: list[TranscriptEvent] = []
        t = StreamingTranscriber(
            FakeEngine(["   "], speech=[True, False, True]),
            "mic",
            events.append,
            StreamingConfig(hop_s=0.01, min_utterance_s=0.1),
        )
        apri_frase(t)
        t._step()
        assert events == []

    def test_una_frase_gia_mostrata_non_sparisce_se_la_passata_finale_e_vuota(self) -> None:
        # La passata di `_finalize` guarda la frase intera: su una frase lunga o
        # rumorosa puo' restituire vuoto anche dopo provvisori sensati. Buttare
        # via tutto vorrebbe dire perdere una riga che l'utente ha gia' letto.
        events: list[TranscriptEvent] = []
        t = StreamingTranscriber(
            FakeEngine(["il preventivo", "il preventivo di Clotilde", ""], speech=True),
            "mic",
            events.append,
            StreamingConfig(hop_s=0.01, min_utterance_s=0.1),
        )
        utt = apri_frase(t)
        t._emit_partial(utt)
        t._emit_partial(utt)
        t._finalize()

        assert events[-1].is_final
        assert events[-1].text == "il preventivo di Clotilde"

    def test_una_frase_gia_mostrata_si_chiude_anche_quando_non_resta_niente(self) -> None:
        # Qui non c'e' niente da salvare — il VAD, riguardando tutta la frase,
        # non ci sente parlato. Il definitivo esce lo stesso, vuoto: e' cio' che
        # dice a chi ascolta di togliere il provvisorio. Senza, quella frase
        # resterebbe aperta e se la prenderebbe la successiva.
        events: list[TranscriptEvent] = []
        t = StreamingTranscriber(
            FakeEngine(["rumore preso per parola"], speech=[True, False]),
            "mic",
            events.append,
            StreamingConfig(hop_s=0.01, min_utterance_s=0.1),
        )
        utt = apri_frase(t)
        t._emit_partial(utt)
        t._finalize()

        assert [(e.is_final, e.text) for e in events][-1] == (True, "")

    def test_un_rumore_isolato_non_diventa_testo(self) -> None:
        # Il VAD apre la frase su un colpo secco (una porta, una notifica), ma
        # sul totale non c'e' parlato: non deve finire nella trascrizione.
        events: list[TranscriptEvent] = []
        t = StreamingTranscriber(
            FakeEngine(["rumore interpretato come parola"], speech=[True, False, False]),
            "mic",
            events.append,
            StreamingConfig(hop_s=0.01, min_utterance_s=0.1),
        )
        apri_frase(t)
        t._step()
        assert events == []

    def test_la_sorgente_viene_riportata(self) -> None:
        events: list[TranscriptEvent] = []
        t = StreamingTranscriber(
            FakeEngine(["gli altri parlano"], speech=[True, False, True]),
            "loopback",
            events.append,
            StreamingConfig(hop_s=0.01, min_utterance_s=0.1),
        )
        apri_frase(t)
        t._step()
        assert events[0].source == "loopback"


class TestThread:
    def test_feed_non_blocca_il_thread_audio(self) -> None:
        """`feed` è chiamata dal callback della scheda audio: se aspetta
        l'inferenza, l'audio si perde."""

        class SlowEngine(FakeEngine):
            def transcribe(self, audio: np.ndarray, *, language: str | None = None) -> str:
                time.sleep(0.3)
                return "lento"

        t = StreamingTranscriber(
            SlowEngine(["lento"]), "mic", lambda e: None,
            StreamingConfig(hop_s=0.01, min_utterance_s=0.1),
        )
        t.start()
        try:
            time.sleep(0.05)  # lascio partire un'inferenza lenta
            start = time.perf_counter()
            for _ in range(20):
                t.feed(audio(0.1), 0)
            assert time.perf_counter() - start < 0.05
        finally:
            t.stop(timeout=5)

    def test_lo_stop_chiude_la_frase_in_corso(self) -> None:
        # Se la call finisce mentre qualcuno sta parlando, l'ultima frase non
        # deve sparire.
        events: list[TranscriptEvent] = []
        t = StreamingTranscriber(
            FakeEngine(["ultima frase"], speech=True),
            "mic",
            events.append,
            StreamingConfig(hop_s=10.0, min_utterance_s=0.1),
        )
        t.start()
        t.feed(audio(1.0), 0)
        time.sleep(0.15)
        t.stop(timeout=5)

        assert any(e.is_final for e in events)
        assert events[-1].text == "ultima frase"


def test_durata_evento() -> None:
    e = TranscriptEvent("mic", 1_000, 4_500, "x", is_final=True)
    assert e.duration_ms == 3_500
