"""Verifica che la timeline ricostruita di system.wav sia fedele.

Lo spike di cattura riproduce un bip di 1s ogni 2s. Se la timeline è corretta,
gli attacchi dei bip devono cadere a distanza di 2.000s l'uno dall'altro: uno
scarto crescente segnala che i silenzi sono stati collassati e che tutto ciò che
viene dopo è fuori sincrono.

Uso:
    python spikes/verify_alignment.py [spikes/out/system.wav]
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

EXPECTED_PERIOD_S = 2.0


def load_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0, rate


def find_onsets(mono: np.ndarray, rate: int, frame_ms: float = 10.0) -> np.ndarray:
    """Istanti in cui il segnale passa da silenzio a suono."""
    hop = int(rate * frame_ms / 1000.0)
    n = len(mono) // hop
    energy = np.array([np.sqrt(np.mean(mono[i * hop : (i + 1) * hop] ** 2)) for i in range(n)])
    if energy.max() < 1e-4:
        return np.array([])

    loud = energy > (energy.max() * 0.25)
    # Un attacco è un passaggio da "silenzio" a "suono": prendo i fronti di salita.
    edges = np.flatnonzero(np.diff(loud.astype(np.int8)) == 1) + 1
    return edges * hop / rate


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "out" / "system.wav"
    if not path.exists():
        print(f"File non trovato: {path}\nEsegui prima: python spikes/audio_capture.py --tone")
        return 1

    mono, rate = load_mono(path)
    print(f"{path.name}: {len(mono) / rate:.3f}s @ {rate} Hz\n")

    onsets = find_onsets(mono, rate)
    if len(onsets) < 3:
        print(f"Trovati solo {len(onsets)} attacchi: servono almeno 3 bip per valutare.")
        return 1

    gaps = np.diff(onsets)
    # In modalità --gap c'è un silenzio voluto in mezzo: quell'intervallo non è
    # un errore di allineamento e va misurato a parte, non mediato con gli altri.
    is_pause = gaps > (EXPECTED_PERIOD_S * 1.5)
    beat_gaps = gaps[~is_pause]
    errors_ms = (beat_gaps - EXPECTED_PERIOD_S) * 1000.0

    print(f"Attacchi rilevati: {len(onsets)}")
    print("  " + "  ".join(f"{t:.3f}s" for t in onsets[:14]))

    if is_pause.any():
        for idx in np.flatnonzero(is_pause):
            print(f"\nPausa voluta: {onsets[idx]:.3f}s -> {onsets[idx + 1]:.3f}s  ({gaps[idx]:.3f}s)")

    if len(beat_gaps) == 0:
        print("\nNessun intervallo regolare da valutare.")
        return 1

    print(f"\nIntervallo atteso fra i bip: {EXPECTED_PERIOD_S:.3f}s  ({len(beat_gaps)} intervalli)")
    print(f"  medio    : {beat_gaps.mean():.3f}s  ({errors_ms.mean():+.1f} ms)")
    worst_i = int(np.argmax(np.abs(errors_ms)))
    print(f"  peggiore : {beat_gaps[worst_i]:.3f}s  ({errors_ms[worst_i]:+.1f} ms)")

    # Lo scarto che conta è quello cumulato: un errore che cresce nel tempo
    # sposta le parole di fine call, non quelle di inizio.
    cumulative_ms = float(errors_ms.sum())
    print(f"\nScarto cumulato sui tratti continui: {cumulative_ms:+.1f} ms")

    worst = float(np.max(np.abs(errors_ms)))
    if worst > 50.0:
        print(f"\n[X] Un intervallo sbaglia di {worst:.1f} ms: la timeline non è fedele.")
        return 1

    print("\n[OK] Gli intervalli fra i bip sono corretti: la timeline regge.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
