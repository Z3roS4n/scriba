"""Il motore che trascrive dal vivo: Parakeet via ONNX Runtime.

Gira su CPU e non richiede CUDA, il che su una macchina AMD è l'unica strada
praticabile — e lascia comunque la GPU libera per l'LLM.

Misurato su Ryzen 5 5600G: 15.2x realtime su parlato italiano (FLEURS dev),
382 ms su finestre da 5 s. È l'unico dei due modelli locali che sta dentro il
budget della trascrizione in tempo reale.

## La lingua, qui, non si può imporre

`stt.lingua` arriva fin quaggiù e **non viene letta**. Non è una dimenticanza
nostra: onnx-asr accetta `language` per qualunque modello e lo onora solo per
Whisper e Canary — «Speech language (only for Whisper and Canary models)» —
mentre `nemo-parakeet-tdt-0.6b-v3` si risolve in `NemoConformerTdt`, la cui
decodifica dai kwargs legge solo `need_logprobs`.

Verificato sul modello installato: `language='zz-non-esiste'` non solleva
niente, dove Whisper e Canary darebbero `KeyError: '<|zz-non-esiste|>'`.

Parakeet v3 è multilingue su 25 lingue europee e la lingua se la deduce
dall'audio a ogni chiamata: sulle finestre corte della trascrizione dal vivo
sbaglia, ed è da lì che vengono le frasi in spagnolo dentro una call italiana
(#41). Per questo `lingua_imponibile` è False e il parametro non viene nemmeno
passato: un parametro che sembra funzionare è peggio di uno che non c'è.
"""

from __future__ import annotations

from .motore_onnx import MAX_CHUNK_S, SAMPLE_RATE, MotoreOnnx  # noqa: F401  (API storica)

MODEL_ID = "nemo-parakeet-tdt-0.6b-v3"


def scarica_modello(*, quantization: str | None = "int8") -> None:
    """Forza l'acquisizione dei pesi, senza tenere in RAM la sessione dopo.

    `ParakeetEngine.__init__` fa la stessa chiamata al primo utilizzo reale;
    questa esiste per «Modelli locali», così chi vuole può scaricare i ~640 MB
    prima di aprire la prima call invece di scoprirlo a metà della prima
    trascrizione. onnx-asr scarica, mette in cache e costruisce comunque una
    sessione ONNX in un solo passaggio — non espone un download "puro"
    separato dal caricamento — quindi il modello resta in memoria per il
    tempo di questa chiamata e va in garbage collection subito dopo.

    `quantization` è tenuto uguale al default di `ParakeetEngine`: scaricare
    pesi diversi da quelli che l'app userà davvero sarebbe un download inutile.
    """
    import onnx_asr

    onnx_asr.load_model(MODEL_ID, quantization=quantization)


class ParakeetEngine(MotoreOnnx):
    MODEL_ID = MODEL_ID
    name = "parakeet-tdt-0.6b-v3"
    lingua_imponibile = False
