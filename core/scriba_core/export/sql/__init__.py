"""Sincronizza le call su un database SQL remoto.

Lo scopo non è esportare, è **tenere**: i dati di Scriba vivono in uno SQLite
su un computer solo, e quel computer si rompe. Da qui la forma di tutto quello
che c'è qui dentro — si riesegue quante volte si vuole e il risultato è lo
stesso, perché ogni riga si riconosce dalla sua chiave naturale invece che
dall'ordine in cui è stata scritta.

**Due strade, non una.** Chi parte da zero si fa creare le tabelle (`crea`), e
allora nomi e tipi sono giusti per costruzione. Chi ha già il suo schema mappa
i campi di Scriba sulle colonne che ha (`mappa`), e a quel punto è lui a dire
cosa va dove. Sotto sono la stessa cosa: in entrambi i casi la configurazione
finisce per dire, tabella per tabella, «questo campo va in questa colonna».
`invia` non sa quale delle due strade è stata presa, e non deve saperlo.

**Il segreto.** L'URL contiene la password, quindi non vive in chiaro (vedi
`segreti.py`) e non torna mai verso l'interfaccia: si dice *che* c'è un
collegamento, e verso quale server, mai con quale password.

**Il dialetto.** Tutto quello che è specifico di PostgreSQL sta in
`postgres.py`. Questo file parla solo di tabelle, campi e righe: è la ragione
per cui aggiungere MySQL sarà scrivere un file, non riscrivere questo.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ...db.store import Store
from ...i18n import colonna_sql
from . import modello, postgres, segreti
from .modello import Tabella
from .postgres import ErroreSql

log = logging.getLogger(__name__)

#: L'unico dialetto per ora. Quando ce ne saranno due, questa diventa una
#: scelta salvata nella configurazione — non un `if` sparso nel file.
DIALETTO = postgres

PREFISSO_PREDEFINITO = "scriba_"


# --------------------------------------------------------------- configurazione


def _percorso(store: Store) -> Path:
    return Path(store.path).with_name("database_remoto.json")


def _vuota() -> dict[str, Any]:
    return {
        "url": "",
        "modalita": "diretta",
        "schema": "",
        "prefisso": PREFISSO_PREDEFINITO,
        # chiave tabella -> {"nome": str, "colonne": {campo: colonna}}
        "tabelle": {},
        # Sincronizza da solo a fine analisi. Spento finché non si collega.
        "automatico": True,
    }


def leggi_config(store: Store) -> dict[str, Any]:
    percorso = _percorso(store)
    if not percorso.exists():
        return _vuota()
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Come fa Settings con settings.json: un file rovinato non deve
        # impedire di usare l'applicazione, si riparte da «non collegato».
        return _vuota()
    for chiave, valore in _vuota().items():
        dati.setdefault(chiave, valore)
    return dati


def _salva_config(store: Store, dati: dict[str, Any]) -> None:
    percorso = _percorso(store)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")


def _url(dati: dict[str, Any]) -> str:
    return segreti.decifra(dati.get("url") or "")


def stato(store: Store) -> dict[str, Any]:
    """Cosa mostrare nelle impostazioni. Senza password, mai."""
    dati = leggi_config(store)
    url = _url(dati)
    fuori: dict[str, Any] = {
        "collegato": bool(url and dati.get("schema") and dati.get("tabelle")),
        "modalita": dati.get("modalita"),
        "schema": dati.get("schema"),
        "prefisso": dati.get("prefisso"),
        "automatico": bool(dati.get("automatico")),
        "tabelle": {
            k: {"nome": v.get("nome"), "campi": sorted((v.get("colonne") or {}).keys())}
            for k, v in (dati.get("tabelle") or {}).items()
        },
        "segreto_in_chiaro": segreti.in_chiaro(dati.get("url") or ""),
    }
    if url:
        try:
            fuori["server"] = DIALETTO.analizza_url(url)
        except ErroreSql:
            # Salvato da una versione precedente, o illeggibile su questo
            # account: si dice che non è utilizzabile invece di fingere.
            fuori["collegato"] = False
            fuori["server"] = None
    else:
        fuori["server"] = None
    return fuori


def scollega(store: Store) -> dict[str, Any]:
    """Dimentica il collegamento. Non tocca niente sul database remoto.

    Cancellare là fuori sarebbe una decisione che non spetta a questo comando:
    l'utente ha chiesto di scollegare, non di buttare via i suoi dati.
    """
    _salva_config(store, _vuota())
    return stato(store)


# ------------------------------------------------------------------ connessione


def _connessione(store: Store, url: str = "", modalita: str = ""):
    dati = leggi_config(store)
    url = (url or _url(dati)).strip()
    if not url:
        raise ErroreSql("Nessun database remoto collegato.")
    return DIALETTO.connetti(url, modalita=modalita or dati.get("modalita") or "diretta")


def prova(store: Store, *, url: str = "", modalita: str = "") -> dict[str, Any]:
    """Si collega davvero e riferisce cosa ha trovato.

    Prima di salvare qualunque cosa: un collegamento che non si è mai provato è
    un collegamento che non funziona, e lo si scopre a fine call.
    """
    dati = leggi_config(store)
    url = (url or _url(dati)).strip()
    modalita = modalita or DIALETTO.deduci_modalita(
        DIALETTO.analizza_url(url)["host"], DIALETTO.analizza_url(url)["porta"]
    )
    conn = DIALETTO.connetti(url, modalita=modalita)
    try:
        return {
            "ok": True,
            "versione": DIALETTO.versione(conn),
            "schemi": DIALETTO.elenca_schemi(conn),
            "modalita": modalita,
            "server": DIALETTO.analizza_url(url),
        }
    finally:
        conn.close()


def tabelle_esistenti(store: Store, *, url: str = "", modalita: str = "", schema: str) -> list[str]:
    conn = _connessione(store, url, modalita)
    try:
        return DIALETTO.elenca_tabelle(conn, schema)
    finally:
        conn.close()


def colonne_di(
    store: Store, *, url: str = "", modalita: str = "", schema: str, tabella: str, per: str
) -> dict[str, Any]:
    """Le colonne di una tabella esistente, dette in termini di campi di Scriba.

    Per ogni campo si elencano **solo** le colonne che possono davvero
    riceverlo: proporre un `text` per una scadenza significa lasciar scegliere
    un errore che si vedrà solo al primo invio.
    """
    t = modello.tabella(per)
    if t is None:
        raise ErroreSql(f"Tabella sconosciuta: {per}")

    conn = _connessione(store, url, modalita)
    try:
        colonne = DIALETTO.colonne(conn, schema, tabella)
    finally:
        conn.close()

    return {
        "colonne": colonne,
        "campi": [
            {
                "chiave": c.chiave,
                "etichetta": colonna_sql(t.chiave, c.chiave, c.etichetta, c.descrizione, lingua)[0],
                "tipo": c.tipo,
                "descrizione": colonna_sql(t.chiave, c.chiave, c.etichetta, c.descrizione, lingua)[1],
                "chiave_naturale": c.chiave_naturale,
                "ammesse": [x["nome"] for x in colonne if DIALETTO.accetta(c.tipo, x["tipo"])],
            }
            for c in t.campi
        ],
    }


# --------------------------------------------------------------------- creazione


def _nome_tabella(prefisso: str, chiave: str) -> str:
    return f"{prefisso or ''}{chiave}"


def anteprima_ddl(*, schema: str, prefisso: str, tabelle: list[str]) -> list[dict[str, str]]:
    """Il DDL che verrebbe eseguito, per mostrarlo prima di eseguirlo.

    Non è cortesia: sta per scrivere nel database di qualcuno, e leggerlo prima
    è l'unico modo per sapere cosa sta per succedere.
    """
    fuori = [{"tabella": "(schema)", "sql": DIALETTO.ddl_schema(schema)}]
    for chiave in tabelle:
        t = modello.tabella(chiave)
        if t is None:
            continue
        nome = _nome_tabella(prefisso, chiave)
        fuori.append(
            {
                "tabella": nome,
                "sql": DIALETTO.ddl_tabella(schema, nome, list(t.campi), t.chiave_naturale),
            }
        )
    return fuori


def crea(
    store: Store,
    *,
    url: str = "",
    modalita: str = "",
    schema: str,
    prefisso: str = PREFISSO_PREDEFINITO,
    tabelle: list[str],
) -> dict[str, Any]:
    """Crea le tabelle scelte e salva il collegamento.

    `CREATE ... IF NOT EXISTS`, mai un `DROP`: su un database che è di qualcun
    altro si aggiunge, non si sistema d'ufficio.
    """
    if not tabelle:
        raise ErroreSql("Non è stata scelta nessuna tabella da creare.")

    conn = _connessione(store, url, modalita)
    try:
        with conn.cursor() as cur:
            for pezzo in anteprima_ddl(schema=schema, prefisso=prefisso, tabelle=tabelle):
                cur.execute(pezzo["sql"])
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise ErroreSql(DIALETTO.spiega(exc, url=url, modalita=modalita)) from exc
    finally:
        conn.close()

    mappa = {}
    for chiave in tabelle:
        t = modello.tabella(chiave)
        if t is None:
            continue
        # Create dal connettore: la corrispondenza campo -> colonna è
        # l'identità, e lo è per costruzione.
        mappa[chiave] = {
            "nome": _nome_tabella(prefisso, chiave),
            "colonne": {c.chiave: c.chiave for c in t.campi},
        }

    return collega(store, url=url, modalita=modalita, schema=schema, prefisso=prefisso, tabelle=mappa)


def collega(
    store: Store,
    *,
    url: str = "",
    modalita: str = "",
    schema: str = "",
    prefisso: str = "",
    tabelle: dict[str, Any] | None = None,
    automatico: bool | None = None,
) -> dict[str, Any]:
    """Salva il collegamento. Un campo vuoto lascia quello già salvato.

    Stesso comportamento del token di Notion e di `llm.api_key`: l'interfaccia
    non rimanda mai indietro il segreto che non le abbiamo mai mostrato, quindi
    un URL vuoto vuol dire «non lo sto cambiando», non «cancellalo».
    """
    dati = leggi_config(store)
    if url.strip():
        nuovo = url.strip()
        # Cambiare server significa che gli id remoti di prima non valgono più:
        # si riparte da zero invece di riportare «aggiornate» righe che stanno
        # in un altro database.
        if nuovo != _url(dati):
            _dimentica_sincronizzazioni(store)
        dati["url"] = segreti.cifra(nuovo)
    if modalita:
        if modalita not in DIALETTO.MODALITA:
            raise ErroreSql(f"Modalità di connessione sconosciuta: {modalita}")
        dati["modalita"] = modalita
    if schema:
        dati["schema"] = schema
    if prefisso:
        dati["prefisso"] = prefisso
    if tabelle is not None:
        _verifica_mappa(tabelle)
        dati["tabelle"] = tabelle
    if automatico is not None:
        dati["automatico"] = bool(automatico)

    _salva_config(store, dati)
    return stato(store)


def _verifica_mappa(tabelle: dict[str, Any]) -> None:
    """Rifiuta una mappatura che non potrebbe funzionare, adesso e non al primo invio."""
    for chiave, voce in tabelle.items():
        t = modello.tabella(chiave)
        if t is None:
            raise ErroreSql(f"Tabella sconosciuta: {chiave}")
        if not (voce.get("nome") or "").strip():
            raise ErroreSql(f"Manca il nome della tabella remota per «{t.etichetta}».")
        colonne = voce.get("colonne") or {}
        for campo in colonne:
            if t.campo(campo) is None:
                raise ErroreSql(f"«{t.etichetta}» non ha un campo che si chiama {campo}.")
        # Senza la chiave naturale non si riconosce una riga già scritta, e
        # ogni sincronizzazione aggiungerebbe doppioni per sempre.
        mancanti = [k for k in t.chiave_naturale if k not in colonne]
        if mancanti:
            etichette = ", ".join(t.campo(m).etichetta for m in mancanti if t.campo(m))
            raise ErroreSql(
                f"«{t.etichetta}»: senza {etichette} non si riconoscono le righe già inviate, "
                "e ogni sincronizzazione ne aggiungerebbe di nuove."
            )


def _dimentica_sincronizzazioni(store: Store) -> None:
    with store.tx() as conn:
        conn.execute("DELETE FROM sync_remoto")


# ------------------------------------------------------------------------ invio


def _valore(campo, grezzo: Any) -> Any:
    """Adatta un valore del modello al tipo della colonna."""
    if grezzo is None:
        return None
    if campo.tipo == "istante":
        # Epoch in millisecondi -> datetime con fuso. Si converte qui e non
        # nell'estrazione perché è qui che si sa che colonna lo riceve.
        from datetime import datetime, timezone

        return datetime.fromtimestamp(int(grezzo) / 1000, tz=timezone.utc)
    if campo.tipo == "booleano":
        return bool(grezzo)
    return grezzo


def invia(session_id: int, store: Store, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Manda una call al database remoto. Rieseguibile quante volte si vuole.

    Tutto in una transazione: o la call c'è per intero, o non c'è. Una call
    scritta a metà — la riunione sì, le sue task no — è peggio di una assente,
    perché sembra completa.
    """
    dati = leggi_config(store)
    schema = dati.get("schema") or ""
    tabelle = dati.get("tabelle") or {}
    if not schema or not tabelle:
        raise ErroreSql("Nessun database remoto collegato.")

    conn = _connessione(store)
    scritte = 0
    try:
        with conn.cursor() as cur:
            for chiave, voce in tabelle.items():
                t = modello.tabella(chiave)
                if t is None:
                    continue
                colonne = voce.get("colonne") or {}
                campi = [c for c in t.campi if c.chiave in colonne]
                if not campi:
                    continue

                sql = DIALETTO.upsert(
                    schema,
                    voce["nome"],
                    [colonne[c.chiave] for c in campi],
                    tuple(colonne[k] for k in t.chiave_naturale),
                )
                righe = modello.righe(store, session_id, chiave)
                for riga in righe:
                    cur.execute(sql, [_valore(c, riga.get(c.chiave)) for c in campi])
                scritte += len(righe)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        messaggio = DIALETTO.spiega(exc, url=_url(dati), modalita=dati.get("modalita") or "diretta")
        _annota(store, session_id, "errore", messaggio, 0)
        raise ErroreSql(messaggio) from exc
    finally:
        conn.close()

    _annota(store, session_id, "ok", None, scritte)
    return {"ok": True, "righe": scritte, "tabelle": sorted(tabelle)}


def _annota(store: Store, session_id: int, esito: str, errore: str | None, righe: int) -> None:
    with store.tx() as conn:
        conn.execute(
            """
            INSERT INTO sync_remoto (session_id, at, esito, errore, righe)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE
               SET at = excluded.at, esito = excluded.esito,
                   errore = excluded.errore, righe = excluded.righe
            """,
            (session_id, int(time.time() * 1000), esito, errore, righe),
        )


def da_sincronizzare(store: Store) -> list[int]:
    """Le call mai sincronizzate, o la cui ultima sincronizzazione è fallita."""
    return [
        r["id"]
        for r in store.conn.execute(
            """
            SELECT s.id
              FROM sessions s
              LEFT JOIN sync_remoto r ON r.session_id = s.id
             WHERE s.stato <> 'recording' AND (r.session_id IS NULL OR r.esito <> 'ok')
             ORDER BY s.started_at
            """
        )
    ]


def sincronizza_tutto(store: Store) -> dict[str, Any]:
    """Manda tutto il pregresso, senza fermarsi al primo intoppo.

    Una call che non passa non deve impedire alle altre di passare: si contano
    gli esiti e si riferiscono, invece di lasciare il lavoro a metà senza dire
    dove si è fermato.
    """
    fatte, fallite, righe = 0, 0, 0
    primo_errore: str | None = None
    for session_id in da_sincronizzare(store):
        try:
            esito = invia(session_id, store)
        except ErroreSql as exc:
            fallite += 1
            if primo_errore is None:
                primo_errore = str(exc)
        else:
            fatte += 1
            righe += esito["righe"]
    return {"sincronizzate": fatte, "fallite": fallite, "righe": righe, "errore": primo_errore}
