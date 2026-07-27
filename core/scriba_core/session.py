"""L'orologio della sessione.

Tutto ciò che viene registrato durante una call — un pezzo di trascrizione, uno
screenshot, una nota — deve poter essere messo in fila con tutto il resto. Perché
funzioni, esiste **un solo orologio**, e sta qui.

La UI non calcola mai da sola l'istante di uno screenshot: lo chiede al core. Due
processi che leggono due orologi diversi producono uno scarto che nessuno nota
finché non si prova a saltare all'audio da una citazione e ci si ritrova venti
secondi più in là.

Si usa `perf_counter`, che è monotonico: non torna indietro se l'ora di sistema
viene corretta (NTP, cambio di fuso) durante una call.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class SessionClock:
    """Converte il tempo reale in millisecondi dall'inizio della call."""

    # Riferimento monotonico: l'unico usato per calcolare le posizioni.
    _t0_perf: float = field(default_factory=time.perf_counter)
    # Ora di calendario del medesimo istante: serve solo a datare la sessione.
    started_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    state: State = State.RECORDING
    _paused_total: float = 0.0
    _paused_at: float | None = None

    def now_ms(self) -> int:
        """Millisecondi dall'inizio della call, pause escluse."""
        elapsed = time.perf_counter() - self._t0_perf - self._paused_total
        if self._paused_at is not None:
            elapsed -= time.perf_counter() - self._paused_at
        return int(elapsed * 1000)

    def to_ms(self, t_perf: float) -> int:
        """Converte un `perf_counter` già preso (es. l'arrivo di un chunk audio).

        Serve perché chi cattura l'audio marca i suoi blocchi nel momento esatto
        in cui arrivano, e quel valore va tradotto sulla stessa timeline senza
        rileggere l'orologio più tardi.
        """
        elapsed = t_perf - self._t0_perf - self._paused_total
        if self._paused_at is not None and t_perf > self._paused_at:
            elapsed -= t_perf - self._paused_at
        return int(elapsed * 1000)

    def pause(self) -> None:
        if self.state is not State.RECORDING:
            return
        self._paused_at = time.perf_counter()
        self.state = State.PAUSED

    def resume(self) -> None:
        if self.state is not State.PAUSED or self._paused_at is None:
            return
        self._paused_total += time.perf_counter() - self._paused_at
        self._paused_at = None
        self.state = State.RECORDING

    def stop(self) -> int:
        """Chiude la sessione e restituisce la durata in millisecondi."""
        if self.state is State.PAUSED:
            self.resume()
        duration = self.now_ms()
        self.state = State.STOPPED
        return duration

    @property
    def ended_at_ms(self) -> int:
        """Ora di calendario della fine, dedotta dalla durata monotonica."""
        return self.started_at_ms + self.now_ms()
