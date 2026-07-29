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
danno vero, non un fastidio: da qui il controllo prima di ogni creazione.

**Credenziali.** Il token non vive in `settings.json` — quel file e la sua
classe `Settings` non sono nel perimetro di questo lavoro, e mescolarci un
formato di credenziali diverso da `llm.api_key` avrebbe significato
cambiarlo. Verso l'interfaccia vale comunque la stessa regola:
si dice *se* il token c'è, mai *quale sia* (vedi `stato()`).

**Schema del database.** Non si assume come sono chiamate le colonne del
database Notion dell'utente: si legge lo schema (`_schema_database`) e si
usa solo la proprietà titolo (garantita per ogni database) più le proprietà
opzionali il cui nome e tipo corrispondono a un alias noto. Una proprietà che
non corrisponde a niente si salta, invece di rischiare un 400 da Notion per
un nome sbagliato.

Non verificato con un vero account Notion (nessuna credenziale disponibile in
questo giro): i test coprono la logica con le chiamate HTTP simulate.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from ..db.store import Store
from ._util import mmss
from .json_export import costruisci_payload

API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Quanti blocchi per chiamata: il limite di Notion è 100, si resta sotto per
# margine invece di inseguirlo esatto.
_BLOCCHI_PER_CHIAMATA = 90


class NotionError(RuntimeError):
    """La chiamata a Notion non è andata a buon fine, o manca la configurazione."""


# --------------------------------------------------------------- configurazione


def _percorso_stato(store: Store) -> Path:
    return Path(store.path).with_name("export_notion.json")


def leggi_config(store: Store) -> dict[str, Any]:
    percorso = _percorso_stato(store)
    if not percorso.exists():
        return {"token": "", "database_id": "", "pagine": {}}
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Un file rovinato non deve bloccare l'export: si riparte da un
        # collegamento vuoto, come fa Settings con settings.json.
        return {"token": "", "database_id": "", "pagine": {}}
    dati.setdefault("token", "")
    dati.setdefault("database_id", "")
    dati.setdefault("pagine", {})
    return dati


def _salva_config(store: Store, dati: dict[str, Any]) -> None:
    percorso = _percorso_stato(store)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")


def collega(store: Store, *, token: str, database_id: str) -> dict[str, Any]:
    """Salva token e database. Un campo vuoto lascia quello già salvato.

    Stesso comportamento di `Settings.aggiorna` per `llm.api_key`: un token
    vuoto arriva dall'interfaccia quando l'utente non lo sta cambiando (non lo
    mostriamo mai), non significa "cancellalo".
    """
    dati = leggi_config(store)
    if token:
        dati["token"] = token
    if database_id:
        dati["database_id"] = database_id
    _salva_config(store, dati)
    return stato(store)


def scollega(store: Store) -> dict[str, Any]:
    _salva_config(store, {"token": "", "database_id": "", "pagine": {}})
    return stato(store)


def stato(store: Store) -> dict[str, Any]:
    dati = leggi_config(store)
    return {
        "collegato": bool(dati["token"] and dati["database_id"]),
        "database_id": dati["database_id"] or None,
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


def _schema_database(database_id: str, headers: dict[str, str]) -> dict[str, Any]:
    r = httpx.get(f"{API_BASE}/databases/{database_id}", headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("properties", {})


def _proprieta_titolo(schema: dict[str, Any]) -> str:
    for nome, info in schema.items():
        if info.get("type") == "title":
            return nome
    return "Name"  # fallback se lo schema non si legge: il nome più comune


def _trova_proprieta(schema: dict[str, Any], alias: set[str], tipo: str) -> str | None:
    for nome, info in schema.items():
        if info.get("type") == tipo and nome.strip().lower() in alias:
            return nome
    return None


def _proprieta_call(schema: dict[str, Any], titolo: str) -> dict[str, Any]:
    return {_proprieta_titolo(schema): {"title": _rich_text(titolo)}}


def _proprieta_task(schema: dict[str, Any], t: dict[str, Any]) -> dict[str, Any]:
    proprieta: dict[str, Any] = {_proprieta_titolo(schema): {"title": _rich_text(t["titolo"])}}

    if t["assignee_text"] and (
        nome := _trova_proprieta(schema, {"assegnatario", "assignee", "responsabile"}, "rich_text")
    ):
        proprieta[nome] = {"rich_text": _rich_text(t["assignee_text"])}

    if t["due_date"] and (
        nome := _trova_proprieta(schema, {"scadenza", "due date", "data", "deadline"}, "date")
    ):
        proprieta[nome] = {"date": {"start": t["due_date"]}}

    if t["priorita"] and (
        nome := _trova_proprieta(schema, {"priorità", "priorita", "priority"}, "select")
    ):
        proprieta[nome] = {"select": {"name": t["priorita"]}}

    if nome := _trova_proprieta(schema, {"fatto", "done", "completato"}, "checkbox"):
        proprieta[nome] = {"checkbox": t["stato"] == "done"}

    return proprieta


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


def invia(session_id: int, store: Store, config: dict[str, Any]) -> dict[str, Any]:
    """Crea o aggiorna la pagina della call e le righe delle sue task confermate.

    `config` può forzare token/database_id per questa sola chiamata;
    altrimenti si usa quanto salvato con `collega`.
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

    payload = costruisci_payload(store, session_id)
    sessione = payload["sessione"]
    titolo = sessione["titolo"] or f"Call #{session_id}"

    proprieta_call = _proprieta_call(schema, titolo)
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

    creati, aggiornati = 0, 0
    da_mandare = [t for t in payload["task"] if t["stato"] in ("confirmed", "done")]
    for t in da_mandare:
        riga = store.conn.execute(
            "SELECT export_ref, export_status FROM tasks WHERE id = ? AND export_target = 'notion'",
            (t["id"],),
        ).fetchone()
        riga_id = riga["export_ref"] if riga and riga["export_status"] == "synced" else None

        proprieta_task = _proprieta_task(schema, t)
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
        "url": f"https://notion.so/{pagina_id.replace('-', '')}",
        "creati": creati,
        "aggiornati": aggiornati,
    }
