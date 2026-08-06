"""Il motore che rifinisce a call finita: Canary via ONNX Runtime.

Esiste per una cosa sola che Parakeet non sa fare: **accettare la lingua**.
Verificato sul modello installato, sulla stessa clip italiana:

    language='it'             -> 'La parte settentrionale, conosciuta come...'
    language='es'             -> 'La parte septentrional, conocida como...'
    language='zz-non-esiste'  -> KeyError: '<|zz-non-esiste|>'

Il `KeyError` è la prova che il token viene davvero cercato e inserito. Su
Parakeet le stesse tre chiamate davano tutte lo stesso risultato.

In più è più preciso: WER 5.3% contro 6.8% su FLEURS italiano, misurati
identici sulla stessa macchina.

## Perché non sostituisce Parakeet

Perché è 2,5 volte più lento, e la trascrizione dal vivo non ha quel margine:

    frase in corso   Parakeet    Canary     (budget: 500 ms a traccia)
             3 s      240 ms    425 ms
             5 s      382 ms    696 ms   <- gia' fuori
            10 s      641 ms   1723 ms
            15 s     1089 ms   3086 ms

Lo streaming ritrascrive l'intera frase in corso a ogni passo, su due tracce
serializzate da un lock: con Canary i provvisori arriverebbero in ritardo da
cinque secondi di frase in poi, cioè quasi sempre. Sta invece dove nessuno
aspetta — `stt/rifinitura.py`, a registrazione conclusa.

Il modello traduce, oltre a trascrivere. `onnx_asr` usa `target_language`
uguale a `language` quando non gli si dice altro, che è quello che serve qui:
trascrivere, non tradurre.
"""

from __future__ import annotations

from .motore_onnx import MotoreOnnx

MODEL_ID = "nemo-canary-1b-v2"


def scarica_modello(*, quantization: str | None = "int8") -> None:
    """Acquisisce i pesi (~1 GB) senza tenerli in RAM dopo.

    Come per Parakeet: onnx-asr non separa il download dal caricamento, quindi
    il modello resta in memoria il tempo di questa chiamata. La quantizzazione
    è la stessa che userà `CanaryEngine`, altrimenti sarebbe un download di
    pesi che non verranno mai usati.
    """
    import onnx_asr

    onnx_asr.load_model(MODEL_ID, quantization=quantization)


class CanaryEngine(MotoreOnnx):
    MODEL_ID = MODEL_ID
    name = "canary-1b-v2"
    lingua_imponibile = True
