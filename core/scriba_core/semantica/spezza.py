"""Da segmenti di trascrizione a passaggi di discorso.

Il pezzo di parlato che si indicizza non è il segmento. Un segmento è quello
che il motore di trascrizione ha deciso di chiudere quando ha sentito una
pausa, e in una conversazione vera è spesso lungo tre parole: «sì», «esatto»,
«aspetta un attimo». Il vettore di «sì» non significa niente — somiglia a ogni
altro «sì» dell'archivio e a nient'altro — e riempirebbe i risultati di rumore
che somiglia a tutto.

Si raggruppano quindi i segmenti consecutivi finché non si è formato un pezzo
di discorso che si regge da solo: abbastanza lungo da avere un argomento,
abbastanza corto da poter essere letto come risultato di ricerca senza dover
aprire la call.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db.store import Segment

# Quanto è lungo un passaggio, in caratteri. Il numero non viene da una teoria:
# a 700 caratteri stanno dentro cinque o sei battute di conversazione, che è
# quanto serve perché un argomento si veda, e restano ben sotto i 512 token che
# il modello legge (in italiano un token vale circa tre caratteri, quindi ~230
# token: c'è margine anche per il parlato fitto).
CARATTERI = 700

# Sotto questa soglia un passaggio non sta in piedi da solo e viene attaccato
# al precedente invece di restare un risultato di ricerca da due parole.
MINIMO = 80

# Quanti segmenti dell'uno ricompaiono in capo all'altro. Serve per le frasi a
# cavallo del confine: senza sovrapposizione «il prezzo lo rivediamo / a
# settembre» diventa due passaggi che, presi singolarmente, non rispondono a
# nessuna delle due domande possibili.
CODA = 1


@dataclass(frozen=True)
class Passaggio:
    """Un pezzo di discorso, con il punto della call in cui è stato detto."""

    ord: int
    t_start_ms: int
    t_end_ms: int
    testo: str


def in_passaggi(
    segmenti: list[Segment],
    *,
    caratteri: int = CARATTERI,
    minimo: int = MINIMO,
    coda: int = CODA,
) -> list[Passaggio]:
    """Raggruppa i segmenti in passaggi indicizzabili.

    Si aspetta i segmenti già filtrati e in ordine di tempo — quelli che
    restituisce `Store.segments(only_final=True)`, che è anche l'unico posto in
    cui l'esclusione dell'eco è scritta una volta sola. I segmenti vuoti si
    scartano qui: una riga senza parole non è un pezzo di discorso, e in una
    trascrizione dal vivo ce ne sono.
    """
    utili = [s for s in segmenti if s.testo and s.testo.strip()]
    if not utili:
        return []

    passaggi: list[Passaggio] = []
    inizio = 0
    while inizio < len(utili):
        fine, lunghezza = inizio, 0
        while fine < len(utili) and lunghezza < caratteri:
            lunghezza += len(utili[fine].testo.strip()) + 1
            fine += 1
        _aggiungi(passaggi, utili[inizio:fine], minimo=minimo)
        if fine >= len(utili):
            break
        # Il gruppo successivo riparte qualche segmento indietro, così le frasi
        # a cavallo del confine appartengono a tutti e due. Mai più indietro di
        # un passo rispetto a dove si era: `inizio` deve crescere sempre,
        # altrimenti il ciclo non finisce.
        inizio = max(inizio + 1, fine - coda)

    return passaggi


def _aggiungi(passaggi: list[Passaggio], gruppo: list[Segment], *, minimo: int) -> None:
    """Chiude un gruppo, o lo attacca al precedente se è troppo corto."""
    if not gruppo:
        return
    testo = " ".join(s.testo.strip() for s in gruppo)
    # Troppo corto per essere un risultato: si allunga il precedente invece di
    # aggiungerne uno che nessuno vorrebbe leggere. Succede soprattutto in coda
    # alla call, dove restano i saluti.
    if passaggi and len(testo) < minimo:
        ultimo = passaggi[-1]
        passaggi[-1] = Passaggio(
            ord=ultimo.ord,
            t_start_ms=ultimo.t_start_ms,
            t_end_ms=max(ultimo.t_end_ms, gruppo[-1].t_end_ms),
            testo=f"{ultimo.testo} {testo}",
        )
        return
    passaggi.append(
        Passaggio(
            ord=len(passaggi),
            t_start_ms=gruppo[0].t_start_ms,
            t_end_ms=gruppo[-1].t_end_ms,
            testo=testo,
        )
    )
