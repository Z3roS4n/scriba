"""Riconosce quando il microfono ha ripreso l'audio dell'altoparlante.

Il problema, visto su una call vera: al minuto 12:09 l'interlocutore dice
"nessuna parte contatterà direttamente un cliente segnalato...", e tre secondi
dopo la stessa frase compare attribuita a chi registra. Non l'ha detta lui: il
microfono ha ripreso l'altoparlante.

Succede anche in cuffia — la capsula raccoglie sempre un po' di quello che esce
dai padiglioni — e in vivavoce è la regola. L'effetto è peggiore del rumore:
non produce testo sbagliato, produce testo *giusto attribuito alla persona
sbagliata*, e un riassunto costruito su quello inverte chi ha detto cosa.

Si riconosce dal confronto fra le due tracce, non dal suono: l'eco è una copia
ritardata di ciò che è appena uscito dalle casse, quindi le stesse parole
compaiono su entrambe le tracce a pochi secondi di distanza. Confrontare il
testo evita di dover fare cancellazione d'eco vera, che richiede allineamento
del segnale e un filtro adattivo.

## Quando si giudica conta quanto come

Il confronto funziona: misurato su sei call vere, segnala il 34,5% delle righe
del microfono confrontate con quelle dell'altoparlante lì accanto e lo 0,2%
confrontate con quelle di dieci minuti prima, dove eco non ce ne può essere.
Fra segnale e falso positivo c'è due ordini di grandezza.

A non funzionare era il **momento**. Una frase dell'altoparlante entra qui
quando si chiude, cioè dopo una pausa o dopo venticinque secondi; l'eco sul
microfono si chiude molto prima, perché è più smorzato e il rilevatore di voce
lo spezza a ogni avvallamento. Il filtro giudicava quindi una riga confrontandola
con una frase che non era ancora stata detta per intero, e nel 97-100% dei casi
sopravvissuti la frase che la spiegava si è chiusa dopo (#59).

Da qui due cose, che vanno insieme:

- dal vivo si annotano anche le **ipotesi provvisorie** dell'altoparlante, non
  solo le frasi chiuse: riduce la cecità, non la elimina — quello che l'altro
  non ha ancora finito di dire non lo sa nessuno;
- a call finita si **ripassa** (`ripassa`), quando ogni frase esiste per intero.
  È lì che si recupera ciò che dal vivo era impossibile sapere.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Protocol


class Riga(Protocol):
    """Il minimo che serve per giudicare una riga: quando, cosa, e quale.

    Un protocollo e non il `Segment` del database: così `ripassa` si prova con
    tre campi scritti a mano, senza aprire uno store.
    """

    id: int
    t_start_ms: int
    testo: str


# Quanto indietro guardare. L'eco arriva quasi subito, ma la trascrizione delle
# due tracce non è simultanea: una frase lunga sul loopback si chiude dopo.
FINESTRA_MS = 12_000

# Quanta parte delle parole deve coincidere. Sotto questa soglia due frasi
# simili sono probabilmente una conversazione — capita di ripetere quello che
# l'altro ha appena detto — e sopprimerle sarebbe peggio del problema.
SOGLIA = 0.72

# I tre livelli che l'utente sceglie in Impostazioni > Trascrizione. Il testo
# che legge lì è «Riconosce quando il microfono riprende l'altoparlante. Se
# alzi troppo, le sovrapposizioni di voce si perdono»: alzare il livello vuol
# dire scartare più a cuor leggero, quindi una soglia di somiglianza più
# bassa (basta assomigliarsi meno per essere giudicata eco).
#
# "medio" resta 0.72: è il valore di sempre, calibrato sulla call vera in
# cima a questo file (somiglianza ~0.9 fra le due tracce). Chi non tocca
# l'impostazione non deve vedere cambiare la trascrizione.
# "basso" sale a 0.85: serve una somiglianza quasi verbatim per scartare, e
# in cambio si accetta di lasciar passare qualche eco più smorzato — quello
# che "medio" avrebbe preso lo stesso, dato che il caso reale sta a ~0.9.
# "alto" scende a 0.55: scarta anche quando l'ASR diverge parecchio fra le
# due tracce (succede, l'eco è più smorzato dell'originale), al prezzo che il
# testo delle impostazioni dichiara — più sovrapposizioni vere finiscono
# buttate via.
SOGLIE_PER_LIVELLO: dict[str, float] = {
    "basso": 0.85,
    "medio": SOGLIA,
    "alto": 0.55,
}

# Sotto questa lunghezza non si giudica: "sì", "certo", "esatto" compaiono di
# continuo su entrambe le tracce senza essere eco.
MIN_PAROLE = 4


def soglia_per_livello(livello: str | None) -> float:
    """La soglia di somiglianza per il livello scelto nelle impostazioni.

    Un livello non riconosciuto — impostazioni salvate da una versione
    vecchia, file toccato a mano — non deve impedire la registrazione: si
    ripiega su "medio", lo stesso comportamento di prima che questa scelta
    esistesse.
    """
    return SOGLIE_PER_LIVELLO.get(livello or "medio", SOGLIE_PER_LIVELLO["medio"])


def _parole(testo: str) -> list[str]:
    senza_accenti = unicodedata.normalize("NFD", testo.lower())
    pulito = "".join(c for c in senza_accenti if unicodedata.category(c) != "Mn")
    return re.findall(r"\w+", pulito)


def somiglianza(a: str, b: str) -> float:
    """Quanto le parole di `a` compaiono in `b`, contando le ripetizioni.

    Non è una distanza fra stringhe: la trascrizione delle due tracce differisce
    sempre un po' — l'eco è più smorzato e qualche parola cambia — quindi conta
    quanto si sovrappone il vocabolario, non che i caratteri coincidano.
    """
    pa, pb = _parole(a), _parole(b)
    if not pa or not pb:
        return 0.0

    restanti = list(pb)
    comuni = 0
    for parola in pa:
        if parola in restanti:
            restanti.remove(parola)
            comuni += 1
    return comuni / len(pa)


def _spiegata_da(
    t_ms: int,
    testo: str,
    uscite: list[tuple[int, str]],
    *,
    soglia: float,
    finestra_ms: int,
) -> bool:
    """La regola, in un posto solo: questa riga del microfono è già stata detta?

    La usano sia il giudizio dal vivo sia il ripasso a call finita. Sono due
    momenti con informazioni diverse — e quella differenza è tutto il difetto
    #59 — ma il criterio deve restare uno: due regole che divergono darebbero
    trascrizioni diverse a seconda di quando le si guarda.
    """
    if len(_parole(testo)) < MIN_PAROLE:
        return False

    for t_uscita, detto in uscite:
        # L'eco segue quello che l'ha causato, ma le due trascrizioni si
        # chiudono in momenti diversi: si guarda anche un po' all'indietro.
        if not (-finestra_ms // 3 <= t_ms - t_uscita <= finestra_ms):
            continue
        if somiglianza(testo, detto) >= soglia:
            return True
    return False


class FiltroEco:
    """Tiene a mente cosa è uscito dalle casse, per riconoscerlo sul microfono.

    Si ricorda solo delle ultime frasi: oltre la finestra, una coincidenza è
    una coincidenza.
    """

    def __init__(self, *, finestra_ms: int = FINESTRA_MS, soglia: float = SOGLIA) -> None:
        self.finestra_ms = finestra_ms
        self.soglia = soglia
        self._uscite: list[tuple[int, str]] = []

    def registra_uscita(self, t_ms: int, testo: str) -> None:
        """Annota cosa sta dicendo l'altoparlante, finita o no la frase.

        Le ipotesi provvisorie contano quanto le definitive. Aspettare che la
        frase si chiuda vuol dire giudicare l'eco prima di sapere cosa l'ha
        causato: è esattamente ciò che lasciava passare una riga su tre (#59).

        Una nuova ipotesi della **stessa** frase sostituisce la precedente
        invece di aggiungersi: è la stessa frase, più lunga. Le due si
        riconoscono dall'istante di inizio, che una frase non cambia più.
        """
        if testo.strip():
            for i, (t, _) in enumerate(self._uscite):
                if t == t_ms:
                    self._uscite[i] = (t_ms, testo)
                    break
            else:
                self._uscite.append((t_ms, testo))
        self._dimentica(t_ms)

    def _dimentica(self, adesso_ms: int) -> None:
        limite = adesso_ms - self.finestra_ms * 3
        self._uscite = [(t, s) for t, s in self._uscite if t >= limite]

    def e_eco(self, t_ms: int, testo: str) -> bool:
        """Vero se questa frase del microfono è il ritorno dell'altoparlante."""
        return _spiegata_da(
            t_ms, testo, self._uscite, soglia=self.soglia, finestra_ms=self.finestra_ms
        )


def ripassa(
    mic: Sequence[Riga],
    loopback: Sequence[Riga],
    *,
    soglia: float = SOGLIA,
    finestra_ms: int = FINESTRA_MS,
) -> list[int]:
    """Rigiudica tutte le righe del microfono, a call finita.

    Dal vivo il filtro può confrontare solo con ciò che l'altoparlante ha già
    detto, e quasi sempre non basta: la frase che spiega l'eco si chiude dopo.
    Qui invece esistono tutte, e il giudizio si può dare per intero.

    Restituisce gli id da marcare. Non tocca niente: chi chiama decide cosa
    farne, e resta una funzione che si prova senza database.
    """
    uscite = [(r.t_start_ms, r.testo) for r in loopback if r.testo.strip()]
    return [
        r.id
        for r in mic
        if _spiegata_da(
            r.t_start_ms, r.testo, uscite, soglia=soglia, finestra_ms=finestra_ms
        )
    ]
