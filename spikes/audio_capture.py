"""Spike Fase 1 — cattura simultanea di microfono e audio di sistema.

Valida l'ipotesi su cui poggia tutto il progetto: si possono tenere due tracce
audio separate ("io" dal mic, "loro" dal loopback) allineate nel tempo, senza
mixarle e senza che derivino l'una dall'altra.

Le due tracce hanno clock hardware diversi, quindi contare i campioni per sapere
"a che punto siamo" è sbagliato: si accumulano decine di ms di sfasamento per
ora. Ogni chunk viene quindi marcato con l'orologio monotonico del processo, che
è la stessa timeline che poi userà tutto il resto dell'app.

Uso:
    python spikes/audio_capture.py [--seconds 60]

Criterio di successo: drift < 100 ms su 60 secondi, e ciascun WAV contiene la
voce che ci si aspetta (mic.wav la tua, system.wav quella degli altri).
"""

from __future__ import annotations

import argparse
import queue
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyaudiowpatch as pyaudio
from scipy.signal import resample_poly

TARGET_RATE = 16_000  # quello che si aspetta il modello STT
OUT_DIR = Path(__file__).resolve().parent / "out"


@dataclass
class Chunk:
    """Un blocco di campioni con il momento in cui è arrivato."""

    t_recv: float  # perf_counter alla consegna del callback
    data: np.ndarray  # float32, shape (frames, channels)


@dataclass
class Track:
    """Una sorgente audio catturata in modo indipendente."""

    name: str
    device_index: int
    channels: int
    rate: int
    chunks: queue.Queue[Chunk] = field(default_factory=queue.Queue)
    stream: object | None = None
    first_t: float | None = None
    n_frames: int = 0

    # Coppie (istante di arrivo, campioni cumulati): servono a misurare il
    # rapporto fra il clock della scheda audio e l'orologio del processo.
    clock_samples: list[tuple[float, int]] = field(default_factory=list)

    def callback(self, in_data, frame_count, time_info, status):  # noqa: ANN001, ARG002
        now = time.perf_counter()
        if self.first_t is None:
            self.first_t = now
        samples = np.frombuffer(in_data, dtype=np.float32).reshape(-1, self.channels)
        self.n_frames += samples.shape[0]
        self.clock_samples.append((now, self.n_frames))
        self.chunks.put(Chunk(t_recv=now, data=samples.copy()))
        return (None, pyaudio.paContinue)

    def clock_ratio(self) -> tuple[float, float]:
        """Rapporto fra tempo audio e tempo reale, e drift estrapolato a 1 ora.

        Confrontare "campioni totali" con "durata della registrazione" non
        funziona: allo stop il driver svuota i buffer e regala centinaia di ms
        che non sono drift. La pendenza della retta campioni/tempo, calcolata su
        centinaia di punti, ignora sia quel transitorio sia il jitter di
        scheduling e isola il vero scarto fra i due clock.
        """
        if len(self.clock_samples) < 10:
            return float("nan"), float("nan")

        t_all = np.array([c[0] for c in self.clock_samples])
        n_all = np.array([c[1] for c in self.clock_samples], dtype=np.float64) / self.rate

        # Le pause in cui il device smette di consegnare non sono drift: vanno
        # escluse, altrimenti dominano la pendenza. Si misura sul tratto
        # continuo più lungo.
        deltas = np.diff(t_all)
        expected = np.diff(n_all)
        contiguous = deltas < (expected + 0.050)

        best_len, best = 0, (0, len(t_all))
        run_start = 0
        for i in range(len(contiguous) + 1):
            if i == len(contiguous) or not contiguous[i]:
                if (i - run_start) > best_len:
                    best_len, best = i - run_start, (run_start, i + 1)
                run_start = i + 1

        lo, hi = best
        if hi - lo < 10:
            return float("nan"), float("nan")

        t = t_all[lo:hi] - t_all[lo]
        n = n_all[lo:hi] - n_all[lo]
        slope = float(np.polyfit(t, n, 1)[0])
        return slope, (slope - 1.0) * 3600.0 * 1000.0

    def collect(self, t0: float, duration_s: float) -> tuple[np.ndarray, list[float], float]:
        """Ricostruisce la timeline posizionando ogni chunk in modo assoluto.

        Il loopback WASAPI non consegna nulla mentre nessuna applicazione
        riproduce audio: concatenare i chunk collasserebbe i silenzi e
        anticiperebbe tutto ciò che viene dopo. Si potrebbe reinserire il buco
        misurando la distanza fra due arrivi, ma quell'errore si somma a ogni
        pausa e a fine call sono secondi.

        La soluzione è ibrida. Finché i chunk arrivano di seguito vengono
        scritti uno attaccato all'altro, perché sono davvero contigui: il jitter
        di consegna è di qualche millisecondo e posizionarli singolarmente
        lascerebbe micro-buchi udibili come click. Quando invece la consegna si
        interrompe davvero, il cursore salta alla posizione assoluta del primo
        chunk che riprende, e ciò che sta in mezzo resta zero.

        Così l'audio è continuo dove deve esserlo e l'errore non si accumula:
        ogni ripresa si riancora al tempo reale.
        """
        n_total = int(np.ceil(duration_s * self.rate)) + self.rate  # +1s di margine
        timeline = np.zeros((n_total, self.channels), dtype=np.float32)
        times: list[float] = []
        gap_threshold = int(0.050 * self.rate)  # sotto i 50 ms è jitter, non un buco
        cursor: int | None = None
        silence_samples = 0

        while not self.chunks.empty():
            chunk = self.chunks.get()
            frames = chunk.data.shape[0]
            # t_recv è il momento della CONSEGNA: i campioni coprono
            # l'intervallo che finisce lì.
            abs_start = int(round(((chunk.t_recv - t0) - frames / self.rate) * self.rate))
            abs_start = max(abs_start, 0)

            if cursor is None:
                cursor = abs_start
                silence_samples += abs_start
            elif abs_start - cursor > gap_threshold:
                silence_samples += abs_start - cursor
                cursor = abs_start

            end = min(cursor + frames, n_total)
            if end > cursor:
                timeline[cursor:end] = chunk.data[: end - cursor]
            cursor = end
            times.append(chunk.t_recv)

        timeline = timeline[: cursor or 0]
        return timeline, times, silence_samples / self.rate


def to_mono_16k(audio: np.ndarray, src_rate: int) -> np.ndarray:
    """Downmix a mono e resample alla frequenza attesa dallo STT."""
    if audio.size == 0:
        return np.zeros(0, dtype=np.float32)
    mono = audio.mean(axis=1)
    if src_rate == TARGET_RATE:
        return mono.astype(np.float32)
    # resample_poly usa un filtro polifase: niente aliasing, costo trascurabile
    from math import gcd

    g = gcd(int(src_rate), TARGET_RATE)
    return resample_poly(mono, TARGET_RATE // g, int(src_rate) // g).astype(np.float32)


def write_wav(path: Path, mono: np.ndarray, rate: int = TARGET_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm16 = np.clip(mono, -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm16.tobytes())


def pick_devices(pa: pyaudio.PyAudio) -> tuple[dict, dict]:
    """Microfono di default e loopback accoppiato all'uscita di default."""
    wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    mic = pa.get_device_info_by_index(wasapi["defaultInputDevice"])
    speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])

    loopback = None
    for dev in pa.get_loopback_device_info_generator():
        if speakers["name"] in dev["name"]:
            loopback = dev
            break
    if loopback is None:
        raise RuntimeError(
            f"Nessun loopback per l'uscita di default ({speakers['name']}). "
            "Esegui spikes/list_devices.py per vedere cosa c'è."
        )
    return mic, loopback


def play_test_tone(seconds: float, rate: int = 48_000) -> "object":
    """Riproduce un pattern di bip sull'uscita di default, in background.

    Serve a validare il loopback senza dipendere da una sorgente esterna: se i
    bip ricompaiono in system.wav, la catena "audio degli altri" funziona.
    Un pattern intermittente è più utile di un tono continuo, perché mette alla
    prova proprio la ricostruzione dei silenzi.
    """
    import sounddevice as sd

    t = np.arange(int(seconds * rate)) / rate
    tone = 0.25 * np.sin(2 * np.pi * 440.0 * t)
    # 1s di bip ogni 2s: i buchi sono i silenzi da ricostruire.
    gate = ((t % 2.0) < 1.0).astype(np.float32)
    signal = (tone * gate).astype(np.float32)

    sd.play(signal, samplerate=rate)
    return sd


def play_with_gap(total_s: float, rate: int = 48_000) -> "object":
    """Bip, poi silenzio TOTALE (nessuna riproduzione), poi di nuovo bip.

    È il caso che rompe tutto se gestito male: mentre nessuna applicazione
    riproduce audio, WASAPI smette di consegnare pacchetti sul loopback. Chi
    concatena i chunk si ritrova la seconda metà della call anticipata di quanto
    è durata la pausa.
    """
    import threading

    import sounddevice as sd

    third = total_s / 3.0

    def burst(seconds: float) -> np.ndarray:
        t = np.arange(int(seconds * rate)) / rate
        gate = ((t % 2.0) < 1.0).astype(np.float32)
        return (0.25 * np.sin(2 * np.pi * 440.0 * t) * gate).astype(np.float32)

    def schedule() -> None:
        sd.play(burst(third), samplerate=rate)
        time.sleep(third)
        sd.stop()  # silenzio vero: il loopback si azzittisce del tutto
        time.sleep(third)
        sd.play(burst(third), samplerate=rate)

    threading.Thread(target=schedule, daemon=True).start()
    return sd


def rms_db(mono: np.ndarray) -> float:
    """Livello medio in dBFS: serve a capire se una traccia è davvero muta."""
    if mono.size == 0:
        return float("-inf")
    rms = float(np.sqrt(np.mean(np.square(mono))))
    return 20.0 * np.log10(rms) if rms > 1e-9 else float("-inf")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=60.0, help="durata della cattura")
    parser.add_argument(
        "--tone",
        action="store_true",
        help="riproduce bip di test sull'uscita, per validare il loopback da solo",
    )
    parser.add_argument(
        "--gap",
        action="store_true",
        help="bip, silenzio totale, bip: verifica la ricostruzione dei buchi",
    )
    args = parser.parse_args()

    with pyaudio.PyAudio() as pa:
        mic_info, loop_info = pick_devices(pa)

        mic = Track(
            name="mic",
            device_index=mic_info["index"],
            channels=int(mic_info["maxInputChannels"]),
            rate=int(mic_info["defaultSampleRate"]),
        )
        system = Track(
            name="system",
            device_index=loop_info["index"],
            channels=int(loop_info["maxInputChannels"]),
            rate=int(loop_info["defaultSampleRate"]),
        )

        print(f"mic     : [{mic.device_index}] {mic_info['name']}  ({mic.channels}ch @ {mic.rate} Hz)")
        print(f"loopback: [{system.device_index}] {loop_info['name']}  ({system.channels}ch @ {system.rate} Hz)")
        print()

        for track in (mic, system):
            track.stream = pa.open(
                format=pyaudio.paFloat32,
                channels=track.channels,
                rate=track.rate,
                input=True,
                input_device_index=track.device_index,
                frames_per_buffer=1024,
                stream_callback=track.callback,
                start=False,
            )

        # Avvio il più ravvicinato possibile; lo sfasamento residuo viene misurato
        # dai timestamp del primo chunk, non assunto pari a zero.
        t0 = time.perf_counter()
        mic.stream.start_stream()
        system.stream.start_stream()

        if args.gap:
            sd = play_with_gap(args.seconds)
        elif args.tone:
            sd = play_test_tone(args.seconds)
        else:
            sd = None

        if args.gap:
            third = args.seconds / 3.0
            print(f"Registro {args.seconds:.0f}s — bip / {third:.0f}s di silenzio totale / bip\n")
        elif args.tone:
            print(f"Registro {args.seconds:.0f}s — bip di test in riproduzione sull'uscita\n")
        else:
            print(f"Registro {args.seconds:.0f}s — parla al microfono E fai suonare qualcosa")
            print("(un video su YouTube va benissimo: simula la voce degli altri)\n")
        try:
            deadline = t0 + args.seconds
            while time.perf_counter() < deadline:
                remaining = deadline - time.perf_counter()
                print(f"\r  {remaining:5.1f}s rimanenti ", end="", flush=True)
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\nInterrotto.")
        finally:
            t_end = time.perf_counter()
            if sd is not None:
                sd.stop()
            for track in (mic, system):
                track.stream.stop_stream()
                track.stream.close()

    wall = t_end - t0
    print(f"\n\nDurata reale (orologio): {wall:.3f}s\n")

    results = {}
    for track in (mic, system):
        audio, times, silence_s = track.collect(t0, wall)
        mono = to_mono_16k(audio, track.rate)
        path = OUT_DIR / f"{track.name}.wav"
        write_wav(path, mono)

        captured_s = track.n_frames / track.rate
        timeline_s = audio.shape[0] / track.rate  # con i silenzi reinseriti
        start_offset = (track.first_t - t0) if track.first_t else float("nan")
        slope, drift_h_ms = track.clock_ratio()

        results[track.name] = {
            "captured_s": captured_s,
            "timeline_s": timeline_s,
            "start_offset_ms": start_offset * 1000.0,
            "slope": slope,
            "drift_h_ms": drift_h_ms,
            "chunks": len(times),
            "level_db": rms_db(mono),
            "path": path,
        }

        print(f"[{track.name}]")
        print(f"  campioni catturati  : {track.n_frames} ({captured_s:.3f}s)")
        print(f"  silenzio ricostruito: {silence_s:.3f}s")
        print(f"  timeline totale     : {timeline_s:.3f}s")
        print(f"  chunk ricevuti      : {len(times)}")
        print(f"  primo chunk a       : {start_offset * 1000:+.1f} ms da t0")
        print(f"  clock audio/reale   : {slope:.7f}  ({(slope - 1) * 1e6:+.0f} ppm)")
        print(f"  drift estrapolato   : {drift_h_ms:+.0f} ms/ora")
        print(f"  livello medio       : {results[track.name]['level_db']:.1f} dBFS")
        print(f"  scritto in          : {path}")
        print()

    skew_ms = results["mic"]["start_offset_ms"] - results["system"]["start_offset_ms"]
    # Il drift assoluto rispetto all'orologio non conta: conta di quanto le due
    # tracce si allontanano FRA LORO, perché è quello che sposta le parole
    # dell'uno rispetto a quelle dell'altro.
    relative_drift_h = abs(results["mic"]["drift_h_ms"] - results["system"]["drift_h_ms"])

    print("--- Esito ---")
    print(f"Sfasamento di partenza fra le due tracce : {skew_ms:+.1f} ms")
    print(f"Drift relativo mic vs system             : {relative_drift_h:.0f} ms/ora")

    ok = True
    if not np.isfinite(relative_drift_h):
        print("\n[X] Dati insufficienti per misurare il drift.")
        ok = False
    elif relative_drift_h >= 500.0:
        print(f"\n[X] Le due tracce divergono di {relative_drift_h:.0f} ms/ora:")
        print("    serve una correzione attiva, non basta marcare i chunk.")
        ok = False
    for name in ("mic", "system"):
        if results[name]["level_db"] == float("-inf") or results[name]["level_db"] < -70:
            print(f"\n[X] La traccia '{name}' è praticamente muta ({results[name]['level_db']:.1f} dBFS).")
            ok = False

    if ok:
        print("\n[OK] Cattura a due tracce valida. Riascolta i due WAV per confermare")
        print("     che in mic.wav ci sia la tua voce e in system.wav l'altra sorgente.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
