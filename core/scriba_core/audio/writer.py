"""Salva su disco l'audio della call, una traccia per sorgente.

Senza i file, una call è irripetibile: se la trascrizione viene male — modello
sbagliato, lingua sbagliata, un pezzo perso — non c'è modo di rifarla, e non si
può nemmeno provare a distinguere chi ha parlato. Il parlato è passato e non
torna.

Si scrive quello che è già stato convertito per la trascrizione: mono a 16 kHz.
Basta per ritrascrivere e per l'analisi delle voci, e occupa un ventesimo
dell'originale — mezz'ora di call sono circa 55 MB per traccia invece di oltre
un gigabyte.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000


class TrackWriter:
    """Scrive una traccia su file, senza far aspettare chi cattura.

    I blocchi arrivano dal thread della scheda audio, che non si può bloccare:
    finiscono in coda e un thread suo li scrive. Una scrittura lenta fa crescere
    la coda, non perdere audio.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._coda: queue.Queue[np.ndarray | None] = queue.Queue()
        self._file: wave.Wave_write | None = None
        self._thread: threading.Thread | None = None
        self._campioni = 0

    def start(self) -> None:
        self._file = wave.open(str(self.path), "wb")
        self._file.setnchannels(1)
        self._file.setsampwidth(2)  # PCM 16 bit
        self._file.setframerate(SAMPLE_RATE)
        self._thread = threading.Thread(
            target=self._scrivi, name=f"wav-{self.path.stem}", daemon=True
        )
        self._thread.start()

    def write(self, samples: np.ndarray) -> None:
        if self._thread is not None:
            self._coda.put(samples)

    def _scrivi(self) -> None:
        while True:
            blocco = self._coda.get()
            if blocco is None:
                break
            try:
                # Da float [-1, 1] a interi a 16 bit. Il taglio evita che un
                # picco oltre il fondoscala si trasformi in un crepitio.
                pcm = np.clip(blocco, -1.0, 1.0)
                assert self._file is not None
                self._file.writeframes((pcm * 32767).astype(np.int16).tobytes())
                self._campioni += len(blocco)
            except Exception as exc:  # pragma: no cover
                log.warning("Scrittura audio non riuscita su %s: %s", self.path.name, exc)

    def stop(self) -> Path | None:
        """Chiude il file e restituisce il percorso, o None se non c'è nulla."""
        if self._thread is None:
            return None
        self._coda.put(None)
        self._thread.join(timeout=30)
        self._thread = None

        if self._file is not None:
            with contextlib.suppress(Exception):
                self._file.close()
            self._file = None

        if self._campioni == 0:
            # Un file vuoto confonde e basta: sembra che l'audio ci sia.
            with contextlib.suppress(Exception):
                self.path.unlink()
            return None
        return self.path

    @property
    def durata_s(self) -> float:
        return self._campioni / SAMPLE_RATE
