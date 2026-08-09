"""La lingua dell'interfaccia, per i testi che nascono nel core.

Alcune stringhe che l'utente legge non stanno nel renderer: i nomi e le
descrizioni dei motori di analisi, i titoli delle fasi, i messaggi d'errore.
Arrivano già scritte e vengono mostrate così come sono, quindi con
l'interfaccia in inglese restavano in italiano — un pannello metà e metà.

**Come arriva la lingua.** Nell'intestazione `Accept-Language` di ogni
richiesta, aggiunta in un punto solo dal processo principale (`coreFetch`).
Nessuna rotta ha dovuto cambiare firma, e nessuno può dimenticarsi di passarla
al prossimo giro: o c'è per tutte, o per nessuna.

Non da `settings`, che pure ce l'ha: lì la scelta può valere `sistema`, e chi
la risolve è il processo che conosce la lingua del sistema operativo. Il core
non deve indovinarla.

**Questo non è `ai/lingue.py`.** Quello è la lingua della *call*, e decide in
che lingua il modello scrive riassunto e task. Questa è la lingua di chi
guarda. Una riunione italiana letta da un'interfaccia inglese è il caso
normale, e i due file non si parlano.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Header

LINGUE = ("it", "en")
PREDEFINITA = "it"


def lingua_da_header(accept_language: str | None) -> str:
    """La prima lingua conosciuta in `Accept-Language`, o l'italiano.

    Si accetta anche la forma regionale (`en-GB`, `it_IT`): rifiutarla vorrebbe
    dire ripiegare sull'italiano per un'interfaccia che la sua lingua l'aveva
    dichiarata.
    """
    if not accept_language:
        return PREDEFINITA
    for pezzo in accept_language.split(","):
        codice = pezzo.split(";")[0].strip().lower().replace("_", "-")
        if not codice:
            continue
        base = codice.split("-")[0]
        if base in LINGUE:
            return base
    return PREDEFINITA


async def _lingua(accept_language: Annotated[str | None, Header()] = None) -> str:
    return lingua_da_header(accept_language)


#: Da usare come parametro nelle rotte che restituiscono testo per l'utente.
LinguaUI = Annotated[str, Depends(_lingua)]


# --------------------------------------------------------------- cataloghi
#
# Solo i testi che il core produce e l'interfaccia mostra senza rielaborarli.
# Gli identificatori — `local`, `anthropic`, `recorded` — non stanno qui: si
# traducono dove si mostrano, mai dove si confrontano.

_MOTORI_EN: dict[str, dict[str, str]] = {
    "local": {
        "etichetta": "Local model",
        "descrizione": "Nothing leaves the computer. Slower: an hour-long call "
        "takes about ten minutes.",
        "rimedio": "Download and start the local model from Settings.",
    },
    "claude-cli": {
        "etichetta": "Claude subscription",
        "descrizione": "Uses the subscription you already have, no metered cost. "
        "About three minutes for an hour-long call. The transcript is sent to Anthropic.",
        "rimedio": "Install Claude Code (the `claude` executable) and sign in to your "
        "subscription with `claude auth login`. If it used to work, the session has "
        "expired: sign in again.",
    },
    "anthropic": {
        "etichetta": "Anthropic API",
        "descrizione": "Requires a key. Billed by usage.",
        "rimedio": "Add an Anthropic API key in Settings.",
    },
    "openai": {
        "etichetta": "OpenAI API",
        "descrizione": "Requires a key. Billed by usage.",
        "rimedio": "Add an OpenAI API key in Settings.",
    },
}

_FASI_EN: dict[str, str] = {
    "riassunto": "Summary",
    "salienti": "Key points",
    "task": "Extracting tasks",
    "unione": "Merging references",
}


def motore(info: dict[str, Any], provider: str, lingua: str) -> dict[str, Any]:
    """`info` di un motore, con i suoi tre testi nella lingua chiesta.

    Torna una copia: la tabella dei motori è un modulo condiviso, e scriverci
    dentro vorrebbe dire che la prima richiesta in inglese la lascia inglese
    per tutti.
    """
    if lingua == "it":
        return dict(info)
    fuori = dict(info)
    fuori.update(_MOTORI_EN.get(provider, {}))
    return fuori


def fase(chiave: str, titolo_it: str, lingua: str) -> str:
    """Il titolo di una fase dell'analisi."""
    return titolo_it if lingua == "it" else _FASI_EN.get(chiave, titolo_it)
