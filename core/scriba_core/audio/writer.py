"""Salva su disco l'audio della call, una traccia per sorgente.

Senza i file, una call è irripetibile: se la trascrizione viene male — modello
sbagliato, lingua sbagliata, un pezzo perso — non c'è modo di rifarla, e non si
può nemmeno provare a distinguere chi ha parlato. Il parlato è passato e non
torna.

Si scrive quello che è già stato convertito per la trascrizione: mono a 16 kHz.
Basta per ritrascrivere e per l'analisi delle voci, e occupa un ventesimo
dell'originale — mezz'ora di call sono circa 55 MB per traccia invece di oltre
un gigabyte.

## Il silenzio si scrive

Ogni blocco porta l'istante della call a cui appartiene, e il file lo rispetta:
dove non è arrivato niente si scrivono zeri. Non è zelo — è ciò che rende il
file utilizzabile per lo scopo dichiarato qui sopra.

Il loopback WASAPI **non consegna pacchetti** mentre nessuna applicazione
riproduce audio. Scrivendo di seguito quello che arriva, i silenzi sparivano e
il file diventava più corto della call: misurato su una registrazione vera,
-21.7%, ventiquattro minuti mancanti. Ogni istante scritto nella trascrizione
puntava, dentro quel file, a un punto diverso da quello giusto — e lo scarto
cresceva lungo la call. Ritrascrivere una singola frase era impossibile.

Il riallineamento è quello deciso in D-006, e finora era rimasto nella
misurazione senza arrivare fin qui: **contiguo finché i blocchi arrivano di
seguito, salto alla posizione assoluta quando la consegna si interrompe oltre
50 ms**. Posizionare ogni blocco in modo assoluto lascerebbe micro-buchi di
~1 ms per blocco, che si sentono come click; concatenare e basta accumula
l'errore. L'ibrido non ha nessuno dei due difetti.
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

# Sotto questo scarto il blocco si scrive di seguito al precedente invece che
# alla sua posizione assoluta. È la soglia di D-006: più in basso si
# inseguirebbero i millisecondi di jitter fra una consegna e l'altra, lasciando
# micro-buchi udibili; più in alto un vero buco verrebbe scambiato per jitter.
SOGLIA_BUCO_MS = 50

# Il silenzio si scrive a pezzi: un buco di ventiquattro minuti sono 46 MB, e
# non c'è motivo di costruirli tutti in memoria in una volta.
PEZZO_SILENZIO_S = 10


class TrackWriter:
    """Scrive una traccia su file, senza far aspettare chi cattura.

    I blocchi arrivano dal thread della scheda audio, che non si può bloccare:
    finiscono in coda e un thread suo li scrive. Una scrittura lenta fa crescere
    la coda, non perdere audio.

    Ogni blocco porta l'istante della call a cui appartiene, ed è quello a
    decidere dove finisce nel file: vedi la nota in testa al modulo.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # `(campioni, t_ms)`. Con `campioni = None` il blocco non porta audio:
        # chiede solo di portare il file fino a quell'istante.
        self._coda: queue.Queue[tuple[np.ndarray | None, int] | None] = queue.Queue()
        self._file: wave.Wave_write | None = None
        self._thread: threading.Thread | None = None
        self._campioni = 0
        self._silenzio = 0

    def start(self) -> None:
        self._file = wave.open(str(self.path), "wb")
        self._file.setnchannels(1)
        self._file.setsampwidth(2)  # PCM 16 bit
        self._file.setframerate(SAMPLE_RATE)
        self._thread = threading.Thread(
            target=self._scrivi, name=f"wav-{self.path.stem}", daemon=True
        )
        self._thread.start()

    def write(self, samples: np.ndarray, t_ms: int) -> None:
        """Accoda un blocco, con l'istante della call a cui appartiene."""
        if self._thread is not None:
            self._coda.put((samples, t_ms))

    def porta_fino_a(self, t_ms: int) -> None:
        """Allunga il file con silenzio fino a questo istante.

        Si chiama a fine registrazione. Senza, una traccia che smette di
        consegnare cinque minuti prima della fine produce un file più corto
        della call — e chi lo confronta con `durata_ms` per orientarsi dentro
        conclude che è disallineato, quando invece lo è solo in coda.
        """
        if self._thread is not None:
            self._coda.put((None, t_ms))

    def _scrivi(self) -> None:
        while True:
            blocco = self._coda.get()
            if blocco is None:
                break
            campioni, t_ms = blocco
            try:
                self._colma(t_ms)
                if campioni is None or len(campioni) == 0:
                    continue
                # Da float [-1, 1] a interi a 16 bit. Il taglio evita che un
                # picco oltre il fondoscala si trasformi in un crepitio.
                pcm = np.clip(campioni, -1.0, 1.0)
                assert self._file is not None
                self._file.writeframes((pcm * 32767).astype(np.int16).tobytes())
                self._campioni += len(campioni)
            except Exception as exc:  # pragma: no cover
                log.warning("Scrittura audio non riuscita su %s: %s", self.path.name, exc)

    def _colma(self, t_ms: int) -> None:
        """Riempie di silenzio fra dov'è arrivato il file e dove va questo blocco.

        Solo se il buco supera la soglia: sotto, il blocco si scrive di seguito
        e i millisecondi di scarto restano dove sono. Un blocco che risulta
        *prima* di dove siamo — capita, l'orologio non è perfetto — non fa
        tornare indietro nessuno: si accoda e basta.
        """
        atteso = t_ms * SAMPLE_RATE // 1000
        mancano = atteso - self._campioni
        if mancano < SOGLIA_BUCO_MS * SAMPLE_RATE // 1000:
            return

        assert self._file is not None
        pezzo = PEZZO_SILENZIO_S * SAMPLE_RATE
        zeri = np.zeros(min(mancano, pezzo), dtype=np.int16).tobytes()
        scritti = 0
        while scritti < mancano:
            quanti = min(pezzo, mancano - scritti)
            self._file.writeframes(zeri[: quanti * 2])
            scritti += quanti
        self._campioni += mancano
        self._silenzio += mancano

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

        if self._campioni - self._silenzio == 0:
            # Niente di catturato: solo il silenzio che ci abbiamo messo noi.
            # Si cancella — un file confonde e basta, sembra che l'audio ci sia
            # — e per una call di un'ora sarebbero 115 MB di zeri.
            #
            # Il confronto è sul catturato, non sul totale: da quando i buchi
            # vengono riempiti, `_campioni` è quasi sempre diverso da zero anche
            # su una traccia che non ha mai consegnato niente.
            with contextlib.suppress(Exception):
                self.path.unlink()
            return None
        return self.path

    @property
    def durata_s(self) -> float:
        return self._campioni / SAMPLE_RATE

    @property
    def silenzio_ricostruito_s(self) -> float:
        """Quanto di questo file è silenzio scritto da noi, non catturato.

        Su una traccia di sistema è normale che sia parecchio: è il tempo in cui
        nessuno stava riproducendo niente. Su un microfono, invece, dovrebbe
        essere quasi zero — se non lo è, quella scheda audio sta perdendo
        blocchi, e vale la pena saperlo.
        """
        return self._silenzio / SAMPLE_RATE
