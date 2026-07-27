"""Interfaccia comune ai motori di trascrizione.

Locale e API stanno dietro la stessa forma, così l'app non cambia quando si
passa dall'uno all'altro. Chi consuma gli eventi vede solo `TranscriptEvent`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class TranscriptEvent:
    """Un pezzo di trascrizione, provvisorio o definitivo.

    Durante una call lo stesso tratto di parlato viene emesso più volte: prima
    come `partial` mentre la persona parla, poi una volta sola come `final`
    quando ha finito la frase e il testo è stato ricalcolato sull'intera
    utterance. La UI sostituisce il provvisorio col definitivo; il database
    aggiorna lo stesso record invece di crearne uno nuovo, così i riferimenti
    delle task non si rompono.
    """

    source: str  # 'mic' | 'loopback'
    t_start_ms: int
    t_end_ms: int
    text: str
    is_final: bool
    confidence: float | None = None

    @property
    def duration_ms(self) -> int:
        return self.t_end_ms - self.t_start_ms


class Engine(Protocol):
    """Un motore che trasforma audio in testo."""

    name: str

    def transcribe(self, audio: np.ndarray, *, language: str | None = None) -> str:
        """Trascrive un blocco di audio mono a 16 kHz, float32 in [-1, 1]."""
        ...
