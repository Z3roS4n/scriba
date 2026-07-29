"""Test dei due interruttori che prima si spostavano senza produrre effetti.

`settings.stt.microfono_id`/`loopback_id` e `settings.stt.filtro_eco` si
salvavano già nelle impostazioni, ma nessuno li leggeva: il recorder apriva
sempre i device predefiniti e il filtro dell'eco usava sempre la stessa
soglia. Qui si verifica che vengano davvero rispettati, e che un id salvato
ormai introvabile (cuffie staccate, scheda cambiata) non impedisca di
registrare.

Niente hardware vero: `pyaudiowpatch` viene sostituito da un modulo finto con
la stessa forma minima (`PyAudio()`, `get_host_api_info_by_type`,
`get_device_info_by_index`, `get_loopback_device_info_generator`, `open`),
iniettato in `DualCapture` tramite `pyaudio_module`.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.audio.capture import DeviceInfo, DualCapture  # noqa: E402
from scriba_core.db.store import Store  # noqa: E402
from scriba_core.recorder import Recorder  # noqa: E402
from scriba_core.settings import Settings  # noqa: E402
from scriba_core.stt.eco import SOGLIA, FiltroEco, soglia_per_livello  # noqa: E402

# ---------------------------------------------------------------- pyaudio finto

WASAPI_INDEX = 7


class _FakeStream:
    def start_stream(self) -> None:
        pass

    def stop_stream(self) -> None:
        pass

    def close(self) -> None:
        pass


class _FakePyAudioInstance:
    """Quello che `pyaudio.PyAudio()` restituisce: sia come context manager
    (usato da `find_devices`) sia direttamente (usato da `start`)."""

    def __init__(self, devices: dict[int, dict], wasapi: dict, opened: list[int]) -> None:
        self._devices = devices
        self._wasapi = wasapi
        self._opened = opened

    def __enter__(self) -> "_FakePyAudioInstance":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get_host_api_info_by_type(self, _tipo: object) -> dict:
        return self._wasapi

    def get_device_info_by_index(self, idx: int) -> dict:
        try:
            return self._devices[idx]
        except KeyError as exc:
            raise OSError(f"device {idx} non trovato") from exc

    def get_loopback_device_info_generator(self):
        return iter(d for d in self._devices.values() if d.get("isLoopbackDevice"))

    def open(self, **kwargs):
        self._opened.append(kwargs["input_device_index"])
        return _FakeStream()

    def terminate(self) -> None:
        pass


class FakePyAudioModulo:
    """Sostituisce `pyaudiowpatch`: stessa forma minima, nessun hardware."""

    paFloat32 = "float32"
    paContinue = 0
    paWASAPI = "wasapi"

    def __init__(self, devices: dict[int, dict], wasapi: dict) -> None:
        self._devices = devices
        self._wasapi = wasapi
        # Gli `input_device_index` passati a `open()`, nell'ordine: è la prova
        # che il dispositivo scelto è davvero quello aperto, non solo quello
        # calcolato.
        self.opened: list[int] = []

    def PyAudio(self) -> _FakePyAudioInstance:
        return _FakePyAudioInstance(self._devices, self._wasapi, self.opened)


def _dispositivi_di_prova() -> tuple[dict[int, dict], dict]:
    """Un sistema con due microfoni e due loopback, uno predefinito e uno no."""
    devices = {
        0: {  # microfono predefinito
            "index": 0, "name": "Microfono integrato", "hostApi": WASAPI_INDEX,
            "maxInputChannels": 1, "maxOutputChannels": 0, "defaultSampleRate": 48_000.0,
        },
        1: {  # microfono scelto dall'utente
            "index": 1, "name": "Cuffie USB", "hostApi": WASAPI_INDEX,
            "maxInputChannels": 1, "maxOutputChannels": 0, "defaultSampleRate": 48_000.0,
        },
        2: {  # uscita audio predefinita (le casse)
            "index": 2, "name": "Altoparlanti", "hostApi": WASAPI_INDEX,
            "maxInputChannels": 0, "maxOutputChannels": 2, "defaultSampleRate": 48_000.0,
        },
        3: {  # loopback delle casse: quello che find_devices() sceglierebbe di default
            "index": 3, "name": "Altoparlanti [Loopback]", "hostApi": WASAPI_INDEX,
            "maxInputChannels": 2, "maxOutputChannels": 0, "defaultSampleRate": 48_000.0,
            "isLoopbackDevice": True,
        },
        4: {  # loopback scelto dall'utente (es. il monitor delle cuffie)
            "index": 4, "name": "Cuffie USB [Loopback]", "hostApi": WASAPI_INDEX,
            "maxInputChannels": 2, "maxOutputChannels": 0, "defaultSampleRate": 48_000.0,
            "isLoopbackDevice": True,
        },
    }
    wasapi = {"index": WASAPI_INDEX, "defaultInputDevice": 0, "defaultOutputDevice": 2}
    return devices, wasapi


class TestUnDispositivoScelto:
    """«Un dispositivo scelto viene davvero aperto», non solo calcolato."""

    def test_il_dispositivo_scelto_viene_aperto_davvero(self) -> None:
        devices, wasapi = _dispositivi_di_prova()
        modulo = FakePyAudioModulo(devices, wasapi)

        cattura = DualCapture(
            clock=None,
            on_audio=lambda *_: None,
            mic_id="1",
            loopback_id="4",
            pyaudio_module=modulo,
        )
        risultato = cattura.start()

        # Non solo il calcolo: la traccia audio è stata aperta su
        # quell'indice, non su un predefinito qualunque.
        assert modulo.opened == [1, 4]
        assert risultato["mic"] == DeviceInfo(1, "Cuffie USB", 1, 48_000)
        assert risultato["loopback"] == DeviceInfo(4, "Cuffie USB [Loopback]", 2, 48_000)
        assert cattura.fallback == {}
        cattura.stop()

    def test_senza_scelta_si_usano_i_predefiniti(self) -> None:
        # Comportamento di sempre quando nessuno ha scelto niente.
        devices, wasapi = _dispositivi_di_prova()
        modulo = FakePyAudioModulo(devices, wasapi)

        cattura = DualCapture(clock=None, on_audio=lambda *_: None, pyaudio_module=modulo)
        risultato = cattura.start()

        assert modulo.opened == [0, 3]
        assert risultato["mic"].index == 0
        assert risultato["loopback"].index == 3
        assert cattura.fallback == {}
        cattura.stop()


class TestIdScomparso:
    """«Un id salvato che non esiste più non deve impedire di registrare»."""

    def test_microfono_scomparso_ripiega_senza_rompere(self, caplog: pytest.LogCaptureFixture) -> None:
        devices, wasapi = _dispositivi_di_prova()
        del devices[1]  # le cuffie scelte sono state scollegate
        modulo = FakePyAudioModulo(devices, wasapi)

        cattura = DualCapture(
            clock=None, on_audio=lambda *_: None, mic_id="1", loopback_id="4", pyaudio_module=modulo
        )
        with caplog.at_level(logging.WARNING):
            risultato = cattura.start()  # non deve sollevare

        assert modulo.opened == [0, 4]  # mic ripiegato sul predefinito, loopback quello scelto
        assert risultato["mic"].index == 0
        assert "mic" in cattura.fallback
        assert "1" in cattura.fallback["mic"]
        assert any("non è più disponibile" in r.message for r in caplog.records)
        cattura.stop()

    def test_loopback_scomparso_ripiega_sul_predefinito_del_sistema(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        devices, wasapi = _dispositivi_di_prova()
        del devices[4]  # il loopback scelto non c'è più
        modulo = FakePyAudioModulo(devices, wasapi)

        cattura = DualCapture(
            clock=None, on_audio=lambda *_: None, mic_id="1", loopback_id="4", pyaudio_module=modulo
        )
        with caplog.at_level(logging.WARNING):
            risultato = cattura.start()  # non deve sollevare

        # Ripiega sul loopback delle casse (quello di sistema), come faceva
        # find_devices() prima che esistesse una scelta da rispettare.
        assert risultato["loopback"].index == 3
        assert "loopback" in cattura.fallback
        cattura.stop()

    def test_id_malformato_non_fa_esplodere_nulla(self) -> None:
        # Un settings.json toccato a mano, o una versione vecchia del file.
        devices, wasapi = _dispositivi_di_prova()
        modulo = FakePyAudioModulo(devices, wasapi)

        cattura = DualCapture(
            clock=None,
            on_audio=lambda *_: None,
            mic_id="non-un-numero",
            loopback_id="",
            pyaudio_module=modulo,
        )
        risultato = cattura.start()

        assert risultato["mic"].index == 0
        assert risultato["loopback"].index == 3
        cattura.stop()


# ------------------------------------------------------------- Recorder + Settings


class FakeEngine:
    name = "fake"

    def transcribe(self, audio: np.ndarray, *, language: str | None = None) -> str:
        return "testo"

    def has_speech(self, audio: np.ndarray) -> bool:
        return False  # non serve emettere segmenti per questi test


class FakeCaptureConDispositivi:
    """Finta scheda audio che ricorda quali id il Recorder le ha assegnato.

    Simula anche un loopback scelto ormai introvabile, per verificare che il
    Recorder propaghi il fallback in `RecordingInfo` invece di inghiottirlo.
    """

    def __init__(self, clock, on_audio) -> None:
        self.clock = clock
        self.on_audio = on_audio
        # Il Recorder li assegna dopo la costruzione: qui partono vuoti.
        self.mic_id: str | None = None
        self.loopback_id: str | None = None
        self.fallback: dict[str, str] = {}

    def start(self) -> dict[str, DeviceInfo]:
        indice_mic = int(self.mic_id) if self.mic_id else 0
        if self.loopback_id == "id-scomparso":
            self.fallback = {
                "loopback": (
                    f"il loopback scelto (id {self.loopback_id}) non è più disponibile, "
                    "uso il predefinito"
                )
            }
            indice_loop = 3
        else:
            indice_loop = int(self.loopback_id) if self.loopback_id else 3
        return {
            "mic": DeviceInfo(indice_mic, "Mic", 1, 16_000),
            "loopback": DeviceInfo(indice_loop, "Loopback", 1, 16_000),
        }

    def stop(self) -> None:
        pass


class TestRecorderLeggeLeImpostazioni:
    def test_recorder_passa_gli_id_e_registra_il_fallback(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        store = Store(tmp_path / "rec.sqlite")
        settings = Settings(tmp_path / "settings.json")
        settings.aggiorna(
            {"stt": {"microfono_id": "7", "loopback_id": "id-scomparso", "filtro_eco": "alto"}}
        )

        rec = Recorder(
            FakeEngine(), store, capture_factory=FakeCaptureConDispositivi, settings=settings
        )
        with caplog.at_level(logging.WARNING):
            info = rec.start()

        # Gli id delle impostazioni sono arrivati davvero alla cattura...
        assert rec._capture.mic_id == "7"
        assert rec._capture.loopback_id == "id-scomparso"
        # ...e il fallback della cattura è arrivato fino a chi ha chiamato start().
        assert info.fallback == {
            "loopback": (
                "il loopback scelto (id id-scomparso) non è più disponibile, "
                "uso il predefinito"
            )
        }
        assert any("ripiegato sul predefinito" in r.message for r in caplog.records)
        # Il livello "alto" scelto nelle impostazioni è arrivato al filtro eco.
        assert rec._eco.soglia == soglia_per_livello("alto")

        rec.stop()

    def test_senza_impostazioni_si_comporta_come_prima(self, tmp_path: Path) -> None:
        # Nessun Settings collegato (CLI, o test più vecchi): comportamento
        # invariato, nessuna scelta da rispettare.
        store = Store(tmp_path / "rec.sqlite")
        rec = Recorder(FakeEngine(), store, capture_factory=FakeCaptureConDispositivi)

        info = rec.start()

        assert rec._capture.mic_id is None
        assert rec._capture.loopback_id is None
        assert info.fallback == {}
        assert rec._eco.soglia == SOGLIA

        rec.stop()


# --------------------------------------------------------- filtro eco a 3 livelli


class TestFiltroEcoTreLivelli:
    """Sullo stesso ingresso, i tre livelli devono scartare in modo diverso."""

    # 20 parole distinte: la "frase" uscita dalle casse.
    USCITA = (
        "progetto budget cliente scadenza fornitore contratto team sviluppo test rilascio "
        "bug modulo interfaccia database server rete sicurezza backup versione ambiente"
    )

    def test_medio_e_invariato(self) -> None:
        # Chi non tocca l'impostazione non deve vedere cambiare la trascrizione.
        assert soglia_per_livello("medio") == SOGLIA == 0.72

    def test_livello_sconosciuto_ripiega_su_medio(self) -> None:
        assert soglia_per_livello(None) == SOGLIA
        assert soglia_per_livello("altissimo") == SOGLIA

    def test_alto_scarta_dove_medio_e_basso_lasciano_passare(self) -> None:
        # 13 parole su 20 coincidono con l'uscita: somiglianza 0.65, sopra la
        # soglia "alto" (0.55) ma sotto "medio" (0.72) e "basso" (0.85).
        parole = self.USCITA.split()
        testo_65 = " ".join(parole[:13] + ["gatto", "pioggia", "montagna", "biscotto", "chitarra", "vulcano", "ombrello"])

        alto = FiltroEco(soglia=soglia_per_livello("alto"))
        medio = FiltroEco(soglia=soglia_per_livello("medio"))
        basso = FiltroEco(soglia=soglia_per_livello("basso"))
        for f in (alto, medio, basso):
            f.registra_uscita(0, self.USCITA)

        assert alto.e_eco(3_000, testo_65) is True
        assert medio.e_eco(3_000, testo_65) is False
        assert basso.e_eco(3_000, testo_65) is False

    def test_medio_scarta_dove_basso_lascia_passare(self) -> None:
        # 15 parole su 20 coincidono: somiglianza 0.75, sopra "medio" (0.72)
        # ma sotto "basso" (0.85).
        parole = self.USCITA.split()
        testo_75 = " ".join(parole[:15] + ["nuvola", "chiave", "sabbia", "lanterna", "cactus"])

        medio = FiltroEco(soglia=soglia_per_livello("medio"))
        basso = FiltroEco(soglia=soglia_per_livello("basso"))
        for f in (medio, basso):
            f.registra_uscita(0, self.USCITA)

        assert medio.e_eco(3_000, testo_75) is True
        assert basso.e_eco(3_000, testo_75) is False
