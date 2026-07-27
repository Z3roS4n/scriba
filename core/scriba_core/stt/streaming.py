"""Trascrizione in tempo reale di una traccia audio.

Il problema da risolvere: mostrare testo mentre la persona parla, senza che
quel testo continui a cambiare sotto gli occhi di chi legge.

Un modello che trascrive gli ultimi secondi di audio produce risultati diversi a
ogni chiamata, perché ogni volta ha più contesto: "quando" diventa "quanto",
"il mock" diventa "il mockup". Mostrare l'ultima ipotesi grezza dà un testo che
sfarfalla ed è illeggibile.

La soluzione è LocalAgreement: si trascrive due volte a distanza di un attimo e
si congela solo il prefisso su cui le due ipotesi concordano. Su quel prefisso
il contesto aggiuntivo non ha cambiato idea, quindi difficilmente lo farà dopo.
Il resto resta provvisorio e può ancora muoversi.

Quando chi parla si ferma, la frase viene ritrascritta per intero — con tutto il
contesto disponibile in una volta sola — e il testo definitivo sostituisce il
provvisorio.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .base import TranscriptEvent

SAMPLE_RATE = 16_000


@dataclass
class StreamingConfig:
    # Ogni quanto ricalcolare l'ipotesi. Sotto i 0.7 s si spreca CPU senza che
    # l'utente percepisca differenza; sopra 1.5 s il testo sembra in ritardo.
    hop_s: float = 1.0
    # Silenzio dopo il quale si considera finita la frase. 700 ms è sopra le
    # pause naturali dentro una frase e sotto l'attesa che infastidisce.
    silence_ms: int = 700
    # Quanto audio guardare per decidere se c'è ancora qualcuno che parla.
    endpoint_window_s: float = 1.0
    # Oltre questa durata la frase viene chiusa comunque: il modello degrada
    # oltre i ~30 s e l'inferenza diventa troppo lenta per stare al passo.
    max_utterance_s: float = 25.0
    # Sotto questa durata non si tenta nemmeno: non c'è abbastanza segnale.
    min_utterance_s: float = 0.4
    # Quanto audio conservare prima che il VAD dichiari "qui si parla". Senza,
    # la prima sillaba di ogni frase viene tagliata.
    preroll_s: float = 0.4
    language: str | None = "it"


@dataclass
class _Utterance:
    """La frase attualmente in corso."""

    t_start_ms: int
    audio: list[np.ndarray] = field(default_factory=list)
    n_samples: int = 0
    committed: list[str] = field(default_factory=list)
    prev_hyp: list[str] = field(default_factory=list)
    last_emitted: str = ""

    def append(self, samples: np.ndarray) -> None:
        self.audio.append(samples)
        self.n_samples += len(samples)

    def waveform(self) -> np.ndarray:
        if not self.audio:
            return np.zeros(0, dtype=np.float32)
        if len(self.audio) > 1:
            self.audio = [np.concatenate(self.audio)]
        return self.audio[0]

    @property
    def duration_s(self) -> float:
        return self.n_samples / SAMPLE_RATE


def common_prefix(a: list[str], b: list[str]) -> list[str]:
    """Il tratto iniziale su cui due ipotesi sono d'accordo."""
    out: list[str] = []
    for x, y in zip(a, b):
        if x != y:
            break
        out.append(x)
    return out


class StreamingTranscriber:
    """Trascrive una traccia mentre arriva, emettendo parziali e definitivi.

    L'audio viene consegnato dal thread che cattura dalla scheda audio, che non
    può essere bloccato: `feed` si limita ad accodare. L'inferenza gira su un
    thread suo, che è anche l'unico a toccare lo stato della frase in corso.
    """

    def __init__(
        self,
        engine,
        source: str,
        on_event: Callable[[TranscriptEvent], None],
        config: StreamingConfig | None = None,
    ) -> None:
        self.engine = engine
        self.source = source
        self.on_event = on_event
        self.cfg = config or StreamingConfig()

        self._pending: list[tuple[np.ndarray, int]] = []
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._utt: _Utterance | None = None
        self._thread: threading.Thread | None = None
        # Audio in attesa che il VAD dichiari che qualcuno sta parlando. Finché
        # resta qui, non raggiunge il modello.
        self._idle: list[np.ndarray] = []
        self._idle_t_ms: int | None = None
        self._idle_samples = 0

    # ------------------------------------------------------------------ ciclo

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name=f"stt-{self.source}", daemon=True
        )
        self._thread.start()

    def stop(self, *, timeout: float = 30.0) -> None:
        """Ferma la trascrizione dopo aver chiuso la frase in corso."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def feed(self, samples: np.ndarray, t_ms: int) -> None:
        """Consegna audio catturato. Chiamata dal thread audio: deve essere rapida."""
        if samples.size == 0:
            return
        with self._lock:
            self._pending.append((samples.astype(np.float32, copy=False), t_ms))
        self._wake.set()

    # ------------------------------------------------------------------ worker

    def _run(self) -> None:
        next_infer = time.perf_counter() + self.cfg.hop_s
        while not self._stop.is_set():
            self._wake.wait(timeout=0.1)
            self._wake.clear()
            self._drain()

            now = time.perf_counter()
            if now >= next_infer:
                next_infer = now + self.cfg.hop_s
                self._step()

        # Quando la call finisce, niente resta a metà: si svuota la coda, si dà
        # una possibilità all'audio ancora in attesa di giudizio, e si chiude la
        # frase in corso.
        self._drain()
        if self._utt is None:
            self._open_if_speech()
        self._finalize()

    def _drain(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, []
        for samples, t_ms in pending:
            if self._utt is not None:
                self._utt.append(samples)
                continue
            # Nessuna frase aperta: l'audio resta in attesa. Si conserva solo
            # l'ultimo tratto, quanto basta a non perdere l'inizio della frase
            # quando il VAD si accorgerà che qualcuno ha cominciato a parlare.
            if self._idle_t_ms is None:
                self._idle_t_ms = t_ms
            self._idle.append(samples)
            self._idle_samples += len(samples)
            self._trim_idle()

    def _trim_idle(self) -> None:
        keep = int((self.cfg.preroll_s + self.cfg.endpoint_window_s) * SAMPLE_RATE)
        while self._idle_samples - len(self._idle[0]) > keep and len(self._idle) > 1:
            dropped = self._idle.pop(0)
            self._idle_samples -= len(dropped)
            if self._idle_t_ms is not None:
                self._idle_t_ms += len(dropped) * 1000 // SAMPLE_RATE

    def _open_if_speech(self) -> None:
        """Apre una frase solo se il VAD sente davvero qualcuno parlare.

        Senza questo controllo il modello riceve silenzio e rumore di fondo, e
        li trasforma in parole: su una traccia muta produce a raffica "Yeah.",
        "Okay.", "Mm-hmm.". Non è un difetto correggibile con un prompt — va
        semplicemente evitato di dargli in pasto audio senza voce.
        """
        if self._idle_samples < int(self.cfg.endpoint_window_s * SAMPLE_RATE):
            return
        buf = np.concatenate(self._idle)
        if not self.engine.has_speech(buf):
            return

        # Si tiene la coda del buffer: il parlato è cominciato lì dentro, e il
        # pre-roll evita di tagliare la prima sillaba.
        keep = int((self.cfg.preroll_s + self.cfg.endpoint_window_s) * SAMPLE_RATE)
        t_offset = 0
        if len(buf) > keep:
            cut = len(buf) - keep
            t_offset = cut * 1000 // SAMPLE_RATE
            buf = buf[cut:]

        self._utt = _Utterance(t_start_ms=(self._idle_t_ms or 0) + t_offset)
        self._utt.append(buf)
        self._idle, self._idle_samples, self._idle_t_ms = [], 0, None

    def _step(self) -> None:
        if self._utt is None:
            self._open_if_speech()

        utt = self._utt
        if utt is None or utt.duration_s < self.cfg.min_utterance_s:
            return

        if utt.duration_s >= self.cfg.max_utterance_s:
            self._finalize()
            return

        if self._is_endpoint(utt):
            self._finalize()
            return

        self._emit_partial(utt)

    def _is_endpoint(self, utt: _Utterance) -> bool:
        """Chi parlava ha finito?

        Si guarda solo la coda dell'audio: se lì dentro non c'è parlato, la
        pausa è abbastanza lunga da chiudere la frase.
        """
        tail_len = int(self.cfg.endpoint_window_s * SAMPLE_RATE)
        if utt.n_samples < tail_len:
            return False
        tail = utt.waveform()[-tail_len:]
        return not self.engine.has_speech(tail)

    def _emit_partial(self, utt: _Utterance) -> None:
        hyp = self.engine.transcribe(utt.waveform(), language=self.cfg.language).split()
        if not hyp:
            return

        # Ciò su cui questa ipotesi e la precedente concordano è considerato
        # stabile: da lì in poi il testo può ancora cambiare.
        agreed = common_prefix(hyp, utt.prev_hyp)
        if len(agreed) > len(utt.committed):
            utt.committed = agreed
        utt.prev_hyp = hyp

        text = " ".join(hyp)
        if text == utt.last_emitted:
            return
        utt.last_emitted = text

        self.on_event(
            TranscriptEvent(
                source=self.source,
                t_start_ms=utt.t_start_ms,
                t_end_ms=utt.t_start_ms + int(utt.duration_s * 1000),
                text=text,
                is_final=False,
            )
        )

    def _finalize(self) -> None:
        """Chiude la frase ritrascrivendola per intero."""
        utt, self._utt = self._utt, None
        if utt is None or utt.duration_s < self.cfg.min_utterance_s:
            return

        # Secondo controllo prima di scrivere: il VAD aveva sentito voce
        # all'apertura, ma un colpo isolato (una porta, una notifica) può
        # aprire una frase che di parlato non ne contiene.
        if not self.engine.has_speech(utt.waveform()):
            return

        # Una passata sola su tutta la frase: il modello vede il contesto
        # completo invece di una finestra, e corregge ciò che in tempo reale
        # aveva potuto solo indovinare.
        text = self.engine.transcribe(utt.waveform(), language=self.cfg.language)
        if not text.strip():
            return

        self.on_event(
            TranscriptEvent(
                source=self.source,
                t_start_ms=utt.t_start_ms,
                t_end_ms=utt.t_start_ms + int(utt.duration_s * 1000),
                text=text.strip(),
                is_final=True,
            )
        )
