"""Governa una sessione di registrazione dall'inizio alla fine.

Tiene insieme i pezzi — orologio, cattura, trascrittori, database — e li spegne
nell'ordine giusto. L'ordine non è un dettaglio: si ferma prima la cattura e poi
i trascrittori, altrimenti la frase che l'utente stava pronunciando quando ha
premuto stop viene persa.

È l'unico posto che sa come si registra una call: la CLI e il server ci si
appoggiano entrambi invece di rifare il lavoro.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio.capture import DeviceInfo, DualCapture
from .db.store import Store
from .session import SessionClock, State
from .stt.base import TranscriptEvent
from .stt.streaming import StreamingConfig, StreamingTranscriber

SOURCES = ("mic", "loopback")


@dataclass(frozen=True)
class RecordingInfo:
    session_id: int
    started_at_ms: int
    devices: dict[str, DeviceInfo]


class Recorder:
    """Una registrazione in corso.

    Il modello di trascrizione viene passato dall'esterno perché caricarlo costa
    secondi: si tiene vivo fra una call e l'altra invece di ricaricarlo a ogni
    avvio.
    """

    def __init__(
        self,
        engine,
        store: Store,
        *,
        on_event: Callable[[TranscriptEvent], None] | None = None,
        config: StreamingConfig | None = None,
        capture_factory: Callable[..., DualCapture] | None = None,
    ) -> None:
        self.engine = engine
        self.store = store
        self._on_event = on_event
        self._config = config
        # Sostituibile nei test: aprire i device audio veri li renderebbe
        # dipendenti dall'hardware della macchina su cui girano.
        self._capture_factory = capture_factory or DualCapture
        self._lock = threading.Lock()

        self.clock: SessionClock | None = None
        self.session_id: int | None = None
        self._capture: DualCapture | None = None
        self._transcribers: dict[str, StreamingTranscriber] = {}
        # Il segmento provvisorio aperto per ogni traccia. Quando la frase si
        # chiude, quel record viene rifinito invece di crearne uno nuovo: è ciò
        # che tiene validi i riferimenti che le task avranno su questi segmenti.
        self._open_segments: dict[str, int] = {}

    # ------------------------------------------------------------------ stato

    @property
    def is_recording(self) -> bool:
        return self.clock is not None and self.clock.state in (State.RECORDING, State.PAUSED)

    def now_ms(self) -> int:
        """L'istante corrente della call.

        Chiunque debba datare qualcosa — uno screenshot, una nota — lo chiede
        qui invece di leggere un proprio orologio. Due orologi diversi producono
        uno scarto che nessuno nota finché non si prova a saltare all'audio da
        una citazione.
        """
        return self.clock.now_ms() if self.clock else 0

    # ------------------------------------------------------------------ avvio

    def start(
        self,
        *,
        titolo: str | None = None,
        piattaforma: str | None = None,
        lingua: str = "it",
        consenso_confermato_at: int | None = None,
    ) -> RecordingInfo:
        with self._lock:
            if self.is_recording:
                raise RuntimeError("C'è già una registrazione in corso.")

            self.clock = SessionClock()
            self.session_id = self.store.create_session(
                self.clock.started_at_ms,
                titolo=titolo,
                piattaforma=piattaforma,
                lingua=lingua,
                stt_model=self.engine.name,
                consenso_confermato_at=consenso_confermato_at,
            )
            self._open_segments.clear()

            cfg = self._config or StreamingConfig(language=lingua)
            self._transcribers = {
                source: StreamingTranscriber(self.engine, source, self._handle_event, cfg)
                for source in SOURCES
            }
            for t in self._transcribers.values():
                t.start()

            self._capture = self._capture_factory(self.clock, self._feed)
            try:
                devices = self._capture.start()
            except Exception:
                # Se l'audio non parte, non si lascia in giro una sessione
                # "in registrazione" che non registra niente.
                self._teardown_transcribers()
                self.store.set_session_state(self.session_id, "error")
                self.clock = None
                raise

            return RecordingInfo(
                session_id=self.session_id,
                started_at_ms=self.clock.started_at_ms,
                devices=devices,
            )

    def _feed(self, source: str, samples: np.ndarray, t_ms: int) -> None:
        transcriber = self._transcribers.get(source)
        if transcriber is not None:
            transcriber.feed(samples, t_ms)

    # ------------------------------------------------------------- eventi STT

    def _handle_event(self, ev: TranscriptEvent) -> None:
        session_id = self.session_id
        if session_id is None:
            return

        seg_id = self._open_segments.get(ev.source)
        if seg_id is None:
            seg_id = self.store.add_segment(
                session_id, ev.source, ev.t_start_ms, ev.t_end_ms, ev.text, is_final=ev.is_final
            )
            self._open_segments[ev.source] = seg_id
        else:
            self.store.refine_segment(
                seg_id, ev.text, t_end_ms=ev.t_end_ms, is_final=ev.is_final
            )
        if ev.is_final:
            self._open_segments.pop(ev.source, None)

        if self._on_event is not None:
            self._on_event(ev)

    # ------------------------------------------------------------ screenshot

    def add_screenshot(self, path: str | Path, **kwargs) -> tuple[int, int]:
        """Aggancia uno screenshot all'istante corrente della call.

        L'istante lo decide il recorder, non chi chiama: è la stessa timeline
        della trascrizione, e deve restare l'unica.
        """
        if self.session_id is None:
            raise RuntimeError("Nessuna registrazione in corso.")
        t_ms = self.now_ms()
        shot_id = self.store.add_screenshot(self.session_id, t_ms, str(path), **kwargs)
        return shot_id, t_ms

    # ------------------------------------------------------------ pausa/stop

    def pause(self) -> None:
        if self.clock is not None:
            self.clock.pause()

    def resume(self) -> None:
        if self.clock is not None:
            self.clock.resume()

    def stop(self) -> int | None:
        """Chiude la registrazione e restituisce l'id della sessione."""
        with self._lock:
            if self.clock is None or self.session_id is None:
                return None

            session_id = self.session_id
            if self._capture is not None:
                self._capture.stop()
                self._capture = None

            # Solo ora i trascrittori: fermandoli prima si perderebbe la frase
            # ancora in corso, che e' proprio quella a cui l'utente teneva
            # quando ha premuto stop.
            self._teardown_transcribers()

            self.store.end_session(session_id, self.clock.ended_at_ms)
            self.store.set_session_state(session_id, "ready")
            self.clock.stop()
            self.clock = None
            self.session_id = None
            self._open_segments.clear()
            return session_id

    def _teardown_transcribers(self) -> None:
        for t in self._transcribers.values():
            t.stop()
        self._transcribers.clear()

    def __enter__(self) -> Recorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
