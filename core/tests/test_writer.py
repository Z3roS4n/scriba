"""Test della traccia salvata su disco.

La cosa che questi test proteggono è una sola: **il secondo 900 del file è il
secondo 900 della call**. È il presupposto di tutto ciò che torna sull'audio
dopo — rifare la trascrizione, distinguere le voci, saltare all'audio da una
citazione — e finora non era vero sulla traccia di sistema, dove i silenzi non
venivano scritti.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.audio.writer import SAMPLE_RATE, SOGLIA_BUCO_MS, TrackWriter  # noqa: E402


def blocco(secondi: float, valore: float = 0.5) -> np.ndarray:
    return np.full(int(secondi * SAMPLE_RATE), valore, dtype=np.float32)


def leggi(p: Path) -> np.ndarray:
    with wave.open(str(p), "rb") as w:
        grezzo = w.readframes(w.getnframes())
    return np.frombuffer(grezzo, dtype=np.int16).astype(np.float32) / 32767.0


@pytest.fixture()
def scrittore(tmp_path: Path):
    w = TrackWriter(tmp_path / "traccia.wav")
    w.start()
    return w


def test_una_traccia_continua_non_cambia(scrittore: TrackWriter) -> None:
    # Il microfono consegna sempre: qui non deve succedere niente di nuovo.
    for i in range(10):
        scrittore.write(blocco(0.1), t_ms=i * 100)
    percorso = scrittore.stop()

    assert percorso is not None
    assert leggi(percorso).size == pytest.approx(1.0 * SAMPLE_RATE, abs=SAMPLE_RATE // 100)
    assert scrittore.silenzio_ricostruito_s == 0.0


def test_il_buco_diventa_silenzio(scrittore: TrackWriter) -> None:
    # È il difetto della issue #45: fra i due blocchi passano dieci secondi in
    # cui nessuno riproduceva niente. Prima sparivano.
    scrittore.write(blocco(1.0), t_ms=0)
    scrittore.write(blocco(1.0), t_ms=11_000)
    percorso = scrittore.stop()

    assert percorso is not None
    audio = leggi(percorso)
    assert audio.size == pytest.approx(12.0 * SAMPLE_RATE, abs=SAMPLE_RATE // 100)
    assert scrittore.silenzio_ricostruito_s == pytest.approx(10.0, abs=0.01)
    # E il secondo blocco sta dove dice l'orologio, non subito dopo il primo.
    assert abs(audio[int(11.5 * SAMPLE_RATE)]) > 0.1
    assert abs(audio[int(5.0 * SAMPLE_RATE)]) < 0.01


def test_il_jitter_non_diventa_un_buco(scrittore: TrackWriter) -> None:
    # Fra una consegna e l'altra ballano dei millisecondi. Inseguirli lascerebbe
    # micro-buchi udibili come click: sotto soglia si scrive di seguito.
    piccolo = SOGLIA_BUCO_MS // 2
    for i in range(10):
        scrittore.write(blocco(0.1), t_ms=i * 100 + piccolo)
    scrittore.stop()
    assert scrittore.silenzio_ricostruito_s == 0.0


def test_un_blocco_in_ritardo_non_fa_tornare_indietro(scrittore: TrackWriter) -> None:
    scrittore.write(blocco(1.0), t_ms=0)
    scrittore.write(blocco(1.0), t_ms=100)  # dice di stare prima di dove siamo
    percorso = scrittore.stop()
    assert percorso is not None
    assert leggi(percorso).size == pytest.approx(2.0 * SAMPLE_RATE, abs=SAMPLE_RATE // 100)


def test_la_coda_si_allunga_fino_alla_fine_della_call(scrittore: TrackWriter) -> None:
    # Gli altri smettono di parlare a metà e la call va avanti: senza questo il
    # file resterebbe corto, e chi lo confronta con la durata della sessione lo
    # giudicherebbe disallineato per tutta la sua lunghezza.
    scrittore.write(blocco(1.0), t_ms=0)
    scrittore.porta_fino_a(30_000)
    percorso = scrittore.stop()

    assert percorso is not None
    assert leggi(percorso).size == pytest.approx(30.0 * SAMPLE_RATE, abs=SAMPLE_RATE // 100)


def test_una_traccia_muta_non_lascia_un_file(scrittore: TrackWriter) -> None:
    # Nessuno ha mai riprodotto niente per tutta la call. Un'ora di zeri sono
    # 115 MB che sembrano audio: si cancella, come si è sempre fatto.
    scrittore.porta_fino_a(3_600_000)
    assert scrittore.stop() is None
    assert not scrittore.path.exists()


def test_la_call_5_tornerebbe_allineata(tmp_path: Path) -> None:
    """Il caso misurato sulla registrazione vera: -21.7% sulla traccia di sistema.

    Si riproduce la forma di quella call in piccolo — parlato a raffiche, con
    in mezzo un tratto lungo in cui nessuno riproduce — e si verifica che il
    file torni lungo quanto la sessione invece che un quinto in meno.
    """
    durata_ms = 100_000
    w = TrackWriter(tmp_path / "loopback.wav")
    w.start()
    # Cinque raffiche da due secondi in dieci secondi, poi ottanta di niente.
    for i in range(5):
        w.write(blocco(2.0), t_ms=i * 2_000)
    w.porta_fino_a(durata_ms)
    percorso = w.stop()

    assert percorso is not None
    atteso = durata_ms / 1000 * SAMPLE_RATE
    assert leggi(percorso).size == pytest.approx(atteso, rel=0.003)
    assert w.silenzio_ricostruito_s == pytest.approx(90.0, abs=0.1)


class TestDentroLaRegistrazione:
    """Che l'istante arrivi davvero fino al file, non solo al trascrittore.

    È il pezzo che può rompersi in silenzio: il writer sa allinearsi, ma se chi
    lo chiama non gli passa l'istante torna tutto com'era — e non se ne
    accorgerebbe nessun test del solo writer.
    """

    class _CapturaFinta:
        def __init__(self, clock, on_audio) -> None:
            self.clock, self.on_audio = clock, on_audio

        def start(self):
            from scriba_core.audio.capture import DeviceInfo

            return {
                "mic": DeviceInfo(0, "Mic finto", 1, 16_000),
                "loopback": DeviceInfo(1, "Loopback finto", 1, 16_000),
            }

        def stop(self) -> None:
            pass

    def test_il_loopback_a_raffiche_resta_allineato(self, tmp_path: Path) -> None:
        from scriba_core.db.store import Store
        from scriba_core.recorder import Recorder

        class MotoreFinto:
            name = "finto"

            def has_speech(self, audio) -> bool:
                return False

            def transcribe(self, audio, *, language=None) -> str:
                return ""

        store = Store(tmp_path / "prova.sqlite")
        rec = Recorder(
            engine=MotoreFinto(),
            store=store,
            capture_factory=self._CapturaFinta,
            audio_dir=tmp_path / "audio",
        )
        rec.start(titolo="Prova")

        # Gli altri parlano due volte, a venti secondi di distanza; il
        # microfono consegna di continuo per i primi due secondi e poi tace.
        rec._feed("loopback", blocco(1.0), 0)
        rec._feed("loopback", blocco(1.0), 20_000)
        rec._feed("mic", blocco(2.0), 0)
        sessione = rec.session_id
        assert sessione is not None
        # La coda la allunga `stop()` da solo, fino all'istante della call.
        rec.stop()

        riga = store.get_session(sessione)
        audio = leggi(Path(riga["audio_loop_path"]))
        # La seconda raffica sta al secondo venti, non al secondo uno.
        assert abs(audio[int(20.5 * SAMPLE_RATE)]) > 0.1
        assert abs(audio[int(10.0 * SAMPLE_RATE)]) < 0.01
        assert audio.size == pytest.approx(21.0 * SAMPLE_RATE, abs=SAMPLE_RATE // 2)
