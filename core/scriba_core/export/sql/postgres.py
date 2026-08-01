"""Il dialetto PostgreSQL.

È il primo di quelli che ci saranno: la superficie che il connettore usa sta
tutta qui sotto in una manciata di funzioni — collegarsi, citare un
identificatore, tradurre un tipo, scrivere il DDL, scrivere l'upsert, elencare
schemi e colonne. Aggiungere MySQL vuol dire scrivere un altro file con queste
stesse funzioni, non toccare il connettore.

Due cose, in questo file, sono la differenza fra funzionare e non funzionare, e
nessuna delle due è ovvia leggendo la documentazione del driver.

**Il pooler in modalità transazione non regge gli statement preparati.**
psycopg li usa da solo dopo qualche esecuzione della stessa query. Il pooler
sposta la connessione fisica sotto ai piedi fra una e l'altra, lo statement
preparato non c'è più, e arriva `prepared statement "_pg3_0" already exists` —
un messaggio che non aiuta nessuno. Si spengono, e si spengono **da soli**
riconoscendo la porta o l'host: chiedere all'utente di sapere questa cosa
sarebbe chiedergli di conoscere un difetto di due librerie messe insieme.

**La connessione diretta a Supabase risponde spesso solo in IPv6.** Su una rete
senza IPv6 non si collega, e l'errore che esce parla di timeout — che manda a
cercare nel posto sbagliato. Qui si riconosce il caso e si dice cosa sta
succedendo davvero.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlparse, urlunparse

from .modello import Campo

NOME = "postgres"

#: Come si scrive ogni tipo del modello in PostgreSQL.
#:
#: `timestamptz` e non `timestamp`: un istante senza fuso è un istante di cui
#: non si sa niente, e le call di una persona che viaggia lo dimostrano subito.
#: `text` ovunque invece di `varchar(n)`: in PostgreSQL non costa niente di più
#: e toglie l'unico modo in cui questo export può troncare quello che scrive.
TIPI_SQL = {
    "testo": "text",
    "testo_lungo": "text",
    "intero": "bigint",
    "decimale": "double precision",
    "booleano": "boolean",
    "istante": "timestamptz",
    "data": "date",
}

#: I tipi PostgreSQL che accettano ciascun tipo del modello, per la mappatura su
#: tabelle già esistenti. Volutamente permissivo su `testo`: qualunque cosa si
#: può scrivere in una colonna di testo, ed è l'utente a decidere se ha senso.
COMPATIBILI = {
    "testo": ("text", "character varying", "character", "citext", "uuid", "name"),
    "testo_lungo": ("text", "character varying", "character"),
    "intero": ("bigint", "integer", "smallint", "numeric"),
    "decimale": ("double precision", "real", "numeric"),
    "booleano": ("boolean",),
    "istante": ("timestamp with time zone", "timestamp without time zone"),
    "data": ("date", "timestamp with time zone", "timestamp without time zone"),
}

MODALITA = ("diretta", "pooling_transazione", "pooling_sessione")

#: Un identificatore che non ha bisogno di essere citato. Tutto il resto passa
#: comunque da `cita`, che non si fida di questa lista.
_SEMPLICE = re.compile(r"^[a-z_][a-z0-9_]*$")


class ErroreSql(Exception):
    """Un guasto che vale la pena mostrare così com'è all'utente."""


# --------------------------------------------------------------------- URL


def analizza_url(url: str) -> dict[str, Any]:
    """Scompone l'URL in quello che serve mostrare e decidere.

    La password non esce da qui: verso l'interfaccia si dice *che* c'è, mai
    quale sia — stessa regola del token di Notion.
    """
    url = (url or "").strip()
    if not url:
        raise ErroreSql("Manca l'indirizzo del database.")

    pezzi = urlparse(url)
    if pezzi.scheme not in ("postgres", "postgresql"):
        raise ErroreSql(
            "L'indirizzo deve cominciare con postgresql:// (o postgres://). "
            f"Questo comincia con «{pezzi.scheme or '?'}»."
        )
    if not pezzi.hostname:
        raise ErroreSql("Nell'indirizzo manca il nome del server.")

    parametri = dict(parse_qsl(pezzi.query))
    porta = pezzi.port or 5432
    return {
        "host": pezzi.hostname,
        "porta": porta,
        "database": (pezzi.path or "/").lstrip("/") or "postgres",
        "utente": pezzi.username or "",
        "password_presente": bool(pezzi.password),
        "sslmode": parametri.get("sslmode"),
        "modalita_dedotta": deduci_modalita(pezzi.hostname, porta),
    }


def deduci_modalita(host: str, porta: int) -> str:
    """Indovina come ci si sta collegando, per proporlo già giusto.

    Resta una proposta: l'utente può contraddirla. Ma indovinarla bene evita
    l'unico errore che nessuno saprebbe diagnosticare da solo.
    """
    host = (host or "").lower()
    if porta == 6543:
        return "pooling_transazione"
    if "pooler." in host:
        # Stesso host, porta 5432: è il pooler in modalità sessione, che invece
        # gli statement preparati li regge.
        return "pooling_sessione"
    return "diretta"


def prepara_url(url: str, *, modalita: str) -> tuple[str, dict[str, Any]]:
    """L'URL da passare al driver, più le opzioni di connessione.

    Aggiunge `sslmode=require` se manca e il server non è locale: verso un
    database remoto una connessione in chiaro non è un'opzione, e nessuno se ne
    accorgerebbe finché non è tardi. Se l'utente ne ha messo uno suo, si lascia
    il suo — anche se è più debole: è una sua scelta esplicita.
    """
    pezzi = urlparse(url.strip())
    parametri = dict(parse_qsl(pezzi.query))
    locale = (pezzi.hostname or "") in ("localhost", "127.0.0.1", "::1")
    if "sslmode" not in parametri and not locale:
        parametri["sslmode"] = "require"

    query = "&".join(f"{k}={v}" for k, v in parametri.items())
    completo = urlunparse(pezzi._replace(query=query))

    opzioni: dict[str, Any] = {}
    if modalita == "pooling_transazione":
        # Vedi la spiegazione in cima al file: senza questo, la seconda
        # sincronizzazione fallisce con un messaggio incomprensibile.
        opzioni["prepare_threshold"] = None
    return completo, opzioni


# ------------------------------------------------------------- connessione


def connetti(url: str, *, modalita: str = "diretta", timeout_s: float = 10.0):
    import psycopg

    completo, opzioni = prepara_url(url, modalita=modalita)
    try:
        return psycopg.connect(completo, connect_timeout=int(timeout_s), autocommit=False, **opzioni)
    except Exception as exc:  # psycopg.OperationalError e parenti
        raise ErroreSql(spiega(exc, url=url, modalita=modalita)) from exc


def spiega(exc: Exception, *, url: str, modalita: str) -> str:
    """Traduce l'errore del driver in qualcosa su cui si può agire.

    Un «connection timed out» manda a controllare la rete, la password, il
    firewall — cioè ovunque tranne dove sta il problema. Le tre cause vere
    hanno tre rimedi diversi, e vanno nominate.
    """
    testo = str(exc).strip()
    basso = testo.lower()

    try:
        host = urlparse(url.strip()).hostname or ""
    except Exception:
        host = ""

    if "prepared statement" in basso and "already exists" in basso:
        return (
            "Il server ha rifiutato uno statement preparato: succede con il pooler in "
            "modalità transazione. Imposta la modalità «pooling (transazione)» e riprova. "
            f"({testo})"
        )
    if "password authentication failed" in basso or "authentication" in basso:
        return f"Utente o password non accettati dal server. ({testo})"
    if "does not exist" in basso and "database" in basso:
        return f"Il database indicato nell'indirizzo non esiste su quel server. ({testo})"
    # «timed out» e «timeout» sono due stringhe diverse, e libpq usa la prima:
    # cercare solo la seconda faceva cadere questo caso nel messaggio generico,
    # cioè proprio quello che questa funzione esiste per evitare.
    if any(
        s in basso
        for s in ("timed out", "timeout", "could not connect", "unreachable", "no route to host")
    ):
        if "supabase.co" in host and modalita == "diretta":
            return (
                "Il server non risponde. Sulla connessione diretta di Supabase questo di solito "
                "significa una cosa sola: quell'indirizzo risponde solo in IPv6, e questa rete non "
                "ce l'ha. Usa l'indirizzo del pooler (porta 6543), oppure attiva l'add-on IPv4. "
                f"({testo})"
            )
        return (
            "Il server non risponde entro il tempo previsto: controlla l'indirizzo, la porta e "
            f"che il tuo IP sia ammesso. ({testo})"
        )
    if "ssl" in basso:
        return f"Collegamento cifrato rifiutato dal server. ({testo})"
    return testo


# ------------------------------------------------------------------- SQL


def cita(identificatore: str) -> str:
    """Un nome di tabella o colonna, al riparo da tutto.

    Si cita sempre, anche quando non servirebbe: un nome che arriva
    dall'utente non è mai «sicuramente semplice», e la differenza fra citare e
    non citare qui è la differenza fra un'iniezione SQL e nessuna. Il doppio
    apice interno si raddoppia, che è come PostgreSQL lo vuole.
    """
    if identificatore is None or identificatore == "":
        raise ErroreSql("Nome di tabella o colonna vuoto.")
    if "\x00" in identificatore:
        raise ErroreSql("Nome di tabella o colonna non valido.")
    return '"' + identificatore.replace('"', '""') + '"'


def tipo_sql(campo: Campo) -> str:
    return TIPI_SQL[campo.tipo]


def ddl_schema(schema: str) -> str:
    return f"CREATE SCHEMA IF NOT EXISTS {cita(schema)}"


def ddl_tabella(schema: str, nome: str, campi: list[Campo], chiave: tuple[str, ...]) -> str:
    """Il DDL di una tabella, da mostrare all'utente prima di eseguirlo.

    `IF NOT EXISTS` e nessun `DROP`: su un database di qualcun altro il
    connettore aggiunge, non toglie. Se una tabella con quel nome c'è già e non
    ha la forma giusta, il rimedio è dirlo, non sistemarla d'ufficio.
    """
    colonne = [f"  {cita(c.chiave)} {tipo_sql(c)}" for c in campi]
    # Aggiunta da noi, non nel modello: è di questa tabella remota, non di
    # Scriba, e serve a chi guarda il database per sapere quando è arrivata
    # l'ultima volta.
    colonne.append('  "sincronizzato_at" timestamptz NOT NULL DEFAULT now()')
    if chiave:
        colonne.append(f"  PRIMARY KEY ({', '.join(cita(k) for k in chiave)})")
    corpo = ",\n".join(colonne)
    return f"CREATE TABLE IF NOT EXISTS {cita(schema)}.{cita(nome)} (\n{corpo}\n)"


def upsert(schema: str, nome: str, colonne: list[str], chiave: tuple[str, ...]) -> str:
    """`INSERT ... ON CONFLICT DO UPDATE`: risincronizzare aggiorna, non duplica.

    Senza chiave naturale non si può riconoscere una riga già scritta, e si
    rifiuta invece di inserire per sempre doppioni silenziosi.
    """
    if not chiave:
        raise ErroreSql(f"La tabella «{nome}» non ha una chiave su cui riconoscere le righe già scritte.")

    citate = [cita(c) for c in colonne]
    segnaposti = ", ".join(["%s"] * len(colonne))
    aggiornabili = [c for c in colonne if c not in chiave]
    set_ = ", ".join(f"{cita(c)} = EXCLUDED.{cita(c)}" for c in aggiornabili)
    set_ = f"{set_}, " if set_ else ""
    return (
        f"INSERT INTO {cita(schema)}.{cita(nome)} ({', '.join(citate)}) VALUES ({segnaposti}) "
        f"ON CONFLICT ({', '.join(cita(k) for k in chiave)}) DO UPDATE SET "
        f'{set_}"sincronizzato_at" = now()'
    )


# ------------------------------------------------------------- ispezione


def elenca_schemi(conn) -> list[str]:
    """Gli schemi in cui si può davvero scrivere.

    Non tutti quelli che esistono: quelli di sistema non sono una scelta
    sensata e mostrarli sarebbe solo un modo di sbagliare.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT nspname FROM pg_namespace
             WHERE nspname NOT LIKE 'pg\\_%' AND nspname <> 'information_schema'
             ORDER BY nspname
            """
        )
        return [r[0] for r in cur.fetchall()]


def elenca_tabelle(conn, schema: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
             WHERE table_schema = %s AND table_type = 'BASE TABLE'
             ORDER BY table_name
            """,
            (schema,),
        )
        return [r[0] for r in cur.fetchall()]


def colonne(conn, schema: str, tabella: str) -> list[dict[str, Any]]:
    """Le colonne di una tabella esistente, per la mappatura."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable
              FROM information_schema.columns
             WHERE table_schema = %s AND table_name = %s
             ORDER BY ordinal_position
            """,
            (schema, tabella),
        )
        return [
            {"nome": r[0], "tipo": r[1], "obbligatoria": r[2] == "NO"} for r in cur.fetchall()
        ]


def accetta(tipo_modello: str, tipo_colonna: str) -> bool:
    """Un campo di Scriba può finire in questa colonna?"""
    return tipo_colonna.lower() in COMPATIBILI.get(tipo_modello, ())


def versione(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        riga = cur.fetchone()
    return riga[0] if riga else "sconosciuta"
