"""Confronta la trascrizione con il testo che era da leggere e calcola il WER.

Il WER da solo dice poco: 8% di errore fatto di articoli sbagliati è innocuo,
8% fatto di cifre e nomi propri rovina l'estrazione delle task. Per questo lo
script stampa anche l'elenco delle differenze, che è la parte che serve
davvero a decidere.

Uso:
    python spikes/score_stt.py [riferimento.txt] [audio.wav]
"""

from __future__ import annotations

import re
import sys
import unicodedata
import wave
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "out"
MODEL = "nemo-parakeet-tdt-0.6b-v3"
TARGET_RATE = 16_000


def normalize(text: str) -> list[str]:
    """Minuscole, senza punteggiatura e senza accenti: confronta le parole, non la resa grafica."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text)
    return text.split()


def levenshtein_ops(ref: list[str], hyp: list[str]) -> tuple[int, int, int, list[tuple[str, str, str]]]:
    """Distanza di edit fra parole, con il dettaglio delle operazioni."""
    n, m = len(ref), len(hyp)
    d = np.zeros((n + 1, m + 1), dtype=np.int32)
    d[:, 0] = np.arange(n + 1)
    d[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + cost)

    # Ripercorro la matrice per capire *quali* parole sono sbagliate.
    ops: list[tuple[str, str, str]] = []
    sub = dele = ins = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hyp[j - 1] and d[i, j] == d[i - 1, j - 1]:
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and d[i, j] == d[i - 1, j - 1] + 1:
            ops.append(("sostituzione", ref[i - 1], hyp[j - 1]))
            sub += 1
            i, j = i - 1, j - 1
        elif i > 0 and d[i, j] == d[i - 1, j] + 1:
            ops.append(("mancante", ref[i - 1], "—"))
            dele += 1
            i -= 1
        else:
            ops.append(("aggiunta", "—", hyp[j - 1]))
            ins += 1
            j -= 1
    return sub, dele, ins, list(reversed(ops))


def load_mono16k(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wf:
        rate, channels = wf.getframerate(), wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != TARGET_RATE:
        from math import gcd

        from scipy.signal import resample_poly

        g = gcd(rate, TARGET_RATE)
        audio = resample_poly(audio, TARGET_RATE // g, rate // g)
    return audio.astype(np.float32)


def main() -> int:
    ref_path = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "sample_it.txt"
    wav_path = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT / "sample_it.wav"

    if not ref_path.exists() or not wav_path.exists():
        print("Mancano il riferimento o l'audio. Esegui prima:")
        print("  python spikes/record_sample.py")
        return 1

    import onnx_asr

    print(f"Carico {MODEL}...")
    model = onnx_asr.load_model(MODEL, quantization="int8")

    audio = load_mono16k(wav_path)
    print(f"Trascrivo {len(audio) / TARGET_RATE:.1f}s...\n")
    hyp_text = model.recognize(audio, sample_rate=TARGET_RATE, language="it")

    ref_text = ref_path.read_text(encoding="utf-8")
    ref, hyp = normalize(ref_text), normalize(hyp_text)

    print("--- Trascrizione ---")
    print(hyp_text)
    print()

    # Se chi registra parla a braccio invece di leggere il testo proposto, il
    # WER esce sopra il 100% e non misura più il modello: misura il fatto che si
    # stanno confrontando due discorsi diversi. Meglio dirlo che stampare un
    # numero privo di senso.
    comuni = len(set(ref) & set(hyp))
    sovrapposizione = comuni / len(set(ref)) if ref else 0.0
    if sovrapposizione < 0.45:
        print("--- Attenzione ---")
        print(f"Solo il {sovrapposizione * 100:.0f}% delle parole del riferimento compare nella")
        print("trascrizione: quello che è stato detto non è il testo di riferimento.")
        print("Il WER qui sotto non misura la qualità del modello.\n")
        print("Per un numero valido, rileggi il testo mostrato da record_sample.py.")
        print("Per valutare comunque a occhio, guarda la trascrizione qui sopra:")
        print("nomi propri, numeri e date sono le cose che contano.\n")
        return 2

    sub, dele, ins, ops = levenshtein_ops(ref, hyp)
    errors = sub + dele + ins
    wer = errors / len(ref) * 100 if ref else float("nan")

    print("--- WER ---")
    print(f"  parole di riferimento : {len(ref)}")
    print(f"  sostituzioni          : {sub}")
    print(f"  mancanti              : {dele}")
    print(f"  aggiunte              : {ins}")
    print(f"  WER                   : {wer:.1f}%\n")

    if ops:
        print("--- Differenze ---")
        for kind, a, b in ops[:40]:
            print(f"  {kind:<13} {a:<20} -> {b}")
        if len(ops) > 40:
            print(f"  ... e altre {len(ops) - 40}")
        print()

    print("--- Esito ---")
    if wer <= 10.0:
        print(f"[OK] WER {wer:.1f}%: utilizzabile per riassunto ed estrazione task.")
        return 0
    print(f"[X] WER {wer:.1f}%: troppo alto. Controlla il microfono, poi valuta il")
    print("    modello non quantizzato (--quantization vuoto) o il path API.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
