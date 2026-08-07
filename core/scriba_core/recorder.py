"""Governa una sessione di registrazione dall'inizio alla fine.

Tiene insieme i pezzi — orologio, cattura, trascrittori, database — e li spegne
nell'ordine giusto. L'ordine non è un dettaglio: si ferma prima la cattura e poi
i trascrittori, altrimenti la frase che l'utente stava pronunciando quando ha
premuto stop viene persa.

È l'unico posto che sa come si registra una call: la CLI e il server ci si
appoggiano entrambi invece di rifare il lavoro.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from .ai import ocr
from .audio.capture import DeviceInfo, DualCapture
from .audio.writer import TrackWriter
from .db.store import Store
from .session import SessionClock, State
from .settings import Settings
from .stt import eco as eco_mod
from .stt import glossario
from .stt.base import TranscriptEvent
from .stt.eco import FiltroEco, soglia_per_livello
from .stt.streaming import StreamingConfig, StreamingTranscriber

log = logging.getLogger(__name__)

SOURCES = ("mic", "loopback")


@dataclass
class _Aperto:
    """Il segmento provvisorio di una traccia, in attesa del definitivo.

    Si tiene anche l'istante di inizio e l'ultimo testo scritto: servono a
    riconoscere una frase rimasta aperta e a chiuderla com'era, invece di
    lasciarla sovrascrivere dalla frase successiva.
    """

    id: int
    t_start_ms: int
    testo: str


@dataclass(frozen=True)
class RecordingInfo:
    session_id: int
    started_at_ms: int
    devices: dict[str, DeviceInfo]
    # Quali sorgenti sono ripiegate sul predefinito perché l'id salvato nelle
    # impostazioni non esiste più (cuffie staccate, scheda cambiata), e
    # perché. Vuoto quando tutto è andato come scelto, o quando non c'era
    # nessuna scelta da rispettare.
    fallback: dict[str, str] = field(default_factory=dict)


class Recorder:
    """Una registrazione in corso.

    Il modello di trascrizione viene passato dall'esterno perché caricarlo costa
    secondi: si tiene vivo fra una call e l'altra invece di ricaricarlo a ogni
    avvio.
    """

    def __init__(
        self,
        engine,
        store: Store,
        *,
        on_event: Callable[[TranscriptEvent], None] | None = None,
        config: StreamingConfig | None = None,
        capture_factory: Callable[..., DualCapture] | None = None,
        audio_dir: Path | str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.engine = engine
        self.store = store
        self.audio_dir = Path(audio_dir) if audio_dir else Path(store.path).parent / "audio"
        self._on_event = on_event
        self._config = config
        # Sostituibile nei test: aprire i device audio veri li renderebbe
        # dipendenti dall'hardware della macchina su cui girano.
        self._capture_factory = capture_factory or DualCapture
        self._lock = threading.Lock()
        # Da qui arrivano il microfono/loopback scelti e il livello del
        # filtro eco (settings.py, chiavi `stt.*`). None = nessuna
        # impostazione da rispettare, si tengono i comportamenti di sempre.
        self.settings = settings

        self.clock: SessionClock | None = None
        self.session_id: int | None = None
        self._capture: DualCapture | None = None
        self._transcribers: dict[str, StreamingTranscriber] = {}
        # Il segmento provvisorio aperto per ogni traccia. Quando la frase si
        # chiude, quel record viene rifinito invece di crearne uno nuovo: è ciò
        # che tiene validi i riferimenti che le task avranno su questi segmenti.
        self._open_segments: dict[str, _Aperto] = {}
        # Il microfono riprende sempre un po' di quello che esce dalle casse.
        self._eco = self._nuovo_filtro_eco()
        self._echi_scartati = 0
        self._writers: dict[str, TrackWriter] = {}
        # Nomi propri da rimettere a posto dopo la trascrizione. Si riempiono
        # all'avvio della call, non qui: le impostazioni possono cambiare fra
        # una call e l'altra.
        self._glossario: list[str] = []
        self._glossario_livello = glossario.LIVELLO_PREDEFINITO
        self._nomi_corretti = 0

    # --------------------------------------------------------- impostazioni

    def _stt_conf(self) -> dict:
        """La sezione `stt` delle impostazioni correnti, o vuota se non c'è
        nessun `Settings` collegato (uso da CLI/test senza impostazioni)."""
        if self.settings is None:
            return {}
        return self.settings.tutto().get("stt", {})

    def _nuovo_filtro_eco(self) -> FiltroEco:
        livello = self._stt_conf().get("filtro_eco")
        return FiltroEco(soglia=soglia_per_livello(livello))

    def _termini_glossario(self) -> list[str]:
        """I nomi che il modello sbaglierebbe, letti una volta all'avvio.

        Si compone qui invece che a ogni frase: durante una call l'elenco non
        cambia, e rileggere l'anagrafica per ogni riga di trascrizione sarebbe
        una query al secondo per un risultato che è sempre lo stesso.
        """
        conf = self._stt_conf()
        termini = [str(t) for t in conf.get("glossario") or []]
        if conf.get("glossario_clienti", True):
            try:
                termini += [r["nome"] for r in self.store.clienti()]
            except Exception:  # pragma: no cover - anagrafica non leggibile
                log.warning("Anagrafica clienti non leggibile: resta il glossario scritto a mano.")
        return termini

    # ------------------------------------------------------------------ stato

    @property
    def is_recording(self) -> bool:
        return self.clock is not None and self.clock.state in (State.RECORDING, State.PAUSED)

    def now_ms(self) -> int:
        """L'istante corrente della call.

        Chiunque debba datare qualcosa — uno screenshot, una nota — lo chiede
        qui invece di leggere un proprio orologio. Due orologi diversi producono
        uno scarto che nessuno nota finché non si prova a saltare all'audio da
        una citazione.
        """
        return self.clock.now_ms() if self.clock else 0

    # ------------------------------------------------------------------ avvio

    def start(
        self,
        *,
        titolo: str | None = None,
        piattaforma: str | None = None,
        lingua: str = "it",
        consenso_confermato_at: int | None = None,
    ) -> RecordingInfo:
        with self._lock:
            if self.is_recording:
                raise RuntimeError("C'è già una registrazione in corso.")

            self.clock = SessionClock()
            self.session_id = self.store.create_session(
                self.clock.started_at_ms,
                titolo=titolo,
                piattaforma=piattaforma,
                lingua=lingua,
                stt_model=self.engine.name,
                consenso_confermato_at=consenso_confermato_at,
            )
            self._open_segments.clear()
            self._eco = self._nuovo_filtro_eco()
            self._echi_scartati = 0
            self._glossario = self._termini_glossario()
            self._glossario_livello = str(
                self._stt_conf().get("glossario_livello") or glossario.LIVELLO_PREDEFINITO
            )
            self._nomi_corretti = 0

            # L'audio si salva sempre. Senza, una trascrizione venuta male non
            # si può rifare e non si può risalire a chi ha parlato: il parlato è
            # passato e non torna.
            cartella = self.audio_dir / f"sessione-{self.session_id:05d}"
            self._writers = {source: TrackWriter(cartella / f"{source}.wav") for source in SOURCES}
            for w in self._writers.values():
                w.start()

            cfg = self._config or StreamingConfig(language=lingua)
            self._transcribers = {
                source: StreamingTranscriber(self.engine, source, self._handle_event, cfg)
                for source in SOURCES
            }
            for t in self._transcribers.values():
                t.start()

            self._capture = self._capture_factory(self.clock, self._feed)
            # Gli id scelti nelle impostazioni: si assegnano dopo la
            # costruzione, non passandoli al factory, perché il factory nei
            # test è spesso una finta scheda audio con una firma fissa
            # `(clock, feed)` — attributi extra non richiesti restano lì
            # inutilizzati invece di rompere la chiamata.
            stt_conf = self._stt_conf()
            self._capture.mic_id = stt_conf.get("microfono_id")
            self._capture.loopback_id = stt_conf.get("loopback_id")
            try:
                devices = self._capture.start()
            except Exception:
                # Se l'audio non parte, non si lascia in giro una sessione
                # "in registrazione" che non registra niente.
                self._teardown_transcribers()
                self.store.set_session_state(self.session_id, "error")
                self.clock = None
                raise

            # Un id salvato che non esiste più (cuffie staccate, scheda
            # cambiata) non deve bloccare l'avvio: `find_devices` è già
            # ripiegato sul predefinito, qui si registra solo il perché.
            fallback = dict(getattr(self._capture, "fallback", None) or {})
            for sorgente, motivo in fallback.items():
                log.warning("Dispositivo audio ripiegato sul predefinito (%s): %s", sorgente, motivo)

            return RecordingInfo(
                session_id=self.session_id,
                started_at_ms=self.clock.started_at_ms,
                devices=devices,
                fallback=fallback,
            )

    def _feed(self, source: str, samples: np.ndarray, t_ms: int) -> None:
        transcriber = self._transcribers.get(source)
        if transcriber is not None:
            transcriber.feed(samples, t_ms)
        writer = self._writers.get(source)
        if writer is not None:
            # L'istante serve al file quanto al trascrittore: è quello a
            # decidere dove il blocco finisce dentro la traccia, e senza il
            # loopback perde tutti i silenzi (vedi audio/writer.py).
            writer.write(samples, t_ms)

    # ------------------------------------------------------------- eventi STT

    def _handle_event(self, ev: TranscriptEvent) -> None:
        session_id = self.session_id
        if session_id is None:
            return

        # I nomi propri si rimettono a posto solo sui definitivi. Sui
        # provvisori il testo cambia a ogni ipotesi, e una correzione che
        # compare e sparisce mentre si sta leggendo è peggio del nome sbagliato.
        # Si fa prima di tutto il resto: il filtro eco confronta i testi delle
        # due tracce, e conviene che siano nella stessa forma — dal vivo non
        # sempre lo sono, perché confronta anche le ipotesi provvisorie
        # dell'altoparlante, che il glossario non ha ancora toccato. Costa
        # qualche nome che non coincide su una riga; il ripasso a fine call
        # lavora su definitivi da entrambe le parti e lì la forma è la stessa.
        originale: str | None = None
        if ev.is_final and ev.text and self._glossario:
            corretto, cambi = glossario.correggi(
                ev.text, self._glossario, livello=self._glossario_livello
            )
            if cambi:
                originale = ev.text
                self._nomi_corretti += len(cambi)
                ev = replace(ev, text=corretto)

        aperto = self._open_segments.get(ev.source)

        # Una frase che non si è chiusa non deve essere presa dalla frase dopo:
        # `refine_segment` ne sostituirebbe il testo lasciandole l'istante di
        # inizio del parlato precedente, e della frase di prima non resterebbe
        # niente. Si chiude com'era e si riparte. Il trascrittore emette sempre
        # un definitivo, quindi qui non si dovrebbe passare mai: se succede si
        # vuole saperlo, invece di scoprirlo da una trascrizione con dei buchi.
        if aperto is not None and aperto.t_start_ms != ev.t_start_ms:
            log.warning(
                "Frase su %s rimasta aperta a %d ms: chiusa prima di aprire quella a %d ms.",
                ev.source,
                aperto.t_start_ms,
                ev.t_start_ms,
            )
            self.store.refine_segment(aperto.id, aperto.testo, is_final=True)
            del self._open_segments[ev.source]
            aperto = None

        # Quello che esce dalle casse viene annotato, così se torna indietro dal
        # microfono lo si riconosce. Anche i provvisori: aspettare che la frase
        # dell'altoparlante si chiuda vuol dire giudicarne l'eco prima di
        # sapere cosa l'ha causato, ed è ciò che ne lasciava passare una su tre
        # (#59). Resta una finestra cieca — quello che l'altro non ha ancora
        # detto — e a quella pensa il ripasso in `stop`.
        eco = False
        if ev.source == "loopback":
            if ev.text:
                self._eco.registra_uscita(ev.t_start_ms, ev.text)
        elif ev.is_final and ev.text and self._eco.e_eco(ev.t_start_ms, ev.text):
            # Il microfono ha ripreso l'altoparlante: non sono parole di chi
            # registra. Attribuirgliele significa invertire chi ha detto cosa
            # nel riassunto, che è peggio di perdere una riga.
            eco = True
            self._echi_scartati += 1

        # Definitivo senza testo: la frase si è chiusa senza produrre niente.
        # Il provvisorio va tolto, non lasciato lì come riga vuota.
        if ev.is_final and not ev.text:
            self._scarta_aperto(ev.source)
            if self._on_event is not None:
                self._on_event(ev)
            return

        if aperto is None:
            seg_id = self.store.add_segment(
                session_id,
                ev.source,
                ev.t_start_ms,
                ev.t_end_ms,
                ev.text,
                is_final=ev.is_final,
                testo_originale=originale,
            )
            self._open_segments[ev.source] = _Aperto(seg_id, ev.t_start_ms, ev.text)
        else:
            seg_id = aperto.id
            self.store.refine_segment(
                aperto.id,
                ev.text,
                t_end_ms=ev.t_end_ms,
                is_final=ev.is_final,
                testo_originale=originale,
            )
            aperto.testo = ev.text
        if ev.is_final:
            self._open_segments.pop(ev.source, None)

        if eco:
            # Scritta e marcata, non cancellata: sta fuori da riassunto, note
            # ed export (la esclude `Store.segments`) ma resta guardabile. Chi
            # legge la trascrizione deve poter controllare che sia davvero eco.
            self.store.marca_eco(seg_id)
            return

        if self._on_event is not None:
            self._on_event(ev)

    def _scarta_aperto(self, source: str) -> None:
        """Toglie il segmento provvisorio di una traccia, se ce n'è uno."""
        aperto = self._open_segments.pop(source, None)
        if aperto is not None:
            self.store.elimina_segmento(aperto.id)

    def _ripassa_eco(self, session_id: int) -> int:
        """Rigiudica l'eco a call finita, e marca quello che dal vivo era sfuggito.

        Non solleva: è l'ultimo gesto di una registrazione andata a buon fine,
        e una call intera non si perde perché il ripasso è inciampato.
        """
        try:
            righe = self.store.segments(session_id, only_final=True)
            mic = [s for s in righe if s.source == "mic"]
            loopback = [s for s in righe if s.source == "loopback"]
            if not mic or not loopback:
                return 0
            ids = eco_mod.ripassa(mic, loopback, soglia=self._eco.soglia)
            for seg_id in ids:
                self.store.marca_eco(seg_id)
            return len(ids)
        except Exception:  # pragma: no cover - il ripasso non fa perdere la call
            log.exception("Ripasso dell'eco non riuscito sulla sessione %d.", session_id)
            return 0

    # ------------------------------------------------------------ screenshot

    def add_screenshot(self, path: str | Path, **kwargs) -> tuple[int, int]:
        """Aggancia uno screenshot all'istante corrente della call.

        L'istante lo decide il recorder, non chi chiama: è la stessa timeline
        della trascrizione, e deve restare l'unica.
        """
        if self.session_id is None:
            raise RuntimeError("Nessuna registrazione in corso.")
        t_ms = self.now_ms()
        shot_id = self.store.add_screenshot(self.session_id, t_ms, str(path), **kwargs)

        # La lettura del testo avviene dopo, su un thread suo. Chi ha premuto la
        # scorciatoia sta seguendo una riunione: lo scatto deve risultare
        # istantaneo, e l'OCR costa qualche decimo di secondo.
        threading.Thread(
            target=self._leggi_testo, args=(shot_id, str(path)), daemon=True
        ).start()
        return shot_id, t_ms

    def _leggi_testo(self, shot_id: int, path: str) -> None:
        testo = ocr.leggi_testo(path)
        if testo:
            self.store.set_screenshot_ocr(shot_id, testo)

    # ------------------------------------------------------------ pausa/stop

    def pause(self) -> None:
        if self.clock is not None:
            self.clock.pause()

    def resume(self) -> None:
        if self.clock is not None:
            self.clock.resume()

    def stop(self) -> int | None:
        """Chiude la registrazione e restituisce l'id della sessione."""
        with self._lock:
            if self.clock is None or self.session_id is None:
                return None

            session_id = self.session_id
            if self._capture is not None:
                self._capture.stop()
                self._capture = None

            # Solo ora i trascrittori: fermandoli prima si perderebbe la frase
            # ancora in corso, che e' proprio quella a cui l'utente teneva
            # quando ha premuto stop.
            self._teardown_transcribers()

            # Le tracce si portano fino alla fine della call prima di chiuderle.
            # Chi smette di consegnare cinque minuti prima dello stop —
            # tipicamente il loopback, se nessuno riproduce più niente —
            # lascerebbe un file più corto della sessione, e chi lo confronta
            # con `durata_ms` per orientarsi dentro lo giudicherebbe
            # disallineato in tutta la sua lunghezza.
            fine_ms = self.clock.now_ms()
            for w in self._writers.values():
                w.porta_fino_a(fine_ms)

            percorsi = {s: w.stop() for s, w in self._writers.items()}
            for sorgente, w in self._writers.items():
                if w.silenzio_ricostruito_s > 1.0:
                    log.info(
                        "Traccia %s: %.0f s di silenzio ricostruito su %.0f s totali.",
                        sorgente,
                        w.silenzio_ricostruito_s,
                        w.durata_s,
                    )
            self._writers.clear()
            self.store.set_audio_paths(
                session_id,
                str(percorsi["mic"]) if percorsi.get("mic") else None,
                str(percorsi["loopback"]) if percorsi.get("loopback") else None,
            )
            # Ora che ogni frase dell'altoparlante esiste per intero, il
            # giudizio sull'eco si può rifare con tutto davanti. Dal vivo non
            # era possibile: la frase che spiega l'eco si chiude quasi sempre
            # dopo l'eco stesso, ed è così che ne passava una su tre (#59).
            self._echi_scartati += self._ripassa_eco(session_id)
            if self._echi_scartati:
                log.info(
                    "Marcate %d frasi in cui il microfono aveva ripreso l'altoparlante.",
                    self._echi_scartati,
                )
            if self._nomi_corretti:
                log.info(
                    "Rimessi a posto %d nomi propri dal glossario (livello %s).",
                    self._nomi_corretti,
                    self._glossario_livello,
                )

            self.store.end_session(session_id, self.clock.ended_at_ms)
            self.store.set_session_state(session_id, "ready")
            self.clock.stop()
            self.clock = None
            self.session_id = None
            self._open_segments.clear()
            return session_id

    def _teardown_transcribers(self) -> None:
        for t in self._transcribers.values():
            t.stop()
        self._transcribers.clear()

    def __enter__(self) -> Recorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
