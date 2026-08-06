"""Test della passata di rifinitura.

Il test che conta più di tutti è quello del rifiuto. Su una traccia in cui
l'audio salvato non corrisponde agli istanti della trascrizione, riscrivere
significa mettere sotto ogni riga il testo di un'altra: un danno silenzioso e
irreversibile, sui dati che l'applicazione esiste per custodire. Meglio non
fare niente e dirlo.

L'audio finto porta dentro di sé la propria identità: ogni frase occupa un
tratto riempito con un valore diverso, e il motore finto legge quel valore per
sapere che frase sta guardando. Così un taglio nel punto sbagliato produce
davvero la frase sbagliata, invece di essere simulato con un mock che dice di
sì. È l'unico modo perché il test possa fallire per il motivo giusto.
"""

from __future__ import annotations

import sys
import threading
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.db.store import Store  # noqa: E402
from scriba_core.stt import rifinitura  # noqa: E402
from scriba_core.stt.rifinitura import (  # noqa: E402
    SAMPLE_RATE,
    _Righello,
    rifinisci,
    somiglianza,
)

FRASI = [
    "il preventivo lo mando domani",
    "la scadenza resta venerdi",
    "manca il collaudo sul secondo ambiente",
    "ci sentiamo la settimana prossima",
    "chiudo io con l'amministrazione",
]

# Come le aveva sentite la trascrizione dal vivo: quasi giuste, una parola per
# frase diversa. È la forma vera del problema — due modelli sullo stesso audio
# scrivono quasi la stessa cosa — ed è ciò che permette al controllo di
# allineamento di distinguere «modello diverso» da «pezzo di audio sbagliato».
# Con un testo di partenza senza nessuna parola in comune il controllo
# rifiuterebbe anche l'audio allineato, e avrebbe ragione.
DAL_VIVO = [
    "il preventivo lo mandò domani",
    "la scadenza resta venerdì",
    "manca il collaudo sul secondo ambiante",
    "ci sentiamo la settimana prossimo",
    "chiudo io con l'amministrazioni",
]


class MotoreFinto:
    """Legge dal livello del segnale quale frase sta guardando.

    Se il tratto non è uniforme — cioè se il taglio è caduto a cavallo fra due
    frasi, o nel silenzio — non inventa niente: dice che non ha capito. È
    esattamente quello che fa un modello vero su audio tagliato male, ed è la
    ragione per cui il controllo di allineamento può funzionare.
    """

    name = "finto"
    lingua_imponibile = True

    def __init__(self) -> None:
        self.chiamate: list[str | None] = []

    def transcribe(self, audio: np.ndarray, *, language: str | None = None) -> str:
        self.chiamate.append(language)
        if audio.size == 0:
            return ""
        indici = np.rint(np.abs(audio) * 100).astype(int) - 1
        dominante = int(np.bincount(np.clip(indici, 0, len(FRASI))).argmax())
        quota = float((indici == dominante).mean())
        if quota < 0.8 or not 0 <= dominante < len(FRASI):
            return "rumore indistinto"
        return FRASI[dominante]


def scrivi_traccia(percorso: Path, tratti: list[tuple[float, float, int]], durata_s: float) -> None:
    """Scrive un WAV in cui ogni frase occupa il proprio tratto.

    `tratti` è `(inizio_s, fine_s, indice della frase)`; `durata_s` è la
    lunghezza totale del file, che non è per forza quella della sessione — ed è
    proprio quando non lo è che questo modulo deve accorgersene.
    """
    percorso.parent.mkdir(parents=True, exist_ok=True)
    audio = np.zeros(int(durata_s * SAMPLE_RATE), dtype=np.float32)
    for inizio, fine, k in tratti:
        audio[int(inizio * SAMPLE_RATE) : int(fine * SAMPLE_RATE)] = (k + 1) / 100.0
    with wave.open(str(percorso), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((audio * 32767).astype(np.int16).tobytes())


# Cinque frasi in mezzo minuto, con silenzi in mezzo: la forma di una call.
QUANDO = [(10.0, 14.0), (20.0, 24.0), (30.0, 34.0), (40.0, 44.0), (50.0, 54.0)]
DURATA_MS = 200_000


@pytest.fixture()
def sessione(tmp_path: Path):
    store = Store(tmp_path / "prova.sqlite")
    sid = store.create_session(0, titolo="Riunione")
    for k, (a, b) in enumerate(QUANDO):
        store.add_segment(
            sid, "mic", int(a * 1000), int(b * 1000), DAL_VIVO[k], is_final=True
        )
    store.conn.execute("UPDATE sessions SET durata_ms = ? WHERE id = ?", (DURATA_MS, sid))
    store.conn.commit()
    return store, sid, tmp_path


def collega(store: Store, sid: int, mic: Path | None, loop: Path | None) -> None:
    store.set_audio_paths(sid, str(mic) if mic else None, str(loop) if loop else None)


def righe_testo(store: Store, sid: int) -> list[str]:
    return [s.testo for s in store.segments(sid, only_final=True)]


class TestSomiglianza:
    def test_identiche(self) -> None:
        assert somiglianza("il preventivo di domani", "il preventivo di domani") == 1.0

    def test_una_parola_diversa(self) -> None:
        assert 0.6 < somiglianza("il preventivo di domani", "il preventivo di lunedi") < 1.0

    def test_niente_in_comune(self) -> None:
        assert somiglianza("il preventivo", "chiudo con l'amministrazione") == 0.0

    def test_una_delle_due_vuota(self) -> None:
        assert somiglianza("qualcosa", "") == 0.0
        assert somiglianza("", "") == 1.0


class TestRighello:
    def test_senza_scarto_taglia_dove_dice_l_orologio(self) -> None:
        r = _Righello(campioni=100 * SAMPLE_RATE, durata_ms=100_000)
        assert r.fattore == pytest.approx(1.0)
        audio = np.arange(100 * SAMPLE_RATE, dtype=np.float32)
        assert r.taglia(audio, 10_000, 11_000)[0] == 10 * SAMPLE_RATE

    def test_lo_scarto_costante_si_corregge(self) -> None:
        # La scheda audio non campiona esattamente alla frequenza dichiarata:
        # su due ore lo scarto si vede, ed è proporzionale.
        r = _Righello(campioni=int(100.2 * SAMPLE_RATE), durata_ms=100_000)
        assert r.taglia(np.arange(int(100.2 * SAMPLE_RATE), dtype=np.float32), 50_000, 51_000)[
            0
        ] == pytest.approx(50.1 * SAMPLE_RATE, rel=1e-4)

    def test_oltre_la_fine_non_esplode(self) -> None:
        r = _Righello(campioni=SAMPLE_RATE, durata_ms=1_000)
        assert r.taglia(np.zeros(SAMPLE_RATE, dtype=np.float32), 5_000, 6_000).size == 0


class TestAllineata:
    """L'audio corrisponde: si riscrive."""

    def test_le_righe_vengono_rifatte(self, sessione) -> None:
        store, sid, tmp = sessione
        mic = tmp / "audio" / "mic.wav"
        scrivi_traccia(mic, [(a, b, k) for k, (a, b) in enumerate(QUANDO)], 200.0)
        collega(store, sid, mic, None)

        esito = rifinisci(store, sid, MotoreFinto(), lingua="it")

        assert esito.tracce["mic"].stato == "rifinita"
        assert esito.riscritte == len(FRASI)
        assert righe_testo(store, sid) == FRASI

    def test_l_originale_resta(self, sessione) -> None:
        store, sid, tmp = sessione
        mic = tmp / "audio" / "mic.wav"
        scrivi_traccia(mic, [(a, b, k) for k, (a, b) in enumerate(QUANDO)], 200.0)
        collega(store, sid, mic, None)
        rifinisci(store, sid, MotoreFinto(), lingua="it")

        originali = [s.testo_originale for s in store.segments(sid, only_final=True)]
        assert originali == DAL_VIVO

    def test_la_lingua_arriva_al_modello(self, sessione) -> None:
        # È il motivo per cui questa passata esiste: Parakeet la lingua non la
        # legge, e qui deve arrivare fino in fondo.
        store, sid, tmp = sessione
        mic = tmp / "audio" / "mic.wav"
        scrivi_traccia(mic, [(a, b, k) for k, (a, b) in enumerate(QUANDO)], 200.0)
        collega(store, sid, mic, None)
        motore = MotoreFinto()
        rifinisci(store, sid, motore, lingua="it")

        assert motore.chiamate and set(motore.chiamate) == {"it"}

    def test_il_glossario_si_riapplica(self, sessione) -> None:
        # Senza, la rifinitura riporterebbe indietro i nomi propri che la
        # trascrizione dal vivo aveva già rimesso a posto.
        store, sid, tmp = sessione
        mic = tmp / "audio" / "mic.wav"
        scrivi_traccia(mic, [(a, b, k) for k, (a, b) in enumerate(QUANDO)], 200.0)
        collega(store, sid, mic, None)

        esito = rifinisci(store, sid, MotoreFinto(), lingua="it", termini=["Venerdì"])

        assert "Venerdì" in righe_testo(store, sid)[1]
        assert esito.nomi_corretti == 1


class TestNonAllineata:
    """L'audio non corrisponde: non si tocca niente, e si dice perché."""

    def test_la_traccia_compressa_viene_rifiutata(self, sessione) -> None:
        # È il caso vero della traccia «gli altri»: il loopback WASAPI non
        # consegna niente mentre nessuno riproduce, e i silenzi nel file non ci
        # sono. Misurato su una call reale: 21.7% più corta della sessione.
        store, sid, tmp = sessione
        loop = tmp / "audio" / "loopback.wav"
        # Le stesse cinque frasi, ma attaccate: 20 s invece di 200.
        scrivi_traccia(loop, [(k * 4.0, k * 4.0 + 4.0, k) for k in range(len(FRASI))], 20.0)
        for k, (a, b) in enumerate(QUANDO):
            store.add_segment(
                sid, "loopback", int(a * 1000), int(b * 1000), DAL_VIVO[k], is_final=True
            )
        collega(store, sid, None, loop)

        prima = righe_testo(store, sid)
        esito = rifinisci(store, sid, MotoreFinto(), lingua="it")

        t = esito.tracce["loopback"]
        assert t.stato == "non_allineata"
        assert t.riscritte == 0
        assert t.somiglianza is not None and t.somiglianza < rifinitura.SOMIGLIANZA_MINIMA
        assert "non corrisponde" in (t.motivo or "")
        assert righe_testo(store, sid) == prima, "non deve essere cambiato niente"

    def test_una_traccia_rotta_non_ferma_l_altra(self, sessione) -> None:
        store, sid, tmp = sessione
        mic = tmp / "audio" / "mic.wav"
        loop = tmp / "audio" / "loopback.wav"
        scrivi_traccia(mic, [(a, b, k) for k, (a, b) in enumerate(QUANDO)], 200.0)
        scrivi_traccia(loop, [(k * 4.0, k * 4.0 + 4.0, k) for k in range(len(FRASI))], 20.0)
        for k, (a, b) in enumerate(QUANDO):
            store.add_segment(
                sid, "loopback", int(a * 1000), int(b * 1000), DAL_VIVO[k], is_final=True
            )
        collega(store, sid, mic, loop)

        esito = rifinisci(store, sid, MotoreFinto(), lingua="it")

        assert esito.tracce["mic"].stato == "rifinita"
        assert esito.tracce["loopback"].stato == "non_allineata"


class TestCasiScomodi:
    def test_audio_mancante(self, sessione) -> None:
        store, sid, tmp = sessione
        collega(store, sid, tmp / "non-esiste.wav", None)
        esito = rifinisci(store, sid, MotoreFinto(), lingua="it")
        assert esito.tracce["mic"].stato == "assente"
        assert esito.riscritte == 0

    def test_una_passata_vuota_non_cancella_la_riga(self, sessione) -> None:
        # Se il modello non produce niente su una riga, quella riga resta com'era:
        # una frase esistente non si perde per un'inferenza andata a vuoto.
        store, sid, tmp = sessione
        mic = tmp / "audio" / "mic.wav"
        scrivi_traccia(mic, [(a, b, k) for k, (a, b) in enumerate(QUANDO)], 200.0)
        collega(store, sid, mic, None)

        class Muto(MotoreFinto):
            def transcribe(self, audio, *, language=None):
                testo = super().transcribe(audio, language=language)
                # Muto solo sulla terza riga, dopo che il controllo a campione
                # ha già stabilito che l'audio è allineato.
                return "" if testo == FRASI[2] else testo

        rifinisci(store, sid, Muto(), lingua="it")
        assert righe_testo(store, sid)[2] == DAL_VIVO[2]

    def test_si_puo_interrompere(self, sessione) -> None:
        store, sid, tmp = sessione
        mic = tmp / "audio" / "mic.wav"
        scrivi_traccia(mic, [(a, b, k) for k, (a, b) in enumerate(QUANDO)], 200.0)
        collega(store, sid, mic, None)

        annulla = threading.Event()
        annulla.set()
        with pytest.raises(rifinitura.Interrotta):
            rifinisci(store, sid, MotoreFinto(), lingua="it", annulla=annulla)

    def test_sessione_inesistente(self, sessione) -> None:
        store, _, _ = sessione
        with pytest.raises(ValueError):
            rifinisci(store, 9999, MotoreFinto(), lingua="it")
