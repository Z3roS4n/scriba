"""Chi ha parlato, dentro «altri» — a call finita, sull'audio salvato.

Le due tracce separate (`recorder.py`, `audio/writer.py`) danno già «io» contro
«altri» gratis e con precisione perfetta: è la traccia da cui il suono è
entrato, non un'inferenza, e per questo `transcript_segments.source` non lo
tocca nessuno qui dentro, mai. Quello che le due tracce non possono dare è la
distinzione *dentro* «altri»: se in una call c'erano Marco e Sofia, oggi sono
la stessa voce. È il problema con cui è nato questo modulo.

Si diarizza **solo la traccia loopback**. Il microfono è per definizione una
persona sola — chi tiene il computer — e mescolarlo alle voci degli altri
sarebbe un errore concettuale ancora prima che tecnico: non c'è niente da
separare su una traccia con un solo parlante.

Il modello è `pyannote/speaker-diarization-community-1`: gira in locale, su
CPU, niente CUDA richiesta. Non è incluso — pesa, insieme a `pyannote.audio` e
a `torch`, qualche centinaio di MB — ed è gated su Hugging Face: bisogna
accettare le condizioni sul modello e avere un token utente (`huggingface-cli
login`, o la variabile d'ambiente `HF_TOKEN`) prima che possa scaricarsi da
solo al primo uso vero. Finché quel token non c'è, o finché le librerie non
sono installate, `disponibile()` dice falso e il resto dell'applicazione deve
continuare esattamente come prima: «Io» e «Altri», senza eccezioni che
risalgono e senza che una call sembri rotta per una funzione mai attivata.

Verifica di fattibilità sui tempi (fatta su questa macchina, Ryzen 5 5600G, 6
core / 12 thread, niente GPU): senza i pesi veri di community-1 — gated, e
senza un token HF non si possono scaricare in questa sessione di lavoro — non
si può misurare la pipeline per intero. Si sono però instanziati con pesi
casuali i due modelli che ne fanno per architettura la parte più pesante,
`pyannote.audio.models.segmentation.PyanNet` (682k parametri) e
`pyannote.audio.models.embedding.WeSpeakerResNet34` (6.6M parametri) — il
costo di calcolo di un forward pass dipende dall'architettura, non dai pesi,
quindi il numero è reale anche senza i pesi scaricati. Con finestre da 10s e
lo scorrimento al 90% di sovrapposizione che pyannote usa di default (~3600
finestre per un'ora di audio): la segmentazione da sola costa sui 4 minuti,
l'estrazione degli embedding, il passo più caro, fra i 15 e i 25 minuti a
seconda del batching. Clustering escluso (costa poco: qualche secondo su
poche migliaia di embedding). Stima totale ragionevole per un'ora di call:
20-35 minuti — sotto ai 40 minuti indicati come soglia oltre la quale la
funzione non sarebbe tale, ma non con un margine comodo: è un passo esplicito
di fine call, mai qualcosa che gira da solo, e va presentato con una barra di
avanzamento vera (da qui `avanzamento`), non fatto aspettare in silenzio.

Nota tecnica emersa nella verifica, non solo di velocità: `pyannote.audio`
4.x usa `torchcodec` per leggere l'audio da file, e `torchcodec` a sua volta
richiede FFmpeg installato nel sistema — cosa che su una macchina Windows
pulita non c'è. Passargli un percorso di file fallisce quindi silenziosamente
verso un warning e un rallentamento all'avvio. Si aggira scrivendo la lettura
del WAV a mano (`_carica_audio`, con `wave` della libreria standard — lo
stesso formato che scrive `audio/writer.py`: mono, 16 kHz, PCM 16 bit) e
passando alla pipeline un waveform già in memoria: è una forma di input che
`pyannote.audio` supporta esplicitamente, e con quella FFmpeg non serve mai.
"""

from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Any, Protocol

import numpy as np

log = logging.getLogger(__name__)

REPO_MODELLO = "pyannote/speaker-diarization-community-1"


class DiarizzazioneNonDisponibile(RuntimeError):
    """Sollevata da `assegna()` quando si prova a usarla senza che sia pronta.

    Una classe a parte invece di un `RuntimeError` generico: chi chiama (la
    rotta HTTP) deve poter distinguere "non è configurata" da un errore vero
    durante l'elaborazione, per rispondere 409 nel primo caso e 500 nel
    secondo invece di confonderli.
    """


class _Avanzamento(Protocol):
    def __call__(self, frazione: float, nota: str) -> None: ...


class Diarizzatore:
    """Esegue la diarizzazione della traccia loopback di una sessione, a call finita."""

    def __init__(self, *, repo: str = REPO_MODELLO) -> None:
        self.repo = repo
        # Caricare la pipeline è la parte lenta (i pesi sono centinaia di MB):
        # si tiene in cache sull'istanza, non si ricarica a ogni `assegna()`.
        # Un'istanza di `Diarizzatore` vive quanto il processo, come
        # `ModelsManager` per il modello di analisi.
        self._pipeline_cache: Any = None

    # --------------------------------------------------------------- stato

    def disponibile(self) -> bool:
        """Vero se si può chiamare `assegna()` adesso, senza tentare download.

        Tre cose devono essere vere insieme: le librerie (`torch`,
        `pyannote.audio`) sono installate, e o i pesi sono già in cache
        locale da una volta precedente, o c'è un token Hugging Face
        risolvibile (variabile d'ambiente o `huggingface-cli login`) con cui
        tentare di scaricarli al primo uso vero. Non solleva mai: un
        controllo di disponibilità che può fallire con un'eccezione non è un
        controllo di disponibilità.
        """
        try:
            import torch  # noqa: F401
            from huggingface_hub import get_token, scan_cache_dir
        except ImportError:
            return False

        try:
            if get_token() is not None:
                return True
            cache = scan_cache_dir()
            return any(r.repo_id == self.repo for r in cache.repos)
        except Exception:
            # Una cache corrotta o un errore di huggingface_hub non devono
            # far sembrare rotta l'intera applicazione: si dice solo "non
            # disponibile adesso", che è vero.
            log.warning("Verifica disponibilità diarizzazione fallita", exc_info=True)
            return False

    # ------------------------------------------------------------ assegna

    def assegna(
        self,
        session_id: int,
        store: Any,
        *,
        avanzamento: _Avanzamento | None = None,
    ) -> dict:
        """Diarizza il loopback della sessione e scrive `speakers`/`speaker_id`.

        Non tocca mai `transcript_segments.source`: quella colonna dice da
        quale traccia è entrato il suono ed è verità di campo, un modello
        probabilistico non la può smentire. Scrive solo `speaker_id`, che è
        un raffinamento e può sbagliare.
        """
        if not self.disponibile():
            raise DiarizzazioneNonDisponibile(
                "il modello di diarizzazione non è installato o configurato "
                "(servono pyannote.audio, torch, e un token Hugging Face che "
                f"abbia accettato le condizioni di {self.repo})"
            )

        def avanza(frazione: float, nota: str) -> None:
            if avanzamento is not None:
                avanzamento(frazione, nota)

        sessione = store.get_session(session_id)
        if sessione is None:
            raise ValueError(f"sessione sconosciuta: {session_id}")

        percorso_loopback = sessione["audio_loop_path"]
        segmenti_loopback = [s for s in store.segments(session_id) if s.source == "loopback"]

        import time

        if not percorso_loopback or not segmenti_loopback:
            # Niente da diarizzare — nessuno ha mai parlato sul loopback, o la
            # traccia non è stata salvata. Si registra comunque che la
            # diarizzazione è stata *eseguita*: è quello che permette a chi
            # costruisce la risposta di `/sessions/{id}/segments` di smettere
            # di mandare sempre `speaker: null` per questa sessione.
            avanza(1.0, "niente da diarizzare sul loopback")
            return store.applica_diarizzazione(
                session_id, {}, quando_ms=int(time.time() * 1000)
            )

        avanza(0.0, "carico il modello")
        pipeline = self._carica_pipeline()

        avanza(0.1, "leggo l'audio")
        audio = self._carica_audio(Path(percorso_loopback))

        avanza(0.2, "analizzo le voci (può volerci qualche minuto)")
        risultato = pipeline(audio)
        tracce = _tracce_da_annotazione(risultato)

        avanza(0.9, "assegno le voci ai segmenti")
        assegnazioni = assegna_etichette(tracce, segmenti_loopback)

        esito = store.applica_diarizzazione(
            session_id, assegnazioni, quando_ms=int(time.time() * 1000)
        )
        avanza(1.0, "fatto")
        return esito

    # ------------------------------------------------------------- interno

    def _carica_pipeline(self) -> Any:
        if self._pipeline_cache is not None:
            return self._pipeline_cache
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(self.repo)
        if pipeline is None:
            # `from_pretrained` di pyannote torna None invece di sollevare
            # quando le condizioni del modello non sono state accettate sul
            # sito: senza questo controllo l'errore vero arriverebbe come un
            # `TypeError` incomprensibile alla prima chiamata della pipeline.
            raise DiarizzazioneNonDisponibile(
                f"Hugging Face non ha restituito la pipeline per {self.repo}: "
                "controlla di aver accettato le condizioni del modello sul "
                "sito con l'account a cui appartiene il token configurato."
            )
        self._pipeline_cache = pipeline
        return pipeline

    @staticmethod
    def _carica_audio(percorso: Path) -> dict:
        """Legge il WAV a mano invece di passare il percorso alla pipeline.

        `pyannote.audio` userebbe `torchcodec`, che su una macchina senza
        FFmpeg installato non funziona (vedi il modulo). Il formato è quello
        scritto da `audio/writer.py`: mono, 16 kHz, PCM a 16 bit — lo stesso
        motivo per cui quel writer lo sceglie, qui torna comodo perché non
        serve nessuna conversione oltre al passaggio a float.
        """
        import torch

        with wave.open(str(percorso), "rb") as f:
            n_canali = f.getnchannels()
            frame_rate = f.getframerate()
            grezzo = f.readframes(f.getnframes())

        campioni = np.frombuffer(grezzo, dtype=np.int16).astype(np.float32) / 32768.0
        if n_canali > 1:
            campioni = campioni.reshape(-1, n_canali).mean(axis=1)

        forma_onda = torch.from_numpy(campioni).unsqueeze(0)  # (canali=1, campioni)
        return {"waveform": forma_onda, "sample_rate": frame_rate}


def _tracce_da_annotazione(annotazione: Any) -> list[tuple[float, float, str]]:
    """Converte l'`Annotation` di pyannote in tuple semplici (inizio, fine, etichetta).

    Tenere `assegna_etichette` (sotto) sganciata dai tipi di pyannote.core la
    rende testabile senza il modello vero, e questa è l'unica funzione che sa
    come nasce quella lista.
    """
    return [
        (float(traccia.start), float(traccia.end), str(etichetta))
        for traccia, _, etichetta in annotazione.itertracks(yield_label=True)
    ]


def assegna_etichette(
    tracce: list[tuple[float, float, str]], segmenti: list[Any]
) -> dict[int, str]:
    """Per ogni segmento di trascrizione, l'etichetta di cluster con più sovrapposizione.

    Confrontare gli intervalli invece di guardare solo l'istante centrale
    tollera i piccoli disallineamenti fra i confini di frase della
    trascrizione (decisi dal VAD di Parakeet) e quelli della diarizzazione
    (decisi da un modello indipendente, con i suoi propri confini): sono due
    segmentazioni diverse dello stesso audio, non si allineano mai alla
    perfezione. Un segmento senza nessuna sovrapposizione (silenzio secondo
    il modello di diarizzazione, ma trascritto lo stesso) resta senza
    etichetta: meglio lasciarlo sulla voce che aveva ('altri') che indovinare.
    """
    assegnazioni: dict[int, str] = {}
    for seg in segmenti:
        inizio_s = seg.t_start_ms / 1000
        fine_s = seg.t_end_ms / 1000
        migliore_etichetta: str | None = None
        migliore_overlap = 0.0
        for t_inizio, t_fine, etichetta in tracce:
            overlap = min(fine_s, t_fine) - max(inizio_s, t_inizio)
            if overlap > migliore_overlap:
                migliore_overlap = overlap
                migliore_etichetta = etichetta
        if migliore_etichetta is not None:
            assegnazioni[seg.id] = migliore_etichetta
    return assegnazioni
