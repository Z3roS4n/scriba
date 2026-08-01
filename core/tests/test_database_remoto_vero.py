"""Prova il database remoto contro un PostgreSQL **vero**.

`test_database_remoto.py` verifica il ragionamento; qui si verifica che il
ragionamento regga contro un server. È la differenza fra «i test passano» e «ha
funzionato»: l'export verso Notion, in questo stesso progetto, è coperto da
test con le chiamate simulate e non ha mai visto un account reale — ed è
scritto nei limiti noti del README proprio perché non è la stessa cosa.

Come si accende, in ordine di preferenza:

1. `SCRIBA_PG_URL` nell'ambiente: si usa quel server. È la strada per provare
   contro un Supabase vero, o contro il pooler, che sono i casi che contano di
   più e che un container locale non riproduce.
2. Docker in esecuzione: si avvia un `postgres:17-alpine` usa-e-getta, si fa
   tutto lì dentro e si butta via alla fine.
3. Né l'uno né l'altro: i test si saltano, dicendo perché.

Quello che si verifica qui non si può verificare altrove: che il DDL generato
sia accettato davvero, che l'upsert aggiorni invece di duplicare quando si
rimanda la stessa call, che i tipi reggano, e che una mappatura su una tabella
preesistente scriva nelle colonne giuste.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.db.store import Store  # noqa: E402
from scriba_core.export import sql  # noqa: E402
from scriba_core.export.sql import postgres  # noqa: E402

CONTENITORE = "scriba-prova-postgres"
PASSWORD = "prova"
PORTA = 55432


def _docker_c_e() -> bool:
    try:
        esito = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=20,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return esito.returncode == 0


def _avvia_contenitore() -> str:
    subprocess.run(["docker", "rm", "-f", CONTENITORE], capture_output=True, timeout=60)
    subprocess.run(
        [
            "docker", "run", "-d", "--name", CONTENITORE,
            "-e", f"POSTGRES_PASSWORD={PASSWORD}",
            "-e", "POSTGRES_DB=scriba",
            "-p", f"{PORTA}:5432",
            "postgres:17-alpine",
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    url = f"postgresql://postgres:{PASSWORD}@localhost:{PORTA}/scriba"
    # Il container risponde alla porta prima di essere pronto a servire: si
    # aspetta una connessione riuscita, non l'apertura della porta.
    scadenza = time.monotonic() + 90
    while time.monotonic() < scadenza:
        try:
            postgres.connetti(url, timeout_s=3).close()
            return url
        except Exception:
            time.sleep(1.0)
    raise RuntimeError("Il PostgreSQL di prova non è diventato pronto in 90 secondi.")


@pytest.fixture(scope="module")
def url_server() -> str:
    dall_ambiente = os.environ.get("SCRIBA_PG_URL", "").strip()
    if dall_ambiente:
        return dall_ambiente
    if not _docker_c_e():
        pytest.skip(
            "Nessun PostgreSQL per la prova: imposta SCRIBA_PG_URL, oppure avvia Docker "
            "(questi test ne creano uno usa-e-getta da soli)."
        )
    url = _avvia_contenitore()
    yield url
    subprocess.run(["docker", "rm", "-f", CONTENITORE], capture_output=True, timeout=60)


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "scriba.sqlite")


@pytest.fixture()
def schema_pulito(url_server: str) -> str:
    """Uno schema vuoto per ogni test: i test non devono vedersi a vicenda."""
    nome = f"prova_{int(time.time() * 1000) % 100000}"
    conn = postgres.connetti(url_server)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {postgres.cita(nome)} CASCADE")
            cur.execute(f"CREATE SCHEMA {postgres.cita(nome)}")
        conn.commit()
    finally:
        conn.close()
    yield nome
    conn = postgres.connetti(url_server)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {postgres.cita(nome)} CASCADE")
        conn.commit()
    finally:
        conn.close()


def _call(store: Store, titolo: str = "Allineamento") -> int:
    cid = store.crea_cliente("Acme")
    sid = store.create_session(1_785_000_000_000, titolo=titolo, piattaforma="zoom")
    store.assegna_cliente(sid, cid)
    store.end_session(sid, 1_785_003_600_000)
    store.add_segment(sid, "loopback", 0, 4_000, "parliamo del budget", is_final=True)
    store.add_segment(sid, "mic", 4_000, 8_000, "d'accordo, mando il preventivo", is_final=True)
    store.add_task(sid, "Mandare il preventivo", assignee_text="Marco", due_date="2026-09-01")
    return sid


def _conta(url: str, schema: str, tabella: str) -> int:
    conn = postgres.connetti(url)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {postgres.cita(schema)}.{postgres.cita(tabella)}")
            return cur.fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------- collegamento


def test_ci_si_collega_e_si_leggono_gli_schemi(store: Store, url_server: str) -> None:
    esito = sql.prova(store, url=url_server)
    assert esito["ok"] is True
    assert "PostgreSQL" in esito["versione"]
    assert "public" in esito["schemi"]


def test_una_password_sbagliata_da_un_errore_leggibile(store: Store, url_server: str) -> None:
    rotto = url_server.replace(f":{PASSWORD}@", ":sbagliata@")
    with pytest.raises(postgres.ErroreSql) as exc:
        sql.prova(store, url=rotto)
    assert "password" in str(exc.value).lower()


# ------------------------------------------------------------------ creazione


def test_il_ddl_generato_viene_accettato(store: Store, url_server: str, schema_pulito: str) -> None:
    """La verifica che nessun test simulato può dare: il server lo esegue davvero."""
    sql.crea(
        store,
        url=url_server,
        schema=schema_pulito,
        prefisso="scriba_",
        tabelle=["call", "task", "analisi", "trascrizione"],
    )
    conn = postgres.connetti(url_server)
    try:
        tabelle = postgres.elenca_tabelle(conn, schema_pulito)
    finally:
        conn.close()
    assert sorted(tabelle) == [
        "scriba_analisi",
        "scriba_call",
        "scriba_task",
        "scriba_trascrizione",
    ]


def test_creare_due_volte_non_da_errore(store: Store, url_server: str, schema_pulito: str) -> None:
    """`IF NOT EXISTS` ovunque: ricollegare non deve rompersi su quello che c'è già."""
    for _ in range(2):
        sql.crea(store, url=url_server, schema=schema_pulito, tabelle=["call"])


# --------------------------------------------------------------------- invio


def test_una_call_arriva_intera(store: Store, url_server: str, schema_pulito: str) -> None:
    sid = _call(store)
    sql.crea(
        store,
        url=url_server,
        schema=schema_pulito,
        tabelle=["call", "task", "trascrizione"],
    )
    esito = sql.invia(sid, store)

    assert esito["ok"] is True
    assert _conta(url_server, schema_pulito, "scriba_call") == 1
    assert _conta(url_server, schema_pulito, "scriba_task") == 1
    assert _conta(url_server, schema_pulito, "scriba_trascrizione") == 2


def test_i_valori_arrivano_giusti(store: Store, url_server: str, schema_pulito: str) -> None:
    sid = _call(store, titolo="Riunione col cliente")
    sql.crea(store, url=url_server, schema=schema_pulito, tabelle=["call"])
    sql.invia(sid, store)

    conn = postgres.connetti(url_server)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'SELECT "titolo", "cliente", "piattaforma", "durata_ms", "inizio" '
                f"FROM {postgres.cita(schema_pulito)}.\"scriba_call\""
            )
            riga = cur.fetchone()
    finally:
        conn.close()

    assert riga[0] == "Riunione col cliente"
    assert riga[1] == "Acme"
    assert riga[2] == "zoom"
    assert riga[3] == 3_600_000
    # L'istante è arrivato come istante, non come numero: è la conversione che
    # avviene solo al momento dell'invio.
    assert riga[4].year == 2026


def test_rimandare_la_stessa_call_non_duplica(
    store: Store, url_server: str, schema_pulito: str
) -> None:
    """Il motivo per cui esistono le chiavi naturali: duplicare le task di una
    riunione dentro il sistema di lavoro di qualcuno è un danno vero."""
    sid = _call(store)
    sql.crea(store, url=url_server, schema=schema_pulito, tabelle=["call", "task", "trascrizione"])

    for _ in range(3):
        sql.invia(sid, store)

    assert _conta(url_server, schema_pulito, "scriba_call") == 1
    assert _conta(url_server, schema_pulito, "scriba_task") == 1
    assert _conta(url_server, schema_pulito, "scriba_trascrizione") == 2


def test_rimandare_aggiorna_quello_che_e_cambiato(
    store: Store, url_server: str, schema_pulito: str
) -> None:
    sid = _call(store, titolo="Prima versione")
    sql.crea(store, url=url_server, schema=schema_pulito, tabelle=["call"])
    sql.invia(sid, store)

    with store.tx() as conn:
        conn.execute("UPDATE sessions SET titolo = ? WHERE id = ?", ("Titolo corretto", sid))
    sql.invia(sid, store)

    conn = postgres.connetti(url_server)
    try:
        with conn.cursor() as cur:
            cur.execute(f'SELECT "titolo" FROM {postgres.cita(schema_pulito)}."scriba_call"')
            assert cur.fetchone()[0] == "Titolo corretto"
    finally:
        conn.close()


def test_l_esito_resta_annotato_in_locale(store: Store, url_server: str, schema_pulito: str) -> None:
    sid = _call(store)
    sql.crea(store, url=url_server, schema=schema_pulito, tabelle=["call"])
    sql.invia(sid, store)

    riga = store.conn.execute(
        "SELECT esito, righe FROM sync_remoto WHERE session_id = ?", (sid,)
    ).fetchone()
    assert riga["esito"] == "ok"
    assert riga["righe"] == 1


def test_un_invio_fallito_non_lascia_la_call_a_meta(
    store: Store, url_server: str, schema_pulito: str
) -> None:
    """Una call scritta a metà è peggio di una assente: sembra completa."""
    sid = _call(store)
    sql.crea(store, url=url_server, schema=schema_pulito, tabelle=["call", "task"])

    # Si toglie una colonna che l'invio userà: la scrittura delle task fallirà
    # dopo che quella della call è già passata, nella stessa transazione.
    conn = postgres.connetti(url_server)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'ALTER TABLE {postgres.cita(schema_pulito)}."scriba_task" DROP COLUMN "titolo"'
            )
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(postgres.ErroreSql):
        sql.invia(sid, store)

    assert _conta(url_server, schema_pulito, "scriba_call") == 0


# ---------------------------------------------------------------- mappatura


def test_si_puo_scrivere_in_una_tabella_gia_esistente(
    store: Store, url_server: str, schema_pulito: str
) -> None:
    """L'altra metà della richiesta: chi ha già il suo schema non si fa creare niente."""
    conn = postgres.connetti(url_server)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE {postgres.cita(schema_pulito)}."riunioni" (
                  "id" text PRIMARY KEY,
                  "nome" text,
                  "quando" timestamptz,
                  "sincronizzato_at" timestamptz DEFAULT now()
                )
                """
            )
        conn.commit()
    finally:
        conn.close()

    sid = _call(store, titolo="Su tabella mia")
    sql.collega(
        store,
        url=url_server,
        schema=schema_pulito,
        tabelle={
            "call": {
                "nome": "riunioni",
                "colonne": {"uuid": "id", "titolo": "nome", "inizio": "quando"},
            }
        },
    )
    sql.invia(sid, store)

    conn = postgres.connetti(url_server)
    try:
        with conn.cursor() as cur:
            cur.execute(f'SELECT "nome" FROM {postgres.cita(schema_pulito)}."riunioni"')
            assert cur.fetchone()[0] == "Su tabella mia"
    finally:
        conn.close()


def test_le_colonne_esistenti_si_leggono_col_tipo_giusto(
    store: Store, url_server: str, schema_pulito: str
) -> None:
    conn = postgres.connetti(url_server)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f'CREATE TABLE {postgres.cita(schema_pulito)}."riunioni" '
                '("id" text, "quando" timestamptz, "quante" bigint)'
            )
        conn.commit()
    finally:
        conn.close()

    esito = sql.colonne_di(
        store, url=url_server, schema=schema_pulito, tabella="riunioni", per="call"
    )
    per_campo = {c["chiave"]: c["ammesse"] for c in esito["campi"]}
    # Un istante non si propone per una colonna di testo: sarebbe lasciar
    # scegliere un errore che si vedrebbe solo al primo invio.
    assert per_campo["inizio"] == ["quando"]
    assert "id" in per_campo["titolo"]
    assert per_campo["durata_ms"] == ["quante"]


# ------------------------------------------------------------- il pregresso


def test_sincronizza_tutto_prende_le_call_arretrate(
    store: Store, url_server: str, schema_pulito: str
) -> None:
    a = _call(store, titolo="Prima")
    b = _call(store, titolo="Seconda")
    for sid in (a, b):
        store.set_session_state(sid, "ready")

    sql.crea(store, url=url_server, schema=schema_pulito, tabelle=["call"])
    esito = sql.sincronizza_tutto(store)

    assert esito["sincronizzate"] == 2
    assert esito["fallite"] == 0
    assert _conta(url_server, schema_pulito, "scriba_call") == 2
    assert sql.da_sincronizzare(store) == []
