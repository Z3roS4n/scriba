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


#: La nota dei modelli locali: nel catalogo è la loro `descrizione`, ed è
#: l'unico testo del pannello Modelli che nasce nel core.
_MODELLI_EN: dict[str, str] = {
    "gemma-4-12b": "The default. Official Google conversion, QAT quantisation.",
    "qwen3.5-9b": "Faster and lighter. It follows instructions better, but the "
    "architecture is recent: check that the build supports it.",
    "gemma-4-26b-a4b": "Better quality, much slower. Only 3.8 billion parameters "
    "active per token: it fits in 10 GB of VRAM with the experts kept in RAM.",
    "parakeet-tdt-0.6b-v3": "The default local transcription, already in use by "
    "the application. The download (~640 MB, several files) is handled by "
    "onnx-asr: no byte-by-byte resuming and no pausing, but the library checks "
    "its integrity itself at every load.",
    "canary-1b-v2": "It is for the touch-up after the call, not for live "
    "transcription: it is the only one of the two you can impose a language on, "
    "and it is more accurate (WER 5.3% against 6.8% on Italian FLEURS, measured "
    "on this machine). Too slow to keep up with speech — 2.5 times Parakeet.",
    #: Non viene dal catalogo: la scrive `_descrivi_gestito` mentre il download
    #: affidato a una libreria esterna è in corso.
    "@in_corso": "downloading · it cannot be paused",
}


def nota_modello(model_id: str, nota_it: str, lingua: str) -> str:
    """La nota di un modello locale nella lingua chiesta."""
    return nota_it if lingua == "it" else _MODELLI_EN.get(model_id, nota_it)


#: I campi che si possono mandare a Notion: etichetta e riga di aiuto.
_CAMPI_NOTION_EN: dict[str, tuple[str, str]] = {
    "titolo": (
        "Task title",
        "It always goes in the database's title property: it is the only one Notion guarantees.",
    ),
    "descrizione": ("Description", "The detail of the task, when the model wrote one."),
    "assegnatario": (
        "Assignee",
        "The name as it was said in the call, not a Notion user.",
    ),
    "scadenza": ("Due date", "The date, when the call makes clear which one it is."),
    "priorita": ("Priority", "Low, medium, high or critical."),
    "stato": ("Done", "Ticked when the task is marked done in Scriba."),
    "prova": (
        "Evidence",
        "The sentences from the call the task comes from, with the minute. It is what makes it checkable.",
    ),
    "call": ("Call it came from", "The title of the meeting the task comes from."),
    "data_call": ("Call date", "When the meeting was held."),
    "link_call": ("Link to the call page", "The address of the page Scriba creates for the call."),
    "confidenza": ("Model confidence", "How sure the model was, from 0 to 1."),
    "da_rivedere": ("To review", "Ticked when Scriba suggests checking the task by hand."),
}


def campo_notion(campo_id: str, etichetta_it: str, aiuto_it: str, lingua: str) -> tuple[str, str]:
    """Etichetta e aiuto di un campo esportabile su Notion."""
    if lingua == "it":
        return etichetta_it, aiuto_it
    return _CAMPI_NOTION_EN.get(campo_id, (etichetta_it, aiuto_it))


#: Il modello dati del database remoto: tabelle e colonne, come si leggono
#: nella schermata in cui si sceglie cosa mandare fuori.
_TABELLE_SQL_EN: dict[str, tuple[str, str]] = {
    "call": ("Calls", "One row per meeting: when, how long it ran, whose it was."),
    "task": ("Tasks", "The commitments taken from the meeting, with the quote they come from."),
    "analisi": ("Summary and key points", "What the model produced, and with which model."),
    "trascrizione": ("Transcript", "Every sentence said, with the minute and the track it comes from."),
    "partecipante": ("Participants", "The voices recognised in the call, with the name if one was given."),
    "screenshot": (
        "Screenshots",
        "Only the data, not the images: path on the computer and the text read by OCR. "
        "The path opens nothing from somewhere else.",
    ),
}

#: Le colonne, per `tabella.colonna`: molte si ripetono fra tabelle e il nome
#: da solo non basterebbe a distinguerle.
_COLONNE_SQL_EN: dict[str, tuple[str, str]] = {
    "call.uuid": ("Identifier", "Stable: it never changes"),
    "call.titolo": ("Title", ""),
    "call.cliente": ("Client", "Empty when the call is not attributed"),
    "call.piattaforma": ("Platform", "Zoom, Teams, browser…"),
    "call.inizio": ("Start", ""),
    "call.fine": ("End", ""),
    "call.durata_ms": ("Length (ms)", ""),
    "call.stato": ("State", ""),
    "call.lingua": ("Language", ""),
    "call.note": ("Notes", "The ones written by hand on the card"),
    "task.uuid": ("Identifier", ""),
    "task.call_uuid": ("Call", "Which meeting it belongs to"),
    "task.titolo": ("Title", ""),
    "task.descrizione": ("Description", ""),
    "task.assegnatario": ("Assignee", ""),
    "task.scadenza": ("Due date", "Resolved into a real date"),
    "task.scadenza_detta": ("Due date as said", "“by the end of the month”: the ambiguity as it was"),
    "task.priorita": ("Priority", ""),
    "task.stato": ("State", ""),
    "task.confidenza": ("Confidence", "How much the model believes it, from 0 to 1"),
    "task.citazione": ("Quote", "The sentence the task comes from"),
    "task.citazione_ms": ("Minute of the quote", ""),
    "analisi.call_uuid": ("Call", ""),
    "analisi.tipo": ("Kind", "summary, key points…"),
    "analisi.contenuto": ("Content", ""),
    "analisi.modello": ("Model", ""),
    "analisi.provider": ("Engine", "local, anthropic, openai…"),
    "analisi.prodotta_at": ("Produced on", ""),
    "trascrizione.call_uuid": ("Call", ""),
    "trascrizione.indice": ("Position", "The order number inside the call"),
    "trascrizione.t_start_ms": ("From (ms)", ""),
    "trascrizione.t_end_ms": ("To (ms)", ""),
    "trascrizione.sorgente": ("Track", "mic = me, loopback = the others"),
    "trascrizione.parlante": ("Speaker", "Only if the call was diarised"),
    "trascrizione.testo": ("Text", ""),
    "partecipante.call_uuid": ("Call", ""),
    "partecipante.etichetta": ("Label", "“io”, “Voce 2”…"),
    "partecipante.ruolo": ("Role", "me | them"),
    "partecipante.nome": ("Name", ""),
    "screenshot.call_uuid": ("Call", ""),
    "screenshot.t_ms": ("Minute (ms)", ""),
    "screenshot.percorso": ("Local path", ""),
    "screenshot.ocr": ("Text read", ""),
    "screenshot.nota": ("Note", ""),
}


def tabella_sql(chiave: str, etichetta_it: str, descrizione_it: str, lingua: str) -> tuple[str, str]:
    """Nome e descrizione di una tabella del modello dati."""
    if lingua == "it":
        return etichetta_it, descrizione_it
    return _TABELLE_SQL_EN.get(chiave, (etichetta_it, descrizione_it))


def colonna_sql(
    tabella: str, colonna: str, etichetta_it: str, descrizione_it: str, lingua: str
) -> tuple[str, str]:
    """Nome e descrizione di una colonna del modello dati."""
    if lingua == "it":
        return etichetta_it, descrizione_it
    return _COLONNE_SQL_EN.get(f"{tabella}.{colonna}", (etichetta_it, descrizione_it))


