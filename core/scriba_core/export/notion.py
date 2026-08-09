"""Connettore Notion: una pagina per call, più una riga per ogni task
confermata nel database indicato.

**Idempotenza.** Rieseguire l'invio non deve duplicare niente:

- l'id della pagina della call si salva in un piccolo file accanto al
  database (`export_notion.json`) e le esecuzioni successive la aggiornano
  invece di ricrearla;
- l'id di ogni riga-task si salva nelle colonne `export_ref`/`export_status`
  che lo schema (`db/schema.sql`) già prevede per questo scopo — non serve
  aggiungere altro stato, e non tocchiamo `db/store.py` (fuori dal perimetro
  di questo lavoro) per farlo: si scrive direttamente con `store.tx()`, che è
  già l'API pubblica pensata per le scritture.

Duplicare le task di una riunione dentro il sistema di lavoro di qualcuno è un
danno vero, non un fastidio: da qui il controllo prima di ogni creazione. Per
lo stesso motivo, cambiare database azzera gli id remoti (`_azzera_riferimenti`):
tenerli significherebbe aggiornare righe nel database vecchio e lasciare vuoto
quello nuovo, riportando «aggiornati» come se fosse andato tutto bene.

**Credenziali.** Il token non vive in `settings.json` — quel file e la sua
classe `Settings` non sono nel perimetro di questo lavoro, e mescolarci un
formato di credenziali diverso da `llm.api_key` avrebbe significato
cambiarlo. Verso l'interfaccia vale comunque la stessa regola:
si dice *se* il token c'è, mai *quale sia* (vedi `stato()`).

**Quali dati vanno in quali colonne.** Lo decide l'utente, non il connettore:
`CAMPI` è l'elenco di quello che Scriba sa di una task, `mappa` (nel file di
configurazione) dice per ognuno il nome della proprietà Notion che lo deve
ricevere, e un campo assente dalla mappa non viene mandato. La corrispondenza
per nome che c'era prima sopravvive in `proponi_mappa` come *proposta* da
mostrare all'utente già compilata, e come ripiego per chi aveva collegato
Notion quando la mappa non esisteva ancora.

Il titolo è l'eccezione: ogni database Notion ha una e una sola proprietà di
tipo `title`, quindi non c'è niente da scegliere e ci va sempre il titolo della
task.

Chi non ha un database adatto se lo fa creare da qui (`crea_database`),
scegliendo quali campi gli interessano: le colonne nascono col tipo giusto e la
mappa è nota per costruzione.

Non verificato con un vero account Notion (nessuna credenziale disponibile in
questo giro): i test coprono la logica con le chiamate HTTP simulate.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ..db.store import Store
from ..i18n import campo_notion
from ._util import mmss
from .json_export import costruisci_payload

API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Quanti blocchi per chiamata: il limite di Notion è 100, si resta sotto per
# margine invece di inseguirlo esatto.
_BLOCCHI_PER_CHIAMATA = 90

# Quante pagine di risultati scorrere cercando database e pagine: chi ne ha di
# più di così non li trova scorrendo un elenco, li cerca per nome.
_PAGINE_DI_RICERCA = 5


class NotionError(RuntimeError):
    """La chiamata a Notion non è andata a buon fine, o manca la configurazione."""


# ------------------------------------------------------------- campi mappabili


@dataclass(frozen=True)
class Campo:
    """Un dato che Scriba sa di una task, e dove può finire in Notion.

    `tipi` sono i tipi di proprietà Notion che possono riceverlo, in ordine di
    preferenza: il primo è quello usato quando il database lo creiamo noi.
    """

    id: str
    etichetta: str
    aiuto: str
    tipi: tuple[str, ...]
    nome_notion: str
    consigliato: bool = True
    obbligatorio: bool = False


CAMPO_TITOLO = Campo(
    "titolo",
    "Titolo della task",
    "Va sempre nella proprietà titolo del database: è l'unica che Notion garantisce.",
    ("title",),
    "Task",
    obbligatorio=True,
)

CAMPI_OPZIONALI: tuple[Campo, ...] = (
    Campo(
        "descrizione",
        "Descrizione",
        "Il dettaglio della task, quando il modello l'ha scritto.",
        ("rich_text",),
        "Descrizione",
    ),
    Campo(
        "assegnatario",
        "Assegnatario",
        "Il nome come è stato detto nella call, non un utente di Notion.",
        ("rich_text", "select", "multi_select"),
        "Assegnatario",
    ),
    Campo(
        "scadenza",
        "Scadenza",
        "La data, quando dalla call si capisce quale sia.",
        ("date",),
        "Scadenza",
    ),
    Campo(
        "priorita",
        "Priorità",
        "Bassa, media, alta o critica.",
        ("select", "status", "rich_text"),
        "Priorità",
    ),
    Campo(
        "stato",
        "Fatto",
        "Segnato quando la task risulta fatta in Scriba.",
        ("checkbox", "select", "status"),
        "Fatto",
    ),
    Campo(
        "prova",
        "Prova",
        "Le frasi della call da cui viene la task, col minuto. È quello che la rende verificabile.",
        ("rich_text",),
        "Prova",
    ),
    Campo(
        "call",
        "Call di provenienza",
        "Il titolo della riunione da cui arriva la task.",
        ("rich_text", "select"),
        "Call",
    ),
    Campo(
        "data_call",
        "Data della call",
        "Quando si è tenuta la riunione.",
        ("date",),
        "Data della call",
    ),
    Campo(
        "link_call",
        "Link alla pagina della call",
        "L'indirizzo della pagina che Scriba crea per la call.",
        ("url", "rich_text"),
        "Link alla call",
        consigliato=False,
    ),
    Campo(
        "confidenza",
        "Confidenza del modello",
        "Quanto il modello era sicuro, da 0 a 1.",
        ("number", "rich_text"),
        "Confidenza",
        consigliato=False,
    ),
    Campo(
        "da_rivedere",
        "Da rivedere",
        "Segnato quando Scriba consiglia di controllare la task a mano.",
        ("checkbox",),
        "Da rivedere",
        consigliato=False,
    ),
)

CAMPI: tuple[Campo, ...] = (CAMPO_TITOLO, *CAMPI_OPZIONALI)

_PER_ID = {c.id: c for c in CAMPI}

# Nomi di colonna che con buona probabilità vogliono quel campo: servono solo a
# presentare all'utente una mappa già compilata, che poi correggerà lui.
_ALIAS: dict[str, set[str]] = {
    "descrizione": {"descrizione", "description", "dettagli", "note", "notes"},
    "assegnatario": {"assegnatario", "assignee", "responsabile", "owner"},
    "scadenza": {"scadenza", "due date", "due", "deadline", "data"},
    "priorita": {"priorità", "priorita", "priority"},
    "stato": {"fatto", "done", "completato", "stato", "status"},
    "prova": {"prova", "prove", "citazione", "evidence", "quote"},
    "call": {"call", "riunione", "meeting", "sessione"},
    "data_call": {"data della call", "data call", "data riunione", "meeting date"},
    "link_call": {"link alla call", "link", "url", "collegamento"},
    "confidenza": {"confidenza", "confidence"},
    "da_rivedere": {"da rivedere", "needs review", "review"},
}

# Come si chiama un valore di dominio dentro Notion. Il primo è la forma
# italiana che creiamo noi, gli altri servono a riconoscere una colonna già
# esistente invece di aggiungerle un'opzione doppia.
_SINONIMI: dict[tuple[str, str], tuple[str, ...]] = {
    ("stato", "done"): ("Fatto", "Done", "Completato", "Completed"),
    ("stato", "altro"): ("Da fare", "To do", "Todo", "Not started"),
    ("priorita", "bassa"): ("Bassa", "Low"),
    ("priorita", "media"): ("Media", "Medium"),
    ("priorita", "alta"): ("Alta", "High"),
    ("priorita", "critica"): ("Critica", "Critical", "Urgent"),
}

_OPZIONI_IN_CREAZIONE: dict[str, tuple[str, ...]] = {
    "priorita": ("Bassa", "Media", "Alta", "Critica"),
}


def campi_disponibili(lingua: str = "it") -> list[dict[str, Any]]:
    """L'elenco per l'interfaccia: è qui la definizione, non lì."""
    return [
        {
            "id": c.id,
            "etichetta": campo_notion(c.id, c.etichetta, c.aiuto, lingua)[0],
            "aiuto": campo_notion(c.id, c.etichetta, c.aiuto, lingua)[1],
            "tipi": list(c.tipi),
            "nome_notion": c.nome_notion,
            "consigliato": c.consigliato,
            "obbligatorio": c.obbligatorio,
        }
        for c in CAMPI
    ]


# --------------------------------------------------------------- configurazione


def _percorso_stato(store: Store) -> Path:
    return Path(store.path).with_name("export_notion.json")


def _config_vuota() -> dict[str, Any]:
    return {"token": "", "database_id": "", "database_titolo": "", "mappa": None, "pagine": {}}


def leggi_config(store: Store) -> dict[str, Any]:
    percorso = _percorso_stato(store)
    if not percorso.exists():
        return _config_vuota()
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Un file rovinato non deve bloccare l'export: si riparte da un
        # collegamento vuoto, come fa Settings con settings.json.
        return _config_vuota()
    for chiave, valore in _config_vuota().items():
        dati.setdefault(chiave, valore)
    return dati


def _salva_config(store: Store, dati: dict[str, Any]) -> None:
    percorso = _percorso_stato(store)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")


def _azzera_riferimenti(store: Store) -> None:
    with store.tx() as conn:
        conn.execute(
            """
            UPDATE tasks
               SET export_status = 'none', export_target = NULL, export_ref = NULL,
                   exported_at = NULL, export_error = NULL
             WHERE export_target = 'notion'
            """
        )


def collega(
    store: Store,
    *,
    token: str = "",
    database_id: str = "",
    database_titolo: str = "",
    mappa: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Salva token, database e mappatura. Un campo vuoto lascia quello già salvato.

    Stesso comportamento di `Settings.aggiorna` per `llm.api_key`: un token
    vuoto arriva dall'interfaccia quando l'utente non lo sta cambiando (non lo
    mostriamo mai), non significa "cancellalo".

    La mappa, se arriva, viene verificata contro lo schema vero del database
    prima di essere salvata: una mappa sbagliata si scopre qui, non a metà di
    un invio.
    """
    dati = leggi_config(store)
    if token:
        dati["token"] = token
    cambia_database = bool(database_id) and database_id != dati["database_id"]
    if database_id:
        dati["database_id"] = database_id
    if database_titolo:
        dati["database_titolo"] = database_titolo
    if cambia_database:
        dati["pagine"] = {}
        dati["mappa"] = None
        dati["database_titolo"] = database_titolo
    if mappa is not None:
        dati["mappa"] = _mappa_verificata(dati["token"], dati["database_id"], mappa)

    _salva_config(store, dati)
    if cambia_database:
        _azzera_riferimenti(store)
    return stato(store)


def scollega(store: Store) -> dict[str, Any]:
    _salva_config(store, _config_vuota())
    return stato(store)


def stato(store: Store) -> dict[str, Any]:
    dati = leggi_config(store)
    return {
        "collegato": bool(dati["token"] and dati["database_id"]),
        "database_id": dati["database_id"] or None,
        "database_titolo": dati["database_titolo"] or None,
        "mappa": dati["mappa"] or {},
    }


def _salva_pagina_call(store: Store, session_id: int, pagina_id: str) -> None:
    dati = leggi_config(store)
    dati.setdefault("pagine", {})[str(session_id)] = pagina_id
    _salva_config(store, dati)


# -------------------------------------------------------------------- chiamate


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _errore(exc: httpx.HTTPError, contesto: str) -> NotionError:
    codice = getattr(getattr(exc, "response", None), "status_code", None)
    if codice == 401:
        return NotionError("Notion ha rifiutato il token: controlla di averlo copiato per intero.")
    if codice in (403, 404):
        return NotionError(
            f"{contesto}: Notion non lo trova, oppure l'integrazione non è stata condivisa con quella pagina."
        )
    return NotionError(f"{contesto}: {exc}")


def _token_o_salvato(store: Store, token: str) -> str:
    token = (token or leggi_config(store)["token"] or "").strip()
    if not token:
        raise NotionError("Manca il token di Notion: collega l'integrazione dalle impostazioni.")
    return token


def _rich_text(testo: str) -> list[dict[str, Any]]:
    # Notion tronca a 2000 caratteri per blocco di rich_text.
    testo = (testo or "")[:2000]
    return [{"type": "text", "text": {"content": testo}}] if testo else []


def _blocco(tipo: str, testo: str) -> dict[str, Any]:
    return {"object": "block", "type": tipo, tipo: {"rich_text": _rich_text(testo)}}


def _blocchi_da_markdown(testo: str | None) -> list[dict[str, Any]]:
    """Conversione minima: titoli e punti diventano i blocchi corrispondenti,
    il resto paragrafi. Non interpreta il grassetto o altra enfasi inline —
    Notion la renderebbe comunque leggibile come testo semplice."""
    if not testo:
        return []
    blocchi: list[dict[str, Any]] = []
    for grezza in testo.splitlines():
        riga = grezza.strip()
        if not riga:
            continue
        if riga.startswith("## "):
            blocchi.append(_blocco("heading_2", riga[3:].strip()))
        elif riga.startswith("# "):
            blocchi.append(_blocco("heading_1", riga[2:].strip()))
        elif riga[:2] in ("- ", "* "):
            blocchi.append(_blocco("bulleted_list_item", riga[2:].strip()))
        else:
            blocchi.append(_blocco("paragraph", riga))
    return blocchi


def _testo_semplice(pezzi: list[dict[str, Any]] | None) -> str:
    if not pezzi:
        return ""
    return "".join(p.get("plain_text") or p.get("text", {}).get("content", "") for p in pezzi).strip()


def _leggi_database(database_id: str, headers: dict[str, str]) -> dict[str, Any]:
    r = httpx.get(f"{API_BASE}/databases/{database_id}", headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _schema_database(database_id: str, headers: dict[str, str]) -> dict[str, Any]:
    return _leggi_database(database_id, headers).get("properties", {})


def _proprieta_titolo(schema: dict[str, Any]) -> str:
    for nome, info in schema.items():
        if info.get("type") == "title":
            return nome
    return "Name"  # fallback se lo schema non si legge: il nome più comune


def _trova_proprieta(
    schema: dict[str, Any], alias: set[str], tipo: str, escluse: set[str] | None = None
) -> str | None:
    for nome, info in schema.items():
        if escluse and nome in escluse:
            continue
        if info.get("type") == tipo and nome.strip().lower() in alias:
            return nome
    return None


def proponi_mappa(schema: dict[str, Any]) -> dict[str, str]:
    """La mappa da mostrare già compilata: le colonne il cui nome e tipo
    corrispondono a un campo noto. Nessuna scelta definitiva, solo un punto di
    partenza — e il ripiego per i collegamenti fatti prima che la mappa
    esistesse."""
    mappa: dict[str, str] = {}
    usate: set[str] = set()
    for campo in CAMPI_OPZIONALI:
        for tipo in campo.tipi:
            nome = _trova_proprieta(schema, _ALIAS[campo.id], tipo, usate)
            if nome:
                mappa[campo.id] = nome
                usate.add(nome)
                break
    return mappa


# ------------------------------------------------------------------- mappatura


def _mappa_verificata(token: str, database_id: str, mappa: dict[str, str]) -> dict[str, str]:
    if not token:
        raise NotionError("Manca il token di Notion: collega l'integrazione dalle impostazioni.")
    if not database_id:
        raise NotionError("Manca l'id del database Notion.")
    try:
        schema = _schema_database(database_id, _headers(token))
    except httpx.HTTPError as exc:
        raise _errore(exc, "Il database indicato") from exc

    pulita: dict[str, str] = {}
    problemi: list[str] = []
    proprietari: dict[str, str] = {}

    for campo_id, nome in mappa.items():
        if campo_id == CAMPO_TITOLO.id:
            continue  # il titolo non si sceglie: va nella proprietà titolo del database.
        campo = _PER_ID.get(campo_id)
        if campo is None:
            problemi.append(f"Il campo «{campo_id}» non esiste.")
            continue
        if not nome:
            continue
        info = schema.get(nome)
        if info is None:
            problemi.append(f"Il database non ha una proprietà «{nome}» ({campo.etichetta}).")
            continue
        tipo = info.get("type")
        if tipo not in campo.tipi:
            problemi.append(
                f"«{nome}» è di tipo {tipo}: {campo.etichetta} può andare solo in "
                f"{', '.join(campo.tipi)}."
            )
            continue
        if nome in proprietari:
            problemi.append(
                f"«{nome}» è già usata da {proprietari[nome]}: due campi nella stessa "
                "proprietà si sovrascriverebbero."
            )
            continue
        proprietari[nome] = campo.etichetta
        pulita[campo_id] = nome

    if problemi:
        raise NotionError(" ".join(problemi))
    return pulita


def elenca_destinazioni(store: Store, token: str = "") -> dict[str, Any]:
    """Database e pagine che l'integrazione può vedere.

    Serve a non far incollare a mano un id: un id sbagliato è indistinguibile
    da un'integrazione non condivisa, e l'utente non ha modo di capire quale
    dei due gli è capitato.
    """
    token = _token_o_salvato(store, token)
    headers = _headers(token)
    try:
        return {
            "database": _cerca(headers, "database"),
            "pagine": _cerca(headers, "page"),
        }
    except httpx.HTTPError as exc:
        raise _errore(exc, "L'elenco da Notion") from exc


def _cerca(headers: dict[str, str], tipo: str) -> list[dict[str, str]]:
    trovati: list[dict[str, str]] = []
    cursore: str | None = None
    for _ in range(_PAGINE_DI_RICERCA):
        corpo: dict[str, Any] = {
            "filter": {"property": "object", "value": tipo},
            "page_size": 100,
        }
        if cursore:
            corpo["start_cursor"] = cursore
        r = httpx.post(f"{API_BASE}/search", headers=headers, json=corpo, timeout=TIMEOUT)
        r.raise_for_status()
        dati = r.json()
        for oggetto in dati.get("results", []):
            if tipo == "page" and oggetto.get("parent", {}).get("type") not in ("workspace", "page_id"):
                # Una riga di database è una pagina per l'API, ma non è un posto
                # dove qualcuno vorrebbe farsi creare un database.
                continue
            trovati.append({"id": oggetto["id"], "titolo": _titolo_oggetto(oggetto) or "Senza titolo"})
        if not dati.get("has_more"):
            break
        cursore = dati.get("next_cursor")
    return trovati


def _titolo_oggetto(oggetto: dict[str, Any]) -> str:
    if oggetto.get("object") == "database":
        return _testo_semplice(oggetto.get("title"))
    for info in oggetto.get("properties", {}).values():
        if info.get("type") == "title":
            return _testo_semplice(info.get("title"))
    return ""


def schema_per_mappatura(store: Store, *, token: str = "", database_id: str = "") -> dict[str, Any]:
    """Le proprietà del database, con la mappa proposta: quanto basta
    all'interfaccia per costruire la schermata di mappatura."""
    token = _token_o_salvato(store, token)
    database_id = (database_id or leggi_config(store)["database_id"] or "").strip()
    if not database_id:
        raise NotionError("Manca l'id del database Notion.")
    try:
        database = _leggi_database(database_id, _headers(token))
    except httpx.HTTPError as exc:
        raise _errore(exc, "Il database indicato") from exc

    schema = database.get("properties", {})
    return {
        "database_id": database_id,
        "titolo": _testo_semplice(database.get("title")) or "Senza titolo",
        "titolo_proprieta": _proprieta_titolo(schema),
        "proprieta": [
            {"nome": nome, "tipo": info.get("type", "")}
            for nome, info in schema.items()
            if info.get("type") != "title"
        ],
        "mappa_proposta": proponi_mappa(schema),
    }


# ------------------------------------------------------------ creazione database


def _proprieta_in_creazione(campo: Campo) -> dict[str, Any]:
    tipo = campo.tipi[0]
    if tipo in ("select", "multi_select"):
        opzioni = [{"name": n} for n in _OPZIONI_IN_CREAZIONE.get(campo.id, ())]
        return {tipo: {"options": opzioni}}
    if tipo == "number":
        return {"number": {"format": "number"}}
    return {tipo: {}}


def crea_database(
    store: Store, *, token: str = "", pagina_id: str, titolo: str, campi: list[str]
) -> dict[str, Any]:
    """Crea in Notion un database con le sole colonne chieste, e lo collega.

    La mappa qui non si indovina: le colonne le abbiamo fatte noi, quindi si sa
    per costruzione quale campo va in quale proprietà.
    """
    token = _token_o_salvato(store, token)
    pagina_id = (pagina_id or "").strip()
    if not pagina_id:
        raise NotionError("Serve la pagina di Notion dentro cui creare il database.")
    titolo = (titolo or "").strip() or "Task da Scriba"

    scelti = [CAMPO_TITOLO, *(c for c in CAMPI_OPZIONALI if c.id in set(campi))]
    proprieta = {c.nome_notion: _proprieta_in_creazione(c) for c in scelti}

    try:
        r = httpx.post(
            f"{API_BASE}/databases",
            headers=_headers(token),
            json={
                "parent": {"type": "page_id", "page_id": pagina_id},
                "title": _rich_text(titolo),
                "properties": proprieta,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise _errore(exc, "La pagina in cui creare il database") from exc

    database_id = r.json()["id"]
    dati = leggi_config(store)
    dati.update(
        {
            "token": token,
            "database_id": database_id,
            "database_titolo": titolo,
            "mappa": {c.id: c.nome_notion for c in scelti if not c.obbligatorio},
            "pagine": {},
        }
    )
    _salva_config(store, dati)
    _azzera_riferimenti(store)
    return stato(store)


# ------------------------------------------------------------------- proprietà


def _svuota_blocchi(page_id: str, headers: dict[str, str]) -> None:
    """Toglie tutti i blocchi figli di una pagina, per poterla riscrivere
    invece di accumulare contenuto a ogni invio."""
    ids: list[str] = []
    cursore: str | None = None
    while True:
        parametri: dict[str, Any] = {"page_size": 100}
        if cursore:
            parametri["start_cursor"] = cursore
        r = httpx.get(
            f"{API_BASE}/blocks/{page_id}/children", headers=headers, params=parametri, timeout=TIMEOUT
        )
        r.raise_for_status()
        corpo = r.json()
        ids.extend(b["id"] for b in corpo.get("results", []))
        if not corpo.get("has_more"):
            break
        cursore = corpo.get("next_cursor")

    for bid in ids:
        httpx.delete(f"{API_BASE}/blocks/{bid}", headers=headers, timeout=TIMEOUT).raise_for_status()


def _aggiungi_blocchi(page_id: str, blocchi: list[dict[str, Any]], headers: dict[str, str]) -> None:
    for i in range(0, len(blocchi), _BLOCCHI_PER_CHIAMATA):
        pezzo = blocchi[i : i + _BLOCCHI_PER_CHIAMATA]
        httpx.patch(
            f"{API_BASE}/blocks/{page_id}/children",
            headers=headers,
            json={"children": pezzo},
            timeout=TIMEOUT,
        ).raise_for_status()


def _sostituisci_contenuto(page_id: str, blocchi: list[dict[str, Any]], headers: dict[str, str]) -> None:
    _svuota_blocchi(page_id, headers)
    _aggiungi_blocchi(page_id, blocchi, headers)


def _sinonimi(campo_id: str, valore: Any) -> tuple[str, ...]:
    chiave = str(valore).strip().lower()
    if campo_id == "stato":
        chiave = "done" if chiave == "done" else "altro"
    return _SINONIMI.get((campo_id, chiave)) or (str(valore),)


def _opzione_esistente(info: dict[str, Any], tipo: str, candidati: tuple[str, ...]) -> str | None:
    esistenti = {
        o.get("name", "").strip().lower(): o.get("name", "")
        for o in info.get(tipo, {}).get("options", [])
    }
    for c in candidati:
        if c.strip().lower() in esistenti:
            return esistenti[c.strip().lower()]
    return None


def _testo_del_campo(campo_id: str, valore: Any) -> str:
    if campo_id == "confidenza" and isinstance(valore, (int, float)):
        return f"{round(float(valore) * 100)}%"
    if campo_id in ("stato", "priorita"):
        return _sinonimi(campo_id, valore)[0]
    return str(valore)


def _valore_proprieta(campo_id: str, info: dict[str, Any], valore: Any) -> dict[str, Any] | None:
    """Il valore nella forma che vuole il tipo della proprietà, o None se non
    c'è niente da mandare."""
    tipo = info.get("type", "")

    if tipo == "checkbox":
        # Una spunta vuota è un'informazione, non un valore mancante: si manda
        # anche quando è falsa.
        acceso = valore == "done" if campo_id == "stato" else bool(valore)
        return {"checkbox": acceso}

    if valore is None or valore == "":
        return None

    if tipo == "title":
        return {"title": _rich_text(str(valore))}
    if tipo == "rich_text":
        return {"rich_text": _rich_text(_testo_del_campo(campo_id, valore))}
    if tipo == "number":
        return {"number": float(valore)} if isinstance(valore, (int, float)) else None
    if tipo == "date":
        return {"date": {"start": str(valore)}}
    if tipo == "url":
        return {"url": str(valore)}
    if tipo in ("select", "multi_select"):
        candidati = _sinonimi(campo_id, valore)
        nome = _opzione_esistente(info, tipo, candidati) or candidati[0][:100]
        return {tipo: {"name": nome}} if tipo == "select" else {tipo: [{"name": nome}]}
    if tipo == "status":
        # Le opzioni di uno `status` non si possono creare dall'API: se nessuna
        # di quelle presenti corrisponde, meglio non mandare niente che far
        # rifiutare tutta la riga.
        nome = _opzione_esistente(info, tipo, _sinonimi(campo_id, valore))
        return {"status": {"name": nome}} if nome else None
    return None


def _proprieta_mappate(
    schema: dict[str, Any], mappa: dict[str, str], valori: dict[str, Any]
) -> dict[str, Any]:
    proprieta: dict[str, Any] = {}
    for campo_id, nome in mappa.items():
        info = schema.get(nome)
        if info is None or campo_id not in valori:
            continue
        valore = _valore_proprieta(campo_id, info, valori[campo_id])
        if valore is not None:
            proprieta[nome] = valore
    return proprieta


def _data_iso(epoch_ms: int | None) -> str | None:
    if not epoch_ms:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000).date().isoformat()


def _testo_prove(t: dict[str, Any]) -> str:
    return " · ".join(f"[{mmss(e['t_ms'])}] «{e['quote']}»" for e in t["evidence"] if e["quote"])


def _proprieta_call(
    schema: dict[str, Any], mappa: dict[str, str], titolo: str, data_call: str | None
) -> dict[str, Any]:
    proprieta: dict[str, Any] = {_proprieta_titolo(schema): {"title": _rich_text(titolo)}}
    # La riga della call vive nello stesso database delle task: la data è la sola
    # cosa che significhi la stessa cosa per entrambe, e senza di lei la pagina
    # sparisce dalle viste ordinate per data.
    solo_data = {k: v for k, v in mappa.items() if k == "data_call"}
    proprieta.update(_proprieta_mappate(schema, solo_data, {"data_call": data_call}))
    return proprieta


def _proprieta_task(
    schema: dict[str, Any], mappa: dict[str, str], t: dict[str, Any], contesto: dict[str, Any]
) -> dict[str, Any]:
    valori = {
        "descrizione": t["descrizione"],
        "assegnatario": t["assignee_text"],
        "scadenza": t["due_date"],
        "priorita": t["priorita"],
        "stato": t["stato"],
        "prova": _testo_prove(t),
        "call": contesto["call"],
        "data_call": contesto["data_call"],
        "link_call": contesto["link_call"],
        "confidenza": t["confidence"],
        "da_rivedere": t["needs_review"],
    }
    proprieta: dict[str, Any] = {_proprieta_titolo(schema): {"title": _rich_text(t["titolo"])}}
    proprieta.update(_proprieta_mappate(schema, mappa, valori))
    return proprieta


# ------------------------------------------------------------------- contenuto


def _blocchi_pagina_call(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sessione = payload["sessione"]
    blocchi: list[dict[str, Any]] = []

    if sessione["piattaforma"]:
        blocchi.append(_blocco("paragraph", sessione["piattaforma"]))

    if payload["riassunto_md"]:
        blocchi.append(_blocco("heading_2", "Riassunto"))
        blocchi.extend(_blocchi_da_markdown(payload["riassunto_md"]))

    if payload["punti_salienti_md"]:
        blocchi.append(_blocco("heading_2", "Punti salienti"))
        blocchi.extend(_blocchi_da_markdown(payload["punti_salienti_md"]))

    confermate = [t for t in payload["task"] if t["stato"] in ("confirmed", "done")]
    if confermate:
        blocchi.append(_blocco("heading_2", "Task"))
        for t in confermate:
            spunta = "✓ " if t["stato"] == "done" else ""
            blocchi.append(_blocco("bulleted_list_item", f"{spunta}{t['titolo']}"))

    return blocchi


def _blocchi_riga_task(t: dict[str, Any]) -> list[dict[str, Any]]:
    blocchi: list[dict[str, Any]] = []
    if t["descrizione"]:
        blocchi.append(_blocco("paragraph", t["descrizione"]))
    # Le prove per campo: è quello che rende la riga verificabile invece che
    # solo un'affermazione arrivata da Scriba.
    for e in t["evidence"]:
        if e["quote"]:
            blocchi.append(_blocco("bulleted_list_item", f"[{mmss(e['t_ms'])}] {e['supports']}: «{e['quote']}»"))
    return blocchi


# ------------------------------------------------------------------------ invio


def _url_pagina(pagina_id: str) -> str:
    return f"https://notion.so/{pagina_id.replace('-', '')}"


def invia(session_id: int, store: Store, config: dict[str, Any]) -> dict[str, Any]:
    """Crea o aggiorna la pagina della call e le righe delle sue task confermate.

    `config` può forzare token/database_id/mappa per questa sola chiamata;
    altrimenti si usa quanto salvato con `collega` o `crea_database`.
    """
    salvato = leggi_config(store)
    token = (config.get("token") or salvato.get("token") or "").strip()
    database_id = (config.get("database_id") or salvato.get("database_id") or "").strip()
    if not token:
        raise NotionError("Manca il token di Notion: collega l'integrazione dalle impostazioni.")
    if not database_id:
        raise NotionError("Manca l'id del database Notion.")

    headers = _headers(token)
    try:
        schema = _schema_database(database_id, headers)
    except httpx.HTTPError as exc:
        raise NotionError(f"Notion non risponde per il database indicato: {exc}") from exc

    mappa = config.get("mappa")
    if mappa is None:
        mappa = salvato.get("mappa")
    if mappa is None:
        # Collegamenti fatti prima che la mappatura esistesse: si continua a
        # riconoscere le colonne dal nome, come faceva questo connettore.
        mappa = proponi_mappa(schema)

    payload = costruisci_payload(store, session_id)
    sessione = payload["sessione"]
    titolo = sessione["titolo"] or f"Call #{session_id}"
    data_call = _data_iso(sessione["started_at"])

    proprieta_call = _proprieta_call(schema, mappa, titolo, data_call)
    blocchi_call = _blocchi_pagina_call(payload)
    pagina_id = salvato.get("pagine", {}).get(str(session_id))

    try:
        if pagina_id:
            # Si aggiorna la pagina già creata: rieseguire l'export non deve
            # produrne una seconda per la stessa call.
            httpx.patch(
                f"{API_BASE}/pages/{pagina_id}",
                headers=headers,
                json={"properties": proprieta_call},
                timeout=TIMEOUT,
            ).raise_for_status()
            _sostituisci_contenuto(pagina_id, blocchi_call, headers)
        else:
            r = httpx.post(
                f"{API_BASE}/pages",
                headers=headers,
                json={
                    "parent": {"database_id": database_id},
                    "properties": proprieta_call,
                    "children": blocchi_call[:_BLOCCHI_PER_CHIAMATA],
                },
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            pagina_id = r.json()["id"]
            if len(blocchi_call) > _BLOCCHI_PER_CHIAMATA:
                _aggiungi_blocchi(pagina_id, blocchi_call[_BLOCCHI_PER_CHIAMATA:], headers)
            _salva_pagina_call(store, session_id, pagina_id)
    except httpx.HTTPError as exc:
        raise NotionError(f"Notion non ha accettato la pagina della call: {exc}") from exc

    contesto = {"call": titolo, "data_call": data_call, "link_call": _url_pagina(pagina_id)}

    creati, aggiornati = 0, 0
    da_mandare = [t for t in payload["task"] if t["stato"] in ("confirmed", "done")]
    for t in da_mandare:
        riga = store.conn.execute(
            "SELECT export_ref, export_status FROM tasks WHERE id = ? AND export_target = 'notion'",
            (t["id"],),
        ).fetchone()
        riga_id = riga["export_ref"] if riga and riga["export_status"] == "synced" else None

        proprieta_task = _proprieta_task(schema, mappa, t, contesto)
        blocchi_task = _blocchi_riga_task(t)
        try:
            if riga_id:
                httpx.patch(
                    f"{API_BASE}/pages/{riga_id}",
                    headers=headers,
                    json={"properties": proprieta_task},
                    timeout=TIMEOUT,
                ).raise_for_status()
                _sostituisci_contenuto(riga_id, blocchi_task, headers)
                aggiornati += 1
            else:
                r = httpx.post(
                    f"{API_BASE}/pages",
                    headers=headers,
                    json={
                        "parent": {"database_id": database_id},
                        "properties": proprieta_task,
                        "children": blocchi_task[:_BLOCCHI_PER_CHIAMATA],
                    },
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                riga_id = r.json()["id"]
                if len(blocchi_task) > _BLOCCHI_PER_CHIAMATA:
                    _aggiungi_blocchi(riga_id, blocchi_task[_BLOCCHI_PER_CHIAMATA:], headers)
                creati += 1
        except httpx.HTTPError as exc:
            with store.tx() as conn:
                conn.execute(
                    "UPDATE tasks SET export_status = 'error', export_target = 'notion', export_error = ? WHERE id = ?",
                    (str(exc), t["id"]),
                )
            # Una riga fallita non deve bloccare le altre: si prosegue.
            continue

        with store.tx() as conn:
            conn.execute(
                """
                UPDATE tasks
                   SET export_status = 'synced', export_target = 'notion',
                       export_ref = ?, exported_at = ?, export_error = NULL
                 WHERE id = ?
                """,
                (riga_id, int(time.time() * 1000), t["id"]),
            )

    return {
        "url": _url_pagina(pagina_id),
        "creati": creati,
        "aggiornati": aggiornati,
    }
