"""Il pezzo comune ai motori di trascrizione locali, che sono due.

Parakeet trascrive dal vivo perché è l'unico abbastanza veloce da starci
dietro; Canary rifinisce a call finita perché è più preciso e — soprattutto —
la lingua gliela si può imporre. Le due classi cambiano in tre punti: quale
modello caricano, come si chiamano, e se il parametro `language` lo leggono
davvero. Tutto il resto — la segmentazione sui silenzi, il VAD, il lock —
è identico, e sta qui.

Misurato su questa macchina, su 159 s di parlato italiano (FLEURS dev):

    modello                 RTFx     WER    finestra da 5 s
    Parakeet TDT 0.6B v3   15.2x    6.8%             382 ms
    Canary 1B v2            6.1x    5.3%             696 ms

Con due tracce serializzate e un passo da un secondo, il budget è 500 ms a
traccia: da qui la divisione dei compiti, che non è una preferenza.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
# I modelli degradano oltre i ~30 s per chiamata: la segmentazione non è un
# dettaglio implementativo, è un requisito.
MAX_CHUNK_S = 25.0


class MotoreOnnx:
    """Wrapper su un modello onnx-asr, utilizzabile da più thread.

    Le due tracce di una call vengono trascritte in parallelo, ma la sessione
    ONNX non è pensata per chiamate concorrenti sullo stesso oggetto: un lock
    serializza le inferenze. Serializzare è più prudente che tenere due copie
    del modello in RAM.
    """

    MODEL_ID: str = ""
    name: str = ""
    # Se il modello legge davvero il parametro `language`. Falso per le
    # famiglie transducer: onnx-asr accetta il parametro e lo scarta senza
    # dirlo (vedi `parakeet.py`).
    lingua_imponibile: bool = False

    def __init__(
        self, *, quantization: str | None = "int8", model_dir: Path | None = None
    ) -> None:
        import onnx_asr

        self.quantization = quantization
        self._lock = threading.Lock()
        self._model = onnx_asr.load_model(
            self.MODEL_ID,
            path=str(model_dir) if model_dir else None,
            quantization=quantization,
        )
        self._vad = None

    # ------------------------------------------------------------ inferenza

    def transcribe(self, audio: np.ndarray, *, language: str | None = None) -> str:
        if audio.size == 0:
            return ""
        # Il parametro si passa solo a chi lo legge. Passarlo agli altri non
        # dà errore — ed è esattamente il motivo per cui è rimasto lì per
        # mesi a non fare niente mentre sembrava di aver scelto la lingua.
        kwargs = {"language": language} if (language and self.lingua_imponibile) else {}
        with self._lock:
            result = self._model.recognize(audio, sample_rate=SAMPLE_RATE, **kwargs)
        return (result or "").strip()

    def transcribe_segmented(
        self, audio: np.ndarray, *, language: str | None = None
    ) -> list[tuple[int, int, str]]:
        """Trascrive audio lungo spezzandolo sui silenzi.

        Il VAD trova i confini reali fra le frasi, così nessun segmento supera
        il limite del modello e i tagli non cadono in mezzo a una parola.
        Restituisce `(inizio_ms, fine_ms, testo)`, con gli istanti riferiti
        **all'audio che gli è stato passato** — non all'orologio della call.
        """
        if audio.size == 0:
            return []

        spans = self._parlato(audio)
        out: list[tuple[int, int, str]] = []
        for start, end in self._split_long(spans):
            text = self.transcribe(audio[start:end], language=language)
            if text:
                out.append((start * 1000 // SAMPLE_RATE, end * 1000 // SAMPLE_RATE, text))
        return out

    @staticmethod
    def _split_long(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Spezza i tratti di parlato troppo lunghi per il modello.

        Chi parla a lungo senza pause abbastanza nette produce un unico segmento
        di minuti: va diviso comunque, altrimenti il modello lo tronca.
        """
        limit = int(MAX_CHUNK_S * SAMPLE_RATE)
        out: list[tuple[int, int]] = []
        for start, end in spans:
            while end - start > limit:
                out.append((start, start + limit))
                start += limit
            if end > start:
                out.append((start, end))
        return out

    # ------------------------------------------------------------------ VAD

    def _parlato(self, audio: np.ndarray) -> list[tuple[int, int]]:
        import onnx_asr

        with self._lock:
            if self._vad is None:
                self._vad = onnx_asr.load_vad("silero")
            segments = next(
                self._vad.segment_batch(
                    audio[np.newaxis, :],
                    np.array([len(audio)], dtype=np.int64),
                    SAMPLE_RATE,
                )
            )
            return [(int(a), int(b)) for a, b in segments]

    def has_speech(self, audio: np.ndarray) -> bool:
        """Dice se in questo tratto qualcuno sta parlando.

        Serve a capire quando una frase è finita. Si usa Silero invece di una
        soglia di energia perché sulla traccia di sistema qualunque rumore —
        una notifica, il fruscio di fondo — supererebbe la soglia e la frase
        non verrebbe mai chiusa.
        """
        if audio.size == 0:
            return False
        return bool(self._parlato(audio))
