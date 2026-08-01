"""Test del database remoto (PostgreSQL) senza toccare la rete.

Qui si verifica quello che si può verificare senza un server: come si legge un
indirizzo, che SQL si genera, cosa succede a un segreto, e quali configurazioni
vengono rifiutate. La prova contro un PostgreSQL vero sta in
`test_database_remoto_vero.py`, e si accende da sola quando ce n'è uno.

Il criterio con cui questi test sono scelti: ognuno copre un modo in cui questa
integrazione può fallire **in silenzio** — scrivendo doppioni, mandando dati in
chiaro, o dando un errore che manda a cercare nel posto sbagliato.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.db.store import Store  # noqa: E402
from scriba_core.export import sql  # noqa: E402
from scriba_core.export.sql import modello, postgres, segreti  # noqa: E402
from scriba_core.export.sql.postgres import ErroreSql  # noqa: E402

URL = "postgresql://tizio:segreta@db.esempio.com:5432/prod"


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "scriba.sqlite")


# ---------------------------------------------------------------------- URL


def test_legge_le_parti_dell_indirizzo() -> None:
    d = postgres.analizza_url(URL)
    assert d["host"] == "db.esempio.com"
    assert d["porta"] == 5432
    assert d["database"] == "prod"
    assert d["utente"] == "tizio"


def test_la_password_non_esce_dall_analisi() -> None:
    """Si dice *che* c'è, mai quale sia: è la stessa regola del token Notion."""
    d = postgres.analizza_url(URL)
    assert d["password_presente"] is True
    assert "segreta" not in repr(d)


def test_un_indirizzo_di_un_altro_motore_viene_rifiutato() -> None:
    with pytest.raises(ErroreSql, match="postgresql://"):
        postgres.analizza_url("mysql://tizio@host/db")


def test_un_indirizzo_vuoto_lo_dice() -> None:
    with pytest.raises(ErroreSql, match="[Mm]anca"):
        postgres.analizza_url("   ")


@pytest.mark.parametrize(
    "url,attesa",
    [
        ("postgresql://u:p@db.abc.supabase.co:5432/postgres", "diretta"),
        ("postgresql://u:p@aws-0-eu-west-1.pooler.supabase.com:6543/postgres", "pooling_transazione"),
        ("postgresql://u:p@aws-0-eu-west-1.pooler.supabase.com:5432/postgres", "pooling_sessione"),
        ("postgresql://u:p@localhost/scriba", "diretta"),
    ],
)
def test_indovina_la_modalita_dall_indirizzo(url: str, attesa: str) -> None:
    """Indovinarla bene evita l'unico errore che nessuno diagnosticherebbe da solo."""
    assert postgres.analizza_url(url)["modalita_dedotta"] == attesa


def test_col_pooler_a_transazione_gli_statement_preparati_si_spengono() -> None:
    """Senza, la seconda sincronizzazione fallisce con un messaggio incomprensibile."""
    _, opzioni = postgres.prepara_url(URL, modalita="pooling_transazione")
    assert opzioni["prepare_threshold"] is None


def test_sulla_diretta_restano_accesi() -> None:
    _, opzioni = postgres.prepara_url(URL, modalita="diretta")
    assert "prepare_threshold" not in opzioni


def test_verso_un_server_remoto_il_cifrato_si_impone() -> None:
    completo, _ = postgres.prepara_url(URL, modalita="diretta")
    assert "sslmode=require" in completo


def test_in_locale_non_si_impone_niente() -> None:
    """Un Postgres su questa macchina spesso non ha TLS, e non gli serve."""
    completo, _ = postgres.prepara_url("postgresql://u:p@localhost/scriba", modalita="diretta")
    assert "sslmode" not in completo


def test_una_scelta_esplicita_dell_utente_si_rispetta() -> None:
    completo, _ = postgres.prepara_url(f"{URL}?sslmode=verify-full", modalita="diretta")
    assert "sslmode=verify-full" in completo
    assert "sslmode=require" not in completo


# ------------------------------------------------------------------ messaggi


def test_il_caso_ipv6_di_supabase_viene_nominato() -> None:
    """«timeout» manda a controllare rete, password e firewall: ovunque tranne dove sta."""
    messaggio = postgres.spiega(
        Exception("connection timed out"),
        url="postgresql://u:p@db.abc.supabase.co:5432/postgres",
        modalita="diretta",
    )
    assert "IPv6" in messaggio
    assert "6543" in messaggio


def test_lo_statement_preparato_dice_cosa_fare() -> None:
    messaggio = postgres.spiega(
        Exception('prepared statement "_pg3_0" already exists'), url=URL, modalita="diretta"
    )
    assert "pooler" in messaggio
    assert "transazione" in messaggio


def test_una_password_sbagliata_si_riconosce() -> None:
    messaggio = postgres.spiega(
        Exception("password authentication failed for user"), url=URL, modalita="diretta"
    )
    assert "password" in messaggio.lower()


# ----------------------------------------------------------------- identificatori


def test_gli_identificatori_si_citano_sempre() -> None:
    assert postgres.cita("call") == '"call"'


def test_un_apice_dentro_un_nome_non_esce_dalle_virgolette() -> None:
    """È la differenza fra un nome strano e un'iniezione SQL."""
    assert postgres.cita('a"; DROP TABLE x; --') == '"a""; DROP TABLE x; --"'


def test_un_nome_vuoto_viene_rifiutato() -> None:
    with pytest.raises(ErroreSql):
        postgres.cita("")


# -------------------------------------------------------------------- DDL


def test_il_ddl_non_distrugge_niente() -> None:
    """Su un database che è di qualcun altro si aggiunge, non si sistema d'ufficio."""
    sql_ddl = postgres.ddl_tabella("pubblico", "scriba_call", list(modello.CALL.campi), ("uuid",))
    assert "CREATE TABLE IF NOT EXISTS" in sql_ddl
    assert "DROP" not in sql_ddl.upper()
    assert "ALTER" not in sql_ddl.upper()


def test_il_ddl_mette_la_chiave_primaria() -> None:
    sql_ddl = postgres.ddl_tabella("pubblico", "scriba_call", list(modello.CALL.campi), ("uuid",))
    assert 'PRIMARY KEY ("uuid")' in sql_ddl


def test_gli_istanti_portano_il_fuso() -> None:
    """Un istante senza fuso è un istante di cui non si sa niente."""
    sql_ddl = postgres.ddl_tabella("pubblico", "scriba_call", list(modello.CALL.campi), ("uuid",))
    assert '"inizio" timestamptz' in sql_ddl


def test_ogni_tabella_dice_quando_e_arrivata() -> None:
    sql_ddl = postgres.ddl_tabella("pubblico", "scriba_call", list(modello.CALL.campi), ("uuid",))
    assert '"sincronizzato_at" timestamptz' in sql_ddl


# ----------------------------------------------------------------- upsert


def test_risincronizzare_aggiorna_invece_di_duplicare() -> None:
    """Duplicare le task di una riunione dentro il lavoro di qualcuno è un danno vero."""
    s = postgres.upsert("pubblico", "scriba_task", ["uuid", "titolo", "stato"], ("uuid",))
    assert "ON CONFLICT (\"uuid\") DO UPDATE" in s
    assert '"titolo" = EXCLUDED."titolo"' in s


def test_la_chiave_non_si_riscrive_con_se_stessa() -> None:
    s = postgres.upsert("pubblico", "scriba_task", ["uuid", "titolo"], ("uuid",))
    assert '"uuid" = EXCLUDED."uuid"' not in s


def test_una_chiave_composta_funziona() -> None:
    s = postgres.upsert(
        "pubblico", "scriba_trascrizione", ["call_uuid", "indice", "testo"], ("call_uuid", "indice")
    )
    assert 'ON CONFLICT ("call_uuid", "indice")' in s


def test_senza_chiave_si_rifiuta_invece_di_inserire_doppioni() -> None:
    with pytest.raises(ErroreSql, match="chiave"):
        postgres.upsert("pubblico", "x", ["a"], ())


# ---------------------------------------------------------------- segreti


def test_il_segreto_va_e_torna(tmp_path: Path) -> None:
    cifrato = segreti.cifra(URL)
    assert segreti.decifra(cifrato) == URL


def test_il_segreto_non_e_leggibile_a_occhio() -> None:
    assert "segreta" not in segreti.cifra(URL)


def test_un_segreto_illeggibile_non_fa_esplodere_niente() -> None:
    """Copiato da un altro account: si presenta come «non collegato», che è la verità."""
    assert segreti.decifra("dpapi:cXVlc3RvIG5vbiBlIGNpZnJhdG8=") == ""


def test_un_valore_senza_etichetta_e_di_una_versione_precedente() -> None:
    assert segreti.decifra(URL) == URL


# ----------------------------------------------------------- configurazione


def test_all_inizio_non_si_e_collegati(store: Store) -> None:
    s = sql.stato(store)
    assert s["collegato"] is False
    assert s["server"] is None


def test_lo_stato_non_riporta_mai_la_password(store: Store) -> None:
    sql.collega(store, url=URL, schema="pubblico", tabelle={})
    testo = repr(sql.stato(store))
    assert "segreta" not in testo
    assert "db.esempio.com" in testo  # il server sì: serve a sapere dove si scrive


def test_il_file_su_disco_non_contiene_la_password(store: Store, tmp_path: Path) -> None:
    """Chi legge quel file entrerebbe in un database di produzione."""
    sql.collega(store, url=URL, schema="pubblico", tabelle={})
    contenuto = (tmp_path / "database_remoto.json").read_text(encoding="utf-8")
    assert "segreta" not in contenuto


def test_un_url_vuoto_non_cancella_quello_salvato(store: Store) -> None:
    """L'interfaccia non lo rimanda indietro perché non gliel'abbiamo mai mostrato."""
    sql.collega(store, url=URL, schema="pubblico")
    sql.collega(store, schema="altro")
    assert sql.stato(store)["server"]["host"] == "db.esempio.com"


def test_scollegare_dimentica_tutto(store: Store) -> None:
    sql.collega(store, url=URL, schema="pubblico")
    sql.scollega(store)
    assert sql.stato(store)["collegato"] is False


def test_una_modalita_inventata_viene_rifiutata(store: Store) -> None:
    with pytest.raises(ErroreSql, match="[Mm]odalità"):
        sql.collega(store, url=URL, modalita="magica")


def test_un_file_di_configurazione_rovinato_non_impedisce_l_avvio(store: Store, tmp_path: Path) -> None:
    (tmp_path / "database_remoto.json").write_text("{ questo non è json", encoding="utf-8")
    assert sql.stato(store)["collegato"] is False


# ---------------------------------------------------- verifica della mappatura


def _mappa_valida() -> dict:
    return {
        "call": {
            "nome": "riunioni",
            "colonne": {"uuid": "id", "titolo": "nome", "inizio": "iniziata_il"},
        }
    }


def test_una_mappatura_sensata_si_accetta(store: Store) -> None:
    sql.collega(store, url=URL, schema="pubblico", tabelle=_mappa_valida())
    assert "call" in sql.stato(store)["tabelle"]


def test_senza_la_chiave_naturale_si_rifiuta(store: Store) -> None:
    """Senza, ogni sincronizzazione aggiungerebbe doppioni per sempre."""
    mappa = _mappa_valida()
    del mappa["call"]["colonne"]["uuid"]
    with pytest.raises(ErroreSql, match="doppioni|riconoscono"):
        sql.collega(store, url=URL, schema="pubblico", tabelle=mappa)


def test_un_campo_che_non_esiste_si_rifiuta(store: Store) -> None:
    mappa = _mappa_valida()
    mappa["call"]["colonne"]["inventato"] = "x"
    with pytest.raises(ErroreSql, match="inventato"):
        sql.collega(store, url=URL, schema="pubblico", tabelle=mappa)


def test_senza_nome_della_tabella_remota_si_rifiuta(store: Store) -> None:
    mappa = _mappa_valida()
    mappa["call"]["nome"] = ""
    with pytest.raises(ErroreSql, match="nome"):
        sql.collega(store, url=URL, schema="pubblico", tabelle=mappa)


def test_cambiare_server_dimentica_cosa_era_gia_stato_mandato(store: Store) -> None:
    """Tenerli significherebbe riportare «aggiornate» righe di un altro database."""
    sid = store.create_session(1_785_000_000_000)
    sql.collega(store, url=URL, schema="pubblico")
    sql._annota(store, sid, "ok", None, 10)
    assert store.conn.execute("SELECT COUNT(*) c FROM sync_remoto").fetchone()["c"] == 1

    sql.collega(store, url="postgresql://u:p@altro.server.com/db")
    assert store.conn.execute("SELECT COUNT(*) c FROM sync_remoto").fetchone()["c"] == 0


# --------------------------------------------------------------- anteprima


def test_l_anteprima_mostra_il_ddl_prima_di_eseguirlo() -> None:
    pezzi = sql.anteprima_ddl(schema="pubblico", prefisso="scriba_", tabelle=["call", "task"])
    nomi = [p["tabella"] for p in pezzi]
    assert nomi == ["(schema)", "scriba_call", "scriba_task"]
    assert all("CREATE" in p["sql"] for p in pezzi)


# ------------------------------------------------------------- estrazione


def _call_completa(store: Store) -> int:
    cid = store.crea_cliente("Acme")
    sid = store.create_session(1_785_000_000_000, titolo="Allineamento", piattaforma="zoom")
    store.assegna_cliente(sid, cid)
    store.add_segment(sid, "loopback", 0, 4_000, "parliamo del budget", is_final=True)
    store.add_segment(sid, "mic", 4_000, 8_000, "d'accordo", is_final=True)
    store.add_task(sid, "Mandare il preventivo", assignee_text="Marco", due_date="2026-09-01")
    return sid


def test_la_call_porta_con_se_il_cliente(store: Store) -> None:
    sid = _call_completa(store)
    riga = modello.righe(store, sid, "call")[0]
    assert riga["cliente"] == "Acme"
    assert riga["titolo"] == "Allineamento"
    assert riga["uuid"]


def test_le_task_hanno_un_id_stabile(store: Store) -> None:
    """`tasks.id` è un contatore di questo file: due installazioni si sovrascriverebbero."""
    sid = _call_completa(store)
    righe = modello.righe(store, sid, "task")
    assert len(righe) == 1
    assert righe[0]["uuid"]
    assert righe[0]["assegnatario"] == "Marco"


def test_le_task_sanno_a_quale_call_appartengono(store: Store) -> None:
    sid = _call_completa(store)
    assert modello.righe(store, sid, "task")[0]["call_uuid"] == modello.righe(store, sid, "call")[0]["uuid"]


def test_la_trascrizione_si_numera_per_posizione(store: Store) -> None:
    """Non per id: ricostruire il database cambierebbe la chiave di ogni riga."""
    sid = _call_completa(store)
    righe = modello.righe(store, sid, "trascrizione")
    assert [r["indice"] for r in righe] == [0, 1]
    assert righe[0]["sorgente"] == "loopback"


def test_una_sessione_inesistente_lo_dice(store: Store) -> None:
    with pytest.raises(ValueError, match="inesistente"):
        modello.righe(store, 999, "call")


def test_una_tabella_inventata_lo_dice(store: Store) -> None:
    sid = _call_completa(store)
    with pytest.raises(ValueError, match="sconosciuta"):
        modello.righe(store, sid, "inventata")


def test_ogni_tabella_del_modello_sa_riconoscere_le_sue_righe() -> None:
    """Una tabella senza chiave naturale produrrebbe doppioni a ogni invio."""
    for t in modello.TABELLE:
        assert t.chiave_naturale, f"{t.chiave} non ha una chiave naturale"


def test_ogni_campo_ha_un_tipo_che_il_dialetto_sa_scrivere() -> None:
    for t in modello.TABELLE:
        for c in t.campi:
            assert c.tipo in postgres.TIPI_SQL, f"{t.chiave}.{c.chiave}: tipo {c.tipo}"


# ------------------------------------------------------------------ pregresso


def test_le_call_mai_sincronizzate_sono_da_fare(store: Store) -> None:
    sid = _call_completa(store)
    store.set_session_state(sid, "ready")
    assert sql.da_sincronizzare(store) == [sid]


def test_una_call_gia_sincronizzata_non_si_rifa(store: Store) -> None:
    sid = _call_completa(store)
    store.set_session_state(sid, "ready")
    sql._annota(store, sid, "ok", None, 5)
    assert sql.da_sincronizzare(store) == []


def test_una_sincronizzazione_fallita_si_riprova(store: Store) -> None:
    sid = _call_completa(store)
    store.set_session_state(sid, "ready")
    sql._annota(store, sid, "errore", "server irraggiungibile", 0)
    assert sql.da_sincronizzare(store) == [sid]


def test_una_call_in_corso_si_lascia_stare(store: Store) -> None:
    """Si sincronizza quello che è finito, non quello che sta ancora succedendo."""
    _call_completa(store)  # resta in stato 'recording'
    assert sql.da_sincronizzare(store) == []
