"""Le call che sono lo stesso discorso ripreso più volte.

Un cliente seguito per mesi non è una call, sono otto, e ognuna riprende dove
si era rimasti. Chi chiede «quando consegniamo?» a un archivio che guarda una
call alla volta rischia la risposta del 3 marzo — quella **superata** — con la
stessa faccia di quella giusta (#106).

Cosa vuol dire «logicamente consecutive», qui dentro: **stesso cliente, e non
troppo tempo in mezzo**. Nient'altro. In particolare *non* si misura se due
call parlano della stessa cosa, e non è una dimenticanza:

- una soglia di somiglianza fra due call andrebbe tarata, e i punteggi del
  modello che avremmo usato per tararla stanno tutti fra 0,80 e 0,90 anche fra
  frasi che non c'entrano niente (vedi `indice.MARGINE`): sarebbe un numero
  con l'aria di significare qualcosa;
- a giudicare se il discorso è lo stesso è bravo il modello di linguaggio, che
  i passaggi li legge. Gli si consegna la catena dicendogli che è una catena,
  e se la call di marzo parla d'altro lo dice lui.

Le call senza cliente restano fuori: sono l'unico caso in cui non esiste
nemmeno la parentela certa, e metterle insieme per vicinanza di data
vorrebbe dire unire due riunioni con due persone diverse capitate lo stesso
giorno.
"""

from __future__ import annotations

from dataclasses import dataclass

# Quanto può passare fra due call perché siano ancora lo stesso discorso.
#
# Trenta giorni: non è misurato e non c'è modo di misurarlo senza un archivio
# vero da guardare, quindi vale quello che vale — una riunione di
# aggiornamento mensile resta attaccata alla precedente, due call a sei mesi
# di distanza no. È un parametro, e la scelta si vede: l'interfaccia mostra
# quali call ha unito, così un accostamento sbagliato si nota invece di
# restare dentro una risposta.
GIORNI = 30
GIORNI_MS = 86_400_000


@dataclass(frozen=True)
class Catena:
    """Call dello stesso cliente vicine nel tempo, dalla più vecchia."""

    client_id: int
    session_ids: list[int]

    @property
    def unita(self) -> bool:
        return len(self.session_ids) > 1


def catene(
    call: list[tuple[int, int | None, int | None]], *, giorni: int = GIORNI
) -> list[Catena]:
    """Raggruppa `(session_id, client_id, started_at)` in catene.

    Restituisce anche le catene da una call sola: chi chiama deve poter
    trattare tutto allo stesso modo, e «questa non ha compagne» è
    un'informazione, non un caso da saltare.
    """
    per_cliente: dict[int, list[tuple[int, int]]] = {}
    sole: list[Catena] = []
    for session_id, client_id, quando in call:
        if client_id is None or quando is None:
            # Senza cliente o senza data non c'è parentela da riconoscere: la
            # call resta per conto suo invece di essere accostata per caso.
            sole.append(Catena(client_id=-1, session_ids=[session_id]))
            continue
        per_cliente.setdefault(client_id, []).append((quando, session_id))

    fuori: list[Catena] = []
    limite = giorni * GIORNI_MS
    for client_id, righe in per_cliente.items():
        righe.sort()
        corrente = [righe[0][1]]
        for (prima, _), (dopo, session_id) in zip(righe, righe[1:], strict=False):
            if dopo - prima > limite:
                fuori.append(Catena(client_id=client_id, session_ids=corrente))
                corrente = []
            corrente.append(session_id)
        fuori.append(Catena(client_id=client_id, session_ids=corrente))

    return fuori + sole
