"""Cattura simultanea del microfono e dell'audio di sistema.

Le due sorgenti restano separate per tutta la pipeline: è ciò che permette di
dire "questo l'hai detto tu, questo l'hanno detto gli altri" senza diarizzazione,
con precisione esatta invece che probabilistica.

Il comportamento non ovvio, misurato in Fase 1: **il loopback non consegna nulla
mentre nessuna applicazione riproduce audio**. Non è un errore da gestire, è il
funzionamento normale di WASAPI. Chi conta i campioni per sapere a che punto è
arrivato sbaglia di secondi dopo qualche pausa; per questo ogni blocco porta con
sé l'istante in cui è stato catturato, e la posizione si legge da lì.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from math import gcd

import numpy as np
from scipy.signal import resample_poly

log = logging.getLogger(__name__)

TARGET_RATE = 16_000
FRAMES_PER_BUFFER = 1024


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    channels: int
    rate: int


def _dispositivo_input_valido(pa, wasapi: dict, id_: str) -> dict | None:
    """Il device WASAPI d'ingresso con questo id, se esiste ancora.

    L'id arriva da `audio/devices.py` (`GET /dispositivi`): è l'indice
    PortAudio del dispositivo, lo stesso sia per sounddevice che per
    pyaudiowpatch perché sotto usano la stessa libreria. Un indice non più
    valido — cuffie staccate, scheda cambiata — non solleva: si torna None e
    chi chiama ripiega sul predefinito.
    """
    try:
        idx = int(id_)
        dev = pa.get_device_info_by_index(idx)
    except (ValueError, TypeError, OSError):
        return None
    if dev.get("hostApi") != wasapi["index"] or dev.get("maxInputChannels", 0) <= 0:
        return None
    return dev


def _loopback_valido(loopback_devices: list[dict], id_: str) -> dict | None:
    """Il dispositivo di loopback con questo id, fra quelli disponibili adesso."""
    try:
        idx = int(id_)
    except (ValueError, TypeError):
        return None
    return next((d for d in loopback_devices if d["index"] == idx), None)


class _Track:
    """Una sorgente audio, con la sua conversione verso il formato dello STT."""

    def __init__(
        self,
        source: str,
        device: DeviceInfo,
        clock,
        on_audio: Callable[[str, np.ndarray, int], None],
    ) -> None:
        self.source = source
        self.device = device
        self.clock = clock
        self.on_audio = on_audio
        self.stream = None
        self.first_t: float | None = None
        self.n_frames = 0
        self._up, self._down = self._ratio(device.rate)

    @staticmethod
    def _ratio(src_rate: int) -> tuple[int, int]:
        g = gcd(src_rate, TARGET_RATE)
        return TARGET_RATE // g, src_rate // g

    def callback(self, in_data, frame_count, time_info, status):  # noqa: ANN001, ARG002
        # Gira nel thread audio: qui dentro non si fa niente di lento, o si
        # perdono campioni. Downmix e resample su 1024 frame costano
        # microsecondi; l'inferenza avviene altrove.
        t_recv = time.perf_counter()
        if self.first_t is None:
            self.first_t = t_recv

        samples = np.frombuffer(in_data, dtype=np.float32)
        if self.device.channels > 1:
            samples = samples.reshape(-1, self.device.channels).mean(axis=1)
        self.n_frames += len(samples)

        if self._up != self._down:
            samples = resample_poly(samples, self._up, self._down).astype(np.float32)

        # L'istante dei campioni è quello della consegna meno la loro durata.
        t_start = t_recv - (frame_count / self.device.rate)
        self.on_audio(self.source, samples, self.clock.to_ms(t_start))

        import pyaudiowpatch as pyaudio

        return (None, pyaudio.paContinue)


class DualCapture:
    """Apre microfono e loopback e consegna audio pronto per la trascrizione.

    `on_audio(source, samples, t_ms)` viene chiamata dal thread audio con blocchi
    mono a 16 kHz. Chi la implementa deve limitarsi ad accodare.
    """

    def __init__(
        self,
        clock,
        on_audio: Callable[[str, np.ndarray, int], None],
        *,
        mic_id: str | None = None,
        loopback_id: str | None = None,
        pyaudio_module=None,
    ) -> None:
        self.clock = clock
        self.on_audio = on_audio
        # Gli id scelti in Impostazioni > Trascrizione (audio/devices.py,
        # `GET /dispositivi`). None = predefinito di sistema, com'era prima
        # che questa scelta esistesse.
        self.mic_id = mic_id
        self.loopback_id = loopback_id
        # Iniettabile nei test: senza, aprire i device veri legherebbe i test
        # all'hardware della macchina su cui girano.
        self._pyaudio_module = pyaudio_module
        self._pa = None
        self._tracks: dict[str, _Track] = {}
        self._lock = threading.Lock()
        # Quali sorgenti sono ripiegate sul predefinito, e perché. Vuoto
        # finché `find_devices` non ha ancora provato ad aprire niente.
        self.fallback: dict[str, str] = {}

    def _pyaudio(self):
        if self._pyaudio_module is not None:
            return self._pyaudio_module
        import pyaudiowpatch as pyaudio

        return pyaudio

    # ------------------------------------------------------------------ device

    def find_devices(self) -> tuple[DeviceInfo, DeviceInfo]:
        """Microfono e loopback da usare per questa registrazione.

        Se `mic_id`/`loopback_id` sono valorizzati si prova prima quelli; se
        il dispositivo scelto non c'è più si ripiega sul predefinito di
        sistema e si annota il motivo in `self.fallback`, invece di far
        fallire l'avvio per una cuffia che nel frattempo è stata staccata.
        """
        pyaudio = self._pyaudio()
        self.fallback = {}

        with pyaudio.PyAudio() as pa:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)

            mic_raw = None
            if self.mic_id is not None:
                mic_raw = _dispositivo_input_valido(pa, wasapi, self.mic_id)
                if mic_raw is None:
                    self.fallback["mic"] = (
                        f"il microfono scelto (id {self.mic_id}) non è più disponibile, "
                        "uso il predefinito"
                    )
                    log.warning(self.fallback["mic"])
            if mic_raw is None:
                mic_raw = pa.get_device_info_by_index(wasapi["defaultInputDevice"])

            speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            loopback_devices = list(pa.get_loopback_device_info_generator())

            loop_raw = None
            if self.loopback_id is not None:
                loop_raw = _loopback_valido(loopback_devices, self.loopback_id)
                if loop_raw is None:
                    self.fallback["loopback"] = (
                        f"il loopback scelto (id {self.loopback_id}) non è più disponibile, "
                        "uso il predefinito"
                    )
                    log.warning(self.fallback["loopback"])
            if loop_raw is None:
                loop_raw = next(
                    (d for d in loopback_devices if speakers["name"] in d["name"]), None
                )
            if loop_raw is None:
                # Qui non c'è un id scomparso da recuperare: è il sistema che
                # non ha proprio un loopback per l'uscita corrente. Diverso
                # dal caso sopra, e resta un errore che blocca l'avvio — senza
                # loopback si registrerebbe solo la propria voce, e l'utente
                # se ne accorgerebbe solo a call finita.
                raise RuntimeError(
                    f"Nessun dispositivo di loopback per l'uscita corrente "
                    f"({speakers['name']}). Senza, si registra solo la propria voce."
                )

            def info(raw) -> DeviceInfo:  # noqa: ANN001
                return DeviceInfo(
                    index=int(raw["index"]),
                    name=str(raw["name"]),
                    channels=int(raw["maxInputChannels"]),
                    rate=int(raw["defaultSampleRate"]),
                )

            return info(mic_raw), info(loop_raw)

    # ------------------------------------------------------------------- ciclo

    def start(self) -> dict[str, DeviceInfo]:
        pyaudio = self._pyaudio()

        mic, loop = self.find_devices()
        self._pa = pyaudio.PyAudio()

        for source, device in (("mic", mic), ("loopback", loop)):
            track = _Track(source, device, self.clock, self.on_audio)
            track.stream = self._pa.open(
                format=pyaudio.paFloat32,
                channels=device.channels,
                rate=device.rate,
                input=True,
                input_device_index=device.index,
                frames_per_buffer=FRAMES_PER_BUFFER,
                stream_callback=track.callback,
                start=False,
            )
            self._tracks[source] = track

        # Avvio ravvicinato, ma lo sfasamento residuo (~100 ms, misurato) non si
        # assume nullo: ogni traccia si ancora al proprio primo blocco.
        for track in self._tracks.values():
            track.stream.start_stream()

        return {s: t.device for s, t in self._tracks.items()}

    def stop(self) -> None:
        with self._lock:
            for track in self._tracks.values():
                if track.stream is not None:
                    track.stream.stop_stream()
                    track.stream.close()
                    track.stream = None
            if self._pa is not None:
                self._pa.terminate()
                self._pa = None
            self._tracks.clear()

    def __enter__(self) -> DualCapture:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
