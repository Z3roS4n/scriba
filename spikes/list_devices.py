"""Elenca i device audio disponibili, evidenziando i loopback WASAPI.

Serve a capire cosa c'è sulla macchina prima di scrivere la cattura vera.
"""

import pyaudiowpatch as pyaudio


def main() -> None:
    with pyaudio.PyAudio() as pa:
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError:
            print("WASAPI non disponibile su questa macchina.")
            return

        default_speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        default_mic = pa.get_device_info_by_index(wasapi["defaultInputDevice"])

        print(f"Host API WASAPI: index {wasapi['index']}, {wasapi['deviceCount']} device\n")
        print(f"Output di default : [{default_speakers['index']}] {default_speakers['name']}")
        print(f"Input di default  : [{default_mic['index']}] {default_mic['name']}\n")

        print("--- Device di loopback (audio di sistema) ---")
        for dev in pa.get_loopback_device_info_generator():
            marker = " <-- accoppiato all'output di default" if default_speakers["name"] in dev["name"] else ""
            print(
                f"  [{dev['index']:>3}] {dev['name']}\n"
                f"        {dev['maxInputChannels']}ch @ {int(dev['defaultSampleRate'])} Hz{marker}"
            )

        print("\n--- Device di input (microfoni) ---")
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if dev["hostApi"] != wasapi["index"] or dev["maxInputChannels"] < 1:
                continue
            if dev.get("isLoopbackDevice"):
                continue
            marker = " <-- default" if dev["index"] == default_mic["index"] else ""
            print(
                f"  [{dev['index']:>3}] {dev['name']}\n"
                f"        {dev['maxInputChannels']}ch @ {int(dev['defaultSampleRate'])} Hz{marker}"
            )


if __name__ == "__main__":
    main()
