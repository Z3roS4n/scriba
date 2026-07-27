"""Registra un campione di italiano letto, per misurare la qualità dello STT.

Sulla macchina non c'è una voce TTS italiana, quindi il throughput è stato
misurato su audio inglese sintetico. Quello dice quanto è veloce il modello, non
quanto capisce l'italiano parlato da te, col tuo microfono.

Questo script mostra un testo da leggere ad alta voce e lo registra. Il testo è
noto, quindi diventa il riferimento per calcolare il WER: si confronta ciò che il
modello ha scritto con ciò che era da leggere.

Il testo contiene di proposito le cose che in una call vera fanno sbagliare i
modelli: numeri, date, sigle, nomi propri e qualche parola inglese in mezzo
all'italiano.

Uso:
    python spikes/record_sample.py
    python spikes/bench_stt.py spikes/out/sample_it.wav
    python spikes/score_stt.py
"""

from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "out"
RATE = 48_000

TESTO = """
Allora, riepilogo quello che ci siamo detti nella riunione di martedì.
Il primo punto è la migrazione del database clienti, che deve chiudersi entro il
quattordici settembre. Marco ha sollevato un dubbio sulla finestra di fermo
macchina e propone di spostarla nel weekend, quindi sabato notte.
Secondo punto: il team di design ha portato tre proposte per il redesign della
dashboard. Abbiamo scelto la seconda, però la palette va rivista perché il
contrasto non passa le linee guida di accessibilità.
Sofia prepara il dettaglio dei costi prima del prossimo incontro, con il budget
diviso per trimestre. Parliamo di circa quarantaduemila euro, IVA esclusa.
Ultima cosa, le assunzioni restano in sospeso finché non arriva l'approvazione
dal CDA, probabilmente a inizio ottobre.
"""


def main() -> int:
    import pyaudiowpatch as pyaudio

    parole = len(TESTO.split())
    # A ~150 parole al minuto, con un margine per le pause naturali.
    stimati = int(parole / 150 * 60 * 1.35)

    print("=" * 72)
    print("Leggi ad alta voce il testo qui sotto, con calma e a volume normale.")
    print(f"Sono {parole} parole: circa {stimati} secondi.")
    print("=" * 72)
    print(TESTO)
    print("=" * 72)
    print(f"\nRegistrazione di {stimati}s. Premi INVIO quando sei pronto...")
    input()

    with pyaudio.PyAudio() as pa:
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        mic = pa.get_device_info_by_index(wasapi["defaultInputDevice"])
        channels = int(mic["maxInputChannels"])
        rate = int(mic["defaultSampleRate"])
        print(f"Microfono: {mic['name']}\n")

        blocks: list[np.ndarray] = []
        stream = pa.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=mic["index"],
            frames_per_buffer=1024,
        )
        print("REGISTRO — parla ora.\n")
        t0 = time.perf_counter()
        try:
            while time.perf_counter() - t0 < stimati:
                data = stream.read(1024, exception_on_overflow=False)
                blocks.append(np.frombuffer(data, dtype=np.float32).reshape(-1, channels))
                elapsed = time.perf_counter() - t0
                print(f"\r  {elapsed:5.1f}s / {stimati}s ", end="", flush=True)
        except KeyboardInterrupt:
            print("\nFermato.")
        finally:
            stream.stop_stream()
            stream.close()

    audio = np.concatenate(blocks, axis=0).mean(axis=1)
    peak = float(np.abs(audio).max())
    print(f"\n\nPicco: {peak:.3f}", end="")
    if peak < 0.02:
        print("  [!] troppo basso, il microfono ha preso poco o niente")
    elif peak > 0.99:
        print("  [!] in saturazione, abbassa il volume del microfono")
    else:
        print("  ok")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "sample_it.wav"
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())

    (OUT / "sample_it.txt").write_text(TESTO.strip(), encoding="utf-8")
    print(f"\nScritto: {path}  ({len(audio) / rate:.1f}s)")
    print("\nOra:")
    print("  python spikes/bench_stt.py spikes/out/sample_it.wav")
    print("  python spikes/score_stt.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
