"""Rifà la trascrizione di una call già registrata, con più cura.

Dal vivo trascrive Parakeet, che è l'unico abbastanza veloce — e che la lingua
non la sa ricevere: la deduce dall'audio a ogni finestra, e su spezzoni corti
sbaglia. Da lì le frasi in spagnolo dentro una call italiana (#41). A
registrazione conclusa nessuno aspetta più, e si può ripassare con Canary, che
la lingua la accetta davvero ed è anche più preciso (WER 5.3% contro 6.8%).

Il record non viene ricreato: si riscrive il testo dello stesso segmento. È ciò
che tiene valide le citazioni delle task, che puntano a questi id.

## Il vincolo che decide tutta la struttura

L'audio salvato **non è allineato all'orologio della call**, e su una traccia
in particolare non lo è per niente. Il loopback WASAPI non consegna pacchetti
mentre nessuna applicazione riproduce audio, e il file che ne esce è la
concatenazione dei pezzi consegnati: i silenzi non ci sono. Misurato sulle
registrazioni vere:

    call   sessione   loopback   scarto
       5    6595.0s    5166.9s   -21.7%
       4    7082.1s    7094.3s    +0.2%

Nella call 5 mancano ventiquattro minuti. Tagliare l'audio all'istante scritto
nel database, lì, darebbe la frase sbagliata — e la riscriverebbe sopra quella
giusta, che è il modo peggiore di fallire: silenzioso e distruttivo.

Per questo prima di riscrivere **si verifica**: si ritrascrivono alcune righe
sparse e si confronta il risultato con quello che c'è già. Se non si somigliano,
quella traccia si lascia stare e lo si dice. Non è una stima di rischio, è una
misura fatta sui dati di quella call.
"""

from __future__ import annotations

import logging
import re
import statistics
import threading
import wave
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

import numpy as np

from ..db.store import Store
from . import glossario

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000

# Quanto devono somigliarsi il testo vecchio e quello nuovo perché si possa
# credere che parlino dello stesso pezzo di audio. Un modello diverso riscrive
# parecchio, quindi la soglia non può essere alta; ma su audio disallineato la
# somiglianza crolla vicino a zero, e fra i due casi c'è un abisso, non una
# sfumatura.
SOMIGLIANZA_MINIMA = 0.45
# Quante righe si provano prima di decidere. Sparse lungo la call: un
# disallineamento che cresce nel tempo non si vede guardando solo l'inizio.
CAMPIONI_CONTROLLO = 5
# Quante parole deve avere una riga per valere come controllo.
#
# `somiglianza()` e' una distanza di edit **sulle parole**: su una riga da una
# parola il risultato puo' essere solo 1 o 0, e «Okay.» ritrascritto da un
# altro modello come «Ok» vale zero. In una conversazione vera meta' delle
# righe sono interiezioni, quindi prendendole a passo costante sull'indice si
# finiva a misurare la lunghezza delle frasi invece dell'allineamento: su una
# call di due ore, tre righe da una parola su cinque, mediana zero, e la
# rifinitura rifiutata su un audio lungo quanto doveva (#99).
PAROLE_MINIME_CONTROLLO = 8
# Sotto questa durata non si ripassa: non c'è abbastanza segnale perché il
# confronto voglia dire qualcosa, e non c'è niente da guadagnare.
DURATA_MINIMA_MS = 400


@dataclass
class EsitoTraccia:
    #: 'rifinita' | 'non_allineata' | 'non_verificabile' | 'assente' | 'vuota'
    stato: str
    esaminate: int = 0
    riscritte: int = 0
    somiglianza: float | None = None
    #: La frase italiana, come ripiego se il gettone non si conosce.
    motivo: str | None = None
    #: Il gettone da cui l'interfaccia scrive la frase, e i suoi valori.
    #: L'esito va sul websocket: qui la lingua di chi guarda non c'è.
    motivo_chiave: str | None = None
    motivo_valori: dict[str, Any] | None = None


@dataclass
class Esito:
    tracce: dict[str, EsitoTraccia] = field(default_factory=dict)
    nomi_corretti: int = 0

    @property
    def riscritte(self) -> int:
        return sum(t.riscritte for t in self.tracce.values())

    @property
    def qualcosa_e_cambiato(self) -> bool:
        return self.riscritte > 0


class Interrotta(Exception):
    """Chiesto di fermarsi fra una riga e l'altra."""


# --------------------------------------------------------------- somiglianza


def _parole(s: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", s.lower(), flags=re.UNICODE).split()


def somiglianza(a: str, b: str) -> float:
    """Quanto due trascrizioni dicono la stessa cosa, fra 0 e 1.

    Distanza di edit sulle parole, normalizzata. Non misura la qualità: misura
    se stiamo guardando lo stesso pezzo di audio.
    """
    x, y = _parole(a), _parole(b)
    if not x and not y:
        return 1.0
    if not x or not y:
        return 0.0
    riga = list(range(len(y) + 1))
    for i, p in enumerate(x, start=1):
        prec, riga[0] = riga[0], i
        for j, q in enumerate(y, start=1):
            att = riga[j]
            riga[j] = min(riga[j] + 1, riga[j - 1] + 1, prec + (p != q))
            prec = att
    return max(0.0, 1.0 - riga[-1] / max(len(x), len(y)))


# ------------------------------------------------------------------- audio


def leggi_traccia(percorso: str | Path) -> np.ndarray:
    """Carica una traccia salvata: mono, 16 kHz, PCM a 16 bit (vedi writer.py)."""
    with wave.open(str(percorso), "rb") as w:
        if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1:
            raise ValueError(
                f"{Path(percorso).name}: attesi 1 canale a {SAMPLE_RATE} Hz, "
                f"trovati {w.getnchannels()} a {w.getframerate()}"
            )
        grezzo = w.readframes(w.getnframes())
    return np.frombuffer(grezzo, dtype=np.int16).astype(np.float32) / 32768.0


class _Righello:
    """Converte l'istante della call nella posizione dentro il file.

    Lo scarto fra le due durate è quasi sempre costante — la scheda audio non
    campiona esattamente alla frequenza dichiarata — e allora basta una
    proporzione. Quando invece l'audio ha dei buchi dentro, la proporzione è
    sbagliata **a tratti** e nessun fattore la aggiusta: è il caso che il
    controllo a campione deve intercettare, non questo oggetto.
    """

    def __init__(self, campioni: int, durata_ms: int | None) -> None:
        self.campioni = campioni
        attesi = int((durata_ms or 0) / 1000 * SAMPLE_RATE)
        self.fattore = campioni / attesi if attesi > 0 else 1.0

    def taglia(self, audio: np.ndarray, t_start_ms: int, t_end_ms: int) -> np.ndarray:
        a = int(t_start_ms / 1000 * SAMPLE_RATE * self.fattore)
        b = int(t_end_ms / 1000 * SAMPLE_RATE * self.fattore)
        return audio[max(0, a) : min(len(audio), max(a, b))]


# ------------------------------------------------------------------ passata


def _abbastanza_lunga(s) -> bool:
    return len(_parole(s.testo)) >= PAROLE_MINIME_CONTROLLO


def _campioni_sparsi(segmenti: list, quanti: int) -> list:
    """Righe distribuite lungo la call, e abbastanza lunghe da dire qualcosa.

    Distribuite perche' un disallineamento che cresce nel tempo non si vede
    guardando solo l'inizio; lunghe perche' su poche parole il confronto non
    ha sfumature. Se righe lunghe non ce ne sono si ripiega su tutte, e chi
    chiama lo scopre da `_controlla`: e' una risposta che non si puo' dare,
    non un no.
    """
    fra = [s for s in segmenti if _abbastanza_lunga(s)] or segmenti
    if len(fra) <= quanti:
        return list(fra)
    passo = len(fra) / quanti
    return [fra[int(i * passo)] for i in range(quanti)]


def _controlla(
    motore, audio, righello, segmenti, lingua, annulla=None
) -> tuple[float, int, bool]:
    """Ritrascrive qualche riga e dice quanto somiglia a ciò che c'è già.

    Il terzo valore dice se le righe provate potevano rispondere: sotto le
    `PAROLE_MINIME_CONTROLLO` la somiglianza e' un lancio di moneta, e una
    mediana di lanci di moneta non e' un giudizio.
    """
    scelti = _campioni_sparsi(segmenti, CAMPIONI_CONTROLLO)
    attendibile = len(scelti) >= 2 and all(_abbastanza_lunga(s) for s in scelti)
    punti = []
    for s in scelti:
        if annulla is not None and annulla.is_set():
            raise Interrotta("interrotta dall'utente")
        pezzo = righello.taglia(audio, s.t_start_ms, s.t_end_ms)
        if pezzo.size == 0:
            punti.append(0.0)
            continue
        nuovo = motore.transcribe(pezzo, language=lingua)
        punti.append(somiglianza(s.testo, nuovo))
    return (statistics.median(punti) if punti else 0.0), len(punti), attendibile


def rifinisci(
    store: Store,
    session_id: int,
    motore,
    *,
    lingua: str = "it",
    termini: list[str] | None = None,
    livello_glossario: str = glossario.LIVELLO_PREDEFINITO,
    on_progresso=None,
    annulla: threading.Event | None = None,
) -> Esito:
    """Ripassa la trascrizione di una call, traccia per traccia.

    Non tocca gli id: `refine_segment` riscrive il testo dello stesso record, e
    `testo_originale` conserva com'era — se non c'è già, perché il primo
    originale (quello che ha prodotto la trascrizione dal vivo) vale più di
    ogni versione successiva.
    """
    sessione = store.get_session(session_id)
    if sessione is None:
        raise ValueError(f"Sessione {session_id} inesistente.")

    durata_ms = sessione["durata_ms"]
    segmenti = [s for s in store.segments(session_id, only_final=True) if s.testo.strip()]
    esito = Esito()

    percorsi = {"mic": sessione["audio_mic_path"], "loopback": sessione["audio_loop_path"]}
    da_fare = sum(
        1
        for s in segmenti
        if percorsi.get(s.source) and s.t_end_ms - s.t_start_ms >= DURATA_MINIMA_MS
    )
    fatte = 0

    for traccia, percorso in percorsi.items():
        suoi = [
            s
            for s in segmenti
            if s.source == traccia and s.t_end_ms - s.t_start_ms >= DURATA_MINIMA_MS
        ]
        if not percorso or not Path(percorso).exists():
            esito.tracce[traccia] = EsitoTraccia(
                "assente",
                motivo="Audio non trovato sul disco.",
                motivo_chiave="audio_assente",
            )
            continue
        if not suoi:
            esito.tracce[traccia] = EsitoTraccia("vuota")
            continue

        try:
            audio = leggi_traccia(percorso)
        except Exception as exc:
            esito.tracce[traccia] = EsitoTraccia("assente", motivo=str(exc))
            log.warning("Traccia %s non leggibile: %s", traccia, exc)
            continue

        righello = _Righello(len(audio), durata_ms)
        media, provate, attendibile = _controlla(motore, audio, righello, suoi, lingua, annulla)
        if media < SOMIGLIANZA_MINIMA and not attendibile:
            # Non e' un no: e' che non si e' potuto chiedere. Le righe provate
            # sono troppo corte perche' il confronto voglia dire qualcosa, e
            # dare la colpa all'audio sarebbe affermare una cosa non misurata.
            esito.tracce[traccia] = EsitoTraccia(
                "non_verificabile",
                esaminate=provate,
                somiglianza=media,
                motivo=(
                    "Non ci sono righe abbastanza lunghe per capire se l'audio "
                    f"corrisponde alla trascrizione ({provate} righe di controllo, "
                    "troppo corte perche' il confronto significhi qualcosa)."
                ),
                motivo_chiave="poche_righe_lunghe",
                motivo_valori={"righe": provate},
            )
            log.warning(
                "Rifinitura non verificabile su %s della sessione %d: righe troppo corte",
                traccia,
                session_id,
            )
            continue
        if media < SOMIGLIANZA_MINIMA:
            # Il caso del loopback con i silenzi mancanti. Riscrivere qui
            # significherebbe mettere sotto ogni riga il testo di un'altra.
            #
            # La causa si da' come probabile, non come accertata: qui si e'
            # misurata una somiglianza bassa su righe che potevano dire la
            # loro, e questa e' la spiegazione che di solito la produce.
            esito.tracce[traccia] = EsitoTraccia(
                "non_allineata",
                esaminate=provate,
                somiglianza=media,
                motivo=(
                    "Il testo ritrascritto non corrisponde a quello salvato "
                    f"(somiglianza {media:.0%} su {provate} righe di controllo): "
                    "audio e trascrizione sembrano scorrere su tempi diversi. "
                    "Di solito succede sulla traccia degli altri, quando durante "
                    "la call ci sono stati lunghi tratti senza audio in riproduzione."
                ),
                motivo_chiave="non_allineata",
                motivo_valori={"somiglianza": f"{media:.0%}", "righe": provate},
            )
            log.warning(
                "Rifinitura saltata su %s della sessione %d: somiglianza %.2f",
                traccia,
                session_id,
                media,
            )
            continue

        riscritte = 0
        for s in suoi:
            if annulla is not None and annulla.is_set():
                raise Interrotta("interrotta dall'utente")
            pezzo = righello.taglia(audio, s.t_start_ms, s.t_end_ms)
            fatte += 1
            if on_progresso is not None:
                on_progresso(fatte, da_fare, traccia)
            if pezzo.size == 0:
                continue
            nuovo = motore.transcribe(pezzo, language=lingua).strip()
            if not nuovo:
                # La passata non ha prodotto niente: si tiene quello che c'era.
                # Una riga vuota qui cancellerebbe una frase che esisteva.
                continue
            if termini:
                nuovo, cambi = glossario.correggi(
                    nuovo, termini, livello=livello_glossario
                )
                esito.nomi_corretti += len(cambi)
            if nuovo == s.testo:
                continue
            store.refine_segment(s.id, nuovo, testo_originale=s.testo)
            riscritte += 1

        esito.tracce[traccia] = EsitoTraccia(
            "rifinita", esaminate=len(suoi), riscritte=riscritte, somiglianza=media
        )

    return esito
