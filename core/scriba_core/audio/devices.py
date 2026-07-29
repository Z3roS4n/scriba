"""Elenco dei dispositivi audio disponibili, per le impostazioni.

`capture.py` apre solo il microfono e il loopback predefiniti: qui invece si
elencano TUTTI i dispositivi WASAPI, perché è da questa lista che l'utente
sceglie quale usare. Le stesse due librerie, un compito diverso.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _dispositivo(id_: str, nome: str, *, predefinito: bool) -> dict[str, object]:
    return {"id": id_, "nome": nome, "predefinito": predefinito}


def microfoni() -> list[dict[str, object]]:
    """Ingressi WASAPI disponibili.

    Un fallimento qui (driver assente, servizio audio Windows fermo) non deve
    impedire di aprire le impostazioni: si torna una lista vuota invece di
    sollevare, così chi ha l'audio rotto può comunque arrivare a vedere cosa
    non va altrove nell'app.
    """
    try:
        import sounddevice as sd

        api_wasapi = next(
            (i for i, api in enumerate(sd.query_hostapis()) if api["name"] == "Windows WASAPI"),
            None,
        )
        if api_wasapi is None:
            return []

        predefinito_idx = sd.query_hostapis(api_wasapi)["default_input_device"]

        return [
            _dispositivo(str(idx), dev["name"], predefinito=idx == predefinito_idx)
            for idx, dev in enumerate(sd.query_devices())
            if dev["hostapi"] == api_wasapi and dev["max_input_channels"] > 0
        ]
    except Exception as exc:
        log.warning("Enumerazione microfoni non riuscita: %s", exc)
        return []


def sorgenti_loopback() -> list[dict[str, object]]:
    """Uscite disponibili come sorgente di loopback (quello che esce dalle casse).

    Stessa logica di `DualCapture.find_devices`: il loopback predefinito è
    quello il cui nome contiene quello dell'uscita audio predefinita di
    sistema, perché WASAPI non lo segnala altrimenti.
    """
    try:
        import pyaudiowpatch as pyaudio

        with pyaudio.PyAudio() as pa:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            uscita_predefinita = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])

            return [
                _dispositivo(
                    str(dev["index"]),
                    dev["name"],
                    predefinito=uscita_predefinita["name"] in dev["name"],
                )
                for dev in pa.get_loopback_device_info_generator()
            ]
    except Exception as exc:
        log.warning("Enumerazione sorgenti di loopback non riuscita: %s", exc)
        return []


def elenco() -> dict[str, list[dict[str, object]]]:
    """La forma di `Dispositivi`: microfoni e sorgenti di loopback insieme."""
    return {"microfoni": microfoni(), "loopback": sorgenti_loopback()}
