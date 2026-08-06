"""Rimette in piedi i nomi propri che il modello ha sentito male.

Un nome che non è nel vocabolario del modello viene indovinato da capo a ogni
occorrenza, e ogni volta l'ipotesi è diversa: nella stessa call «Clotilde»
diventa *Tilde*, *Cotilde* e *Protile*. Non è un problema estetico — una task
assegnata a *Giulio* quando l'aveva presa Giulia è sbagliata, e cercare
«Clotilde» nell'archivio non trova la call in cui se n'è parlato per mezz'ora.

Parakeet non ha un aggancio per suggerirgli un vocabolario: le famiglie
transducer non hanno un punto in cui infilarlo, e `onnx-asr` non ne espone uno.
Quello che si può fare è correggere il testo **dopo**, confrontandolo con i
pochi nomi che si sanno già — i clienti, chi partecipa, i prodotti.

## Il rischio, che è l'unica cosa difficile qui

Allargare la rete abbastanza da prendere *Protile* (tre modifiche su otto
lettere) vuol dire prendere anche **Matilde**, che è un'altra persona. Correggere
un nome giusto in un nome sbagliato è peggio del difetto che si sta risolvendo:
il primo lo si vede rileggendo, il secondo no.

Da qui le tre regole di questo modulo:

1. **Il livello lo sceglie chi usa l'app.** `prudente` (di default) corregge solo
   ciò che è quasi identico. Gli altri due allargano, e chi li accende lo sa.
2. **Nel dubbio non si tocca.** Se due termini del glossario sono entrambi
   compatibili con la stessa parola, non si corregge: i termini vicini fra loro
   si proteggono a vicenda.
3. **L'originale si conserva.** Chi chiama tiene da parte il testo di partenza,
   così la correzione resta annullabile e verificabile.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Le parole, con la loro posizione: serve a ricostruire il testo con la
# punteggiatura e le spaziature originali invece di riassemblarlo a pezzi.
_PAROLA = re.compile(r"\w+", re.UNICODE)

LIVELLI = ("prudente", "medio", "aggressivo")
LIVELLO_PREDEFINITO = "prudente"


@dataclass(frozen=True)
class Correzione:
    """Una parola riscritta, con quello che c'era prima."""

    trovato: str
    termine: str
    inizio: int
    fine: int


def normalizza(s: str) -> str:
    """Minuscole senza accenti: «Andrè» e «ANDRE» sono la stessa parola."""
    scomposto = unicodedata.normalize("NFD", s.casefold())
    return "".join(c for c in scomposto if not unicodedata.combining(c))


def distanza(a: str, b: str) -> int:
    """Quante modifiche separano due parole (Levenshtein).

    Iterativa su una riga sola: i termini di un glossario sono corti e questa
    gira una volta per parola trascritta per termine.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    riga = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        precedente, riga[0] = riga[0], i
        for j, cb in enumerate(b, start=1):
            attuale = riga[j]
            riga[j] = min(
                riga[j] + 1,          # cancellazione
                riga[j - 1] + 1,      # inserimento
                precedente + (ca != cb),  # sostituzione
            )
            precedente = attuale
    return riga[-1]


def sottostringa_comune(a: str, b: str) -> int:
    """Il tratto più lungo che le due parole hanno in comune, di fila.

    È l'ancora che tiene onesta la distanza di edit: *Protile* e *Clotilde*
    distano tre modifiche — tante — ma condividono `otil`, e senza un pezzo
    intero in comune una distanza così larga prenderebbe qualunque cosa.
    """
    if not a or not b:
        return 0
    prec = [0] * (len(b) + 1)
    massimo = 0
    for ca in a:
        corrente = [0] * (len(b) + 1)
        for j, cb in enumerate(b, start=1):
            if ca == cb:
                corrente[j] = prec[j - 1] + 1
                massimo = max(massimo, corrente[j])
        prec = corrente
    return massimo


def _limiti(candidato: str, termine: str, livello: str) -> tuple[int, int]:
    """Quanto può discostarsi una parola per essere ancora quel termine.

    Restituisce `(distanza massima, sottostringa comune minima)`. Le soglie
    crescono con la lunghezza: una modifica su tre lettere cambia la parola, su
    dieci quasi no.

    I tre livelli si distinguono su *come* è sbagliata la parola, non solo su
    quanto. *Tilde* e *Protile* distano tutti e due tre modifiche da *Clotilde*,
    ma il primo è un pezzo intatto del nome con le lettere di testa mangiate, il
    secondo è il nome con dentro altre lettere. Il livello `medio` prende il
    primo e non il secondo, ed è la sottostringa comune a separarli.
    """
    n = len(termine)
    if n < 5:
        # Su quattro lettere o meno una modifica è già un'altra parola.
        return 0, n
    if livello == "aggressivo":
        # Prende *Protile* → *Clotilde*: tre modifiche su otto. È tanto, e per
        # questo pretende almeno metà nome di fila in comune.
        return max(1, int(n * 0.4)), max(3, (n + 1) // 2)
    if livello == "medio":
        # La parola dev'essere quasi tutta dentro il termine, di fila: si
        # perdonano le lettere mancanti in testa o in coda, non quelle diverse
        # in mezzo.
        return max(1, n // 2 - 1), max(4, len(candidato) - 1)
    # prudente: una lettera sola di scarto.
    return 1, 0


def _compatibile(candidato: str, termine: str, livello: str, *, proprio: bool) -> bool:
    """La parola trascritta può essere quel termine?

    `proprio` dice se la parola nel testo ha l'aria di un nome proprio. Senza
    quel segnale si corregge **solo** ciò che combacia già: «totale» dista una
    lettera da «Tonale», e con un glossario che contiene la seconda ogni
    preventivo diventerebbe un'automobile.
    """
    if candidato == termine:
        return True
    if not proprio:
        return False
    max_distanza, min_comune = _limiti(candidato, termine, livello)
    if max_distanza == 0:
        return False
    # Una differenza di lunghezza superiore alla distanza ammessa è già di per
    # sé oltre soglia: si scarta senza far girare la matrice.
    if abs(len(candidato) - len(termine)) > max_distanza:
        return False
    if sottostringa_comune(candidato, termine) < min_comune:
        return False
    return distanza(candidato, termine) <= max_distanza


def _termini_validi(termini: list[str]) -> list[str]:
    """Scarta i vuoti e i doppioni, tiene l'ordine di inserimento."""
    fuori: list[str] = []
    visti: set[str] = set()
    for t in termini:
        pulito = " ".join(t.split())
        chiave = normalizza(pulito)
        if pulito and chiave not in visti:
            visti.add(chiave)
            fuori.append(pulito)
    return fuori


def correggi(
    testo: str, termini: list[str], *, livello: str = LIVELLO_PREDEFINITO
) -> tuple[str, list[Correzione]]:
    """Riscrive nel testo i termini del glossario che il modello ha storpiato.

    Restituisce il testo corretto e l'elenco di ciò che è cambiato. Se non
    cambia niente, la prima è la stringa di partenza e la seconda è vuota.
    """
    if livello not in LIVELLI:
        livello = LIVELLO_PREDEFINITO
    validi = _termini_validi(termini)
    if not testo or not validi:
        return testo, []

    parole = [(m.start(), m.end(), normalizza(m.group())) for m in _PAROLA.finditer(testo)]
    if not parole:
        return testo, []

    # I termini di più parole si provano per primi: «Banca Sella» deve vincere
    # su «Sella» da solo, altrimenti la seconda metà risulta già corretta e la
    # prima resta com'era.
    per_lunghezza = sorted(validi, key=lambda t: -len(t.split()))

    correzioni: list[Correzione] = []
    occupate: set[int] = set()

    for termine in per_lunghezza:
        n = len(termine.split())
        atteso = normalizza(" ".join(termine.split()))
        for i in range(len(parole) - n + 1):
            if any(k in occupate for k in range(i, i + n)):
                continue
            candidato = " ".join(p[2] for p in parole[i : i + n])
            inizio, fine = parole[i][0], parole[i + n - 1][1]
            originale = testo[inizio:fine]
            # Un termine di più parole porta la propria prova: che due parole di
            # fila siano entrambe quasi giuste non capita per caso. Su una
            # parola sola serve invece il segnale della maiuscola, altrimenti si
            # correggono le parole comuni.
            proprio = n > 1 or originale[:1].isupper()

            if not _compatibile(candidato, atteso, livello, proprio=proprio):
                continue
            # Nel dubbio non si tocca: se un altro termine è altrettanto
            # compatibile, la parola resta com'è. È ciò che impedisce di
            # trasformare Matilde in Clotilde quando ci sono tutte e due.
            altri = [
                a
                for a in validi
                if a != termine
                and len(a.split()) == n
                and _compatibile(
                    candidato, normalizza(" ".join(a.split())), livello, proprio=proprio
                )
            ]
            if altri:
                continue

            if originale != termine:
                correzioni.append(Correzione(originale, termine, inizio, fine))
            occupate.update(range(i, i + n))

    if not correzioni:
        return testo, []

    # Da destra a sinistra, così gli indici di quelle ancora da applicare
    # restano quelli calcolati sul testo di partenza.
    fuori = testo
    for c in sorted(correzioni, key=lambda c: -c.inizio):
        fuori = fuori[: c.inizio] + c.termine + fuori[c.fine :]
    return fuori, sorted(correzioni, key=lambda c: c.inizio)
