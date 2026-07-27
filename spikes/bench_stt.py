"""Spike Fase 2 — quanto è veloce Parakeet su questa macchina.

Il piano si basa su una stima (RTFx 10-15 su CPU) presa da un benchmark fatto su
un 9800X3D. Questa macchina ha un 5600G, che è un'altra cosa. Prima di costruirci
sopra lo streaming va misurato davvero.

Servono due numeri distinti:

- **RTFx**: quanti secondi di audio si trascrivono in un secondo. Deve stare
  sopra 3 perché le tracce da trascrivere sono due, in parallelo, mentre la call
  è in corso.
- **Latenza per finestra**: quanto passa fra "hai finito di parlare" e "il testo
  compare". È quella che l'utente percepisce, e nessun RTFx alto la salva se le
  finestre sono lunghe.

Uso:
    python spikes/bench_stt.py spikes/out/sample.wav
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
import wave
from pathlib import Path

import numpy as np

MODEL = "nemo-parakeet-tdt-0.6b-v3"
TARGET_RATE = 16_000


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path, help="file audio da trascrivere")
    parser.add_argument("--quantization", default="int8", help="int8 (default) oppure vuoto per fp32")
    parser.add_argument("--window", type=float, default=3.0, help="finestra di streaming in secondi")
    parser.add_argument("--hop", type=float, default=1.0, help="passo fra due finestre")
    args = parser.parse_args()

    if not args.wav.exists():
        print(f"File non trovato: {args.wav}")
        return 1

    import onnx_asr

    print(f"Carico {MODEL} (quantization={args.quantization or 'fp32'})...")
    t = time.perf_counter()
    model = onnx_asr.load_model(MODEL, quantization=args.quantization or None)
    load_s = time.perf_counter() - t
    print(f"  caricato in {load_s:.1f}s\n")

    audio = load_mono16k(args.wav)
    duration = len(audio) / TARGET_RATE
    print(f"Audio: {args.wav.name} — {duration:.1f}s\n")

    # --- Passata completa: è il numero che dice se la macchina ce la fa ---
    print("--- Trascrizione completa ---")
    t = time.perf_counter()
    text = model.recognize(audio, sample_rate=TARGET_RATE)
    full_s = time.perf_counter() - t
    rtfx = duration / full_s if full_s > 0 else float("inf")
    print(f"  tempo   : {full_s:.2f}s")
    print(f"  RTFx    : {rtfx:.1f}x")
    print(f"  testo   : {text[:400]}{'...' if len(text) > 400 else ''}\n")

    # --- Simulazione streaming: è il numero che l'utente percepisce ---
    print(f"--- Streaming simulato (finestra {args.window}s, passo {args.hop}s) ---")
    win = int(args.window * TARGET_RATE)
    hop = int(args.hop * TARGET_RATE)
    latencies: list[float] = []
    for start in range(0, max(len(audio) - win, 1), hop):
        chunk = audio[start : start + win]
        if len(chunk) < TARGET_RATE // 2:  # meno di mezzo secondo: non significativo
            break
        t = time.perf_counter()
        model.recognize(chunk, sample_rate=TARGET_RATE)
        latencies.append(time.perf_counter() - t)

    if not latencies:
        print("  audio troppo corto per simulare lo streaming\n")
    else:
        mediana = statistics.median(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95) - 1] if len(latencies) > 1 else latencies[0]
        print(f"  finestre elaborate : {len(latencies)}")
        print(f"  latenza mediana    : {mediana * 1000:.0f} ms")
        print(f"  latenza p95        : {p95 * 1000:.0f} ms")
        # Per stare dietro al parlato ogni finestra deve costare meno del passo.
        margine = args.hop / mediana if mediana > 0 else float("inf")
        print(f"  margine sul passo  : {margine:.1f}x")
        print()

    print("--- Esito ---")
    ok = True
    if rtfx < 3.0:
        print(f"[X] RTFx {rtfx:.1f}x: sotto 3x non si reggono due tracce in parallelo.")
        ok = False
    else:
        print(f"[OK] RTFx {rtfx:.1f}x — margine sufficiente per due tracce.")

    if latencies:
        # Con due tracce ogni finestra viene elaborata due volte per passo.
        if statistics.median(latencies) * 2 > args.hop:
            print(f"[X] Con due tracce la latenza mediana supera il passo di {args.hop}s: la coda cresce.")
            ok = False
        else:
            print(f"[OK] Due tracce stanno dentro il passo di {args.hop}s.")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
