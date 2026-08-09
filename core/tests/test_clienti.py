"""Test dei clienti e dell'archivio.

Tre cose che devono valere, e che sono facili da rompere senza accorgersene:

1. **Lo stesso cliente non si sdoppia.** Importare due volte lo stesso elenco,
   o scriverlo con maiuscole diverse, deve dare un cliente solo. Il giorno in
   cui "Acme" e "ACME  S.r.l. " diventano due righe distinte, il
   raggruppamento per cliente smette di rispondere alla domanda per cui esiste.
2. **Eliminare un cliente non porta via le sue call.** Le call sono il lavoro,
   il cliente è un'etichetta.
3. **La ricerca non esplode su quello che si digita.** Una casella di ricerca
   riceve virgolette, asterischi e la parola AND: FTS5 li legge come sintassi.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.api.clienti import leggi_csv  # noqa: E402
from scriba_core.db.store import Store  # noqa: E402


def _store(tmp_path: Path) -> Store:
    return Store(tmp_path / "scriba.sqlite")


# ------------------------------------------------------------------- clienti


def test_crea_cliente_restituisce_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.crea_cliente("Acme") is not None


def test_nome_gia_presente_non_crea_un_doppione(tmp_path: Path) -> None:
    store = _store(tmp_path)
    primo = store.crea_cliente("Acme S.r.l.")
    # Maiuscole diverse e spazi in più: è lo stesso cliente per una persona,
    # e deve esserlo anche per il database.
    secondo = store.crea_cliente("  ACME   s.r.l. ")
    assert primo == secondo
    assert len(store.clienti()) == 1


def test_nome_vuoto_non_crea_niente(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.crea_cliente("   ") is None
    assert store.clienti() == []


def test_il_nome_si_salva_come_scritto(tmp_path: Path) -> None:
    """Si confronta normalizzato, ma si mostra come l'ha scritto l'utente."""
    store = _store(tmp_path)
    store.crea_cliente("  Acme   S.r.l.  ")
    assert store.clienti()[0]["nome"] == "Acme S.r.l."


def test_rinomina(tmp_path: Path) -> None:
    store = _store(tmp_path)
    cid = store.crea_cliente("Acme")
    assert cid is not None
    assert store.aggiorna_cliente(cid, nome="Acme Italia") is True
    assert store.clienti()[0]["nome"] == "Acme Italia"


def test_rinomina_su_un_nome_gia_di_un_altro_viene_rifiutata(tmp_path: Path) -> None:
    """Fondere due clienti è una decisione, non l'effetto di una rinomina."""
    store = _store(tmp_path)
    store.crea_cliente("Acme")
    altro = store.crea_cliente("Globex")
    assert altro is not None
    assert store.aggiorna_cliente(altro, nome="acme") is False
    nomi = sorted(r["nome"] for r in store.clienti())
    assert nomi == ["Acme", "Globex"]


def test_archiviare_lo_toglie_dall_elenco_ma_non_lo_cancella(tmp_path: Path) -> None:
    store = _store(tmp_path)
    cid = store.crea_cliente("Acme")
    assert cid is not None
    store.aggiorna_cliente(cid, archiviato=True)
    assert store.clienti() == []
    assert len(store.clienti(includi_archiviati=True)) == 1


def test_conteggio_call_per_cliente(tmp_path: Path) -> None:
    store = _store(tmp_path)
    cid = store.crea_cliente("Acme")
    assert cid is not None
    for t in (1_785_000_000_000, 1_785_000_100_000):
        sid = store.create_session(t)
        store.assegna_cliente(sid, cid)
    store.create_session(1_785_000_200_000)  # senza cliente

    riga = store.clienti()[0]
    assert riga["n_call"] == 2
    assert riga["ultima_call"] == 1_785_000_100_000


def test_eliminare_un_cliente_non_elimina_le_sue_call(tmp_path: Path) -> None:
    store = _store(tmp_path)
    cid = store.crea_cliente("Acme")
    assert cid is not None
    sid = store.create_session(1_785_000_000_000, titolo="Allineamento")
    store.assegna_cliente(sid, cid)

    assert store.elimina_cliente(cid) is True

    sessione = store.get_session(sid)
    assert sessione is not None
    assert sessione["titolo"] == "Allineamento"
    assert sessione["client_id"] is None


def test_assegnare_un_cliente_inesistente_fallisce(tmp_path: Path) -> None:
    store = _store(tmp_path)
    sid = store.create_session(1_785_000_000_000)
    assert store.assegna_cliente(sid, 999) is False


def test_togliere_il_cliente_da_una_call(tmp_path: Path) -> None:
    store = _store(tmp_path)
    cid = store.crea_cliente("Acme")
    sid = store.create_session(1_785_000_000_000)
    store.assegna_cliente(sid, cid)
    assert store.assegna_cliente(sid, None) is True
    sessione = store.get_session(sid)
    assert sessione is not None
    assert sessione["client_id"] is None


def test_importa_conta_creati_gia_presenti_e_scartati(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.crea_cliente("Acme")
    esito = store.importa_clienti([("Acme", None), ("Globex", "cliente storico"), ("  ", None)])
    assert esito == {"creati": 1, "gia_presenti": 1, "scartati": 1}


# ------------------------------------------------------------------ archivio


def _call_con_testo(store: Store, quando: int, titolo: str, detto: str) -> int:
    sid = store.create_session(quando, titolo=titolo)
    store.add_segment(sid, "loopback", 0, 4_000, detto, is_final=True)
    return sid


def test_ricerca_nel_parlato(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _call_con_testo(store, 1_785_000_000_000, "Lunedì", "parliamo del budget del trimestre")
    _call_con_testo(store, 1_785_000_100_000, "Martedì", "niente di rilevante qui")

    trovate = store.cerca_call(testo="budget")
    assert [r["titolo"] for r in trovate] == ["Lunedì"]


def test_la_ricerca_riporta_la_frase_trovata(tmp_path: Path) -> None:
    """Non basta sapere CHE una call ne parla: serve leggere dove.

    L'archivio risponde a «cosa ci siamo detti con questo cliente», e un elenco
    di titoli non lo dice. La frase c'era gia' nell'indice full-text e non la
    chiedeva nessuno.
    """
    store = _store(tmp_path)
    _call_con_testo(
        store,
        1_785_000_000_000,
        "Lunedi",
        "assicurati che sia scritto perche con il fornitore ce lo siamo detti a voce",
    )

    (riga,) = store.cerca_call(testo="fornitore")
    frammento = riga["frammento"]
    assert frammento, "nessun frammento: la ricerca dice solo che la parola c'e'"
    # I marcatori sono caratteri di controllo, non tag: qui non si produce HTML.
    assert "fornitore" in frammento
    assert "ce lo siamo detti" in frammento


def test_il_frammento_non_viene_da_una_riga_di_eco(tmp_path: Path) -> None:
    """Citare un'eco vorrebbe dire restituire all'utente le sue stesse parole
    rientrate dal microfono, spacciate per quello che ha detto l'altro."""
    store = _store(tmp_path)
    sid = store.create_session(1_785_000_000_000, titolo="Lunedi")
    eco = store.add_segment(sid, "mic", 0, 1_000, "il fornitore lo chiamo io", is_final=True)
    store.marca_eco(eco)
    store.add_segment(
        sid, "loopback", 2_000, 3_000, "senti, del fornitore parliamo domani", is_final=True
    )

    (riga,) = store.cerca_call(testo="fornitore")
    assert "parliamo domani" in riga["frammento"]
    assert "lo chiamo io" not in riga["frammento"]


def test_senza_ricerca_non_c_e_nessun_frammento(tmp_path: Path) -> None:
    # Sfogliando l'archivio senza cercare niente non c'e' una frase «trovata»:
    # inventarne una vorrebbe dire mettere in evidenza una riga a caso.
    store = _store(tmp_path)
    _call_con_testo(store, 1_785_000_000_000, "Lunedi", "una frase qualunque")
    (riga,) = store.cerca_call()
    assert riga["frammento"] is None


def test_ricerca_nel_titolo(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _call_con_testo(store, 1_785_000_000_000, "Riunione budget", "buongiorno a tutti")
    assert len(store.cerca_call(testo="budget")) == 1


def test_due_parole_stanno_in_and(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _call_con_testo(store, 1_785_000_000_000, "A", "il budget del trimestre")
    _call_con_testo(store, 1_785_000_100_000, "B", "il budget e basta")

    assert [r["titolo"] for r in store.cerca_call(testo="budget trimestre")] == ["A"]


def test_la_ricerca_non_esplode_sui_caratteri_speciali(tmp_path: Path) -> None:
    """Il contenuto di una casella di ricerca è testo, non sintassi FTS5."""
    store = _store(tmp_path)
    _call_con_testo(store, 1_785_000_000_000, "A", "parliamo del budget")

    for tentativo in ('"', 'budget"', "AND", "OR budget", "budget*", "NEAR(a b)", "^budget", "-"):
        store.cerca_call(testo=tentativo)  # non deve sollevare


def test_il_percento_nel_testo_e_letterale(tmp_path: Path) -> None:
    """Cercare '%' non deve diventare il jolly di LIKE e restituire tutto."""
    store = _store(tmp_path)
    _call_con_testo(store, 1_785_000_000_000, "Sconto 20%", "niente")
    _call_con_testo(store, 1_785_000_100_000, "Riunione", "niente")

    trovate = store.cerca_call(testo="20%")
    assert [r["titolo"] for r in trovate] == ["Sconto 20%"]


def test_filtro_per_cliente(tmp_path: Path) -> None:
    store = _store(tmp_path)
    cid = store.crea_cliente("Acme")
    sid = store.create_session(1_785_000_000_000, titolo="Con Acme")
    store.assegna_cliente(sid, cid)
    store.create_session(1_785_000_100_000, titolo="Senza")

    assert [r["titolo"] for r in store.cerca_call(client_id=cid)] == ["Con Acme"]


def test_filtro_senza_cliente(tmp_path: Path) -> None:
    """«Tutte» e «quelle senza cliente» sono due domande diverse."""
    store = _store(tmp_path)
    cid = store.crea_cliente("Acme")
    sid = store.create_session(1_785_000_000_000, titolo="Con Acme")
    store.assegna_cliente(sid, cid)
    store.create_session(1_785_000_100_000, titolo="Senza")

    assert [r["titolo"] for r in store.cerca_call(senza_cliente=True)] == ["Senza"]
    assert len(store.cerca_call()) == 2


def test_filtro_per_periodo(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create_session(1_785_000_000_000, titolo="Prima")
    store.create_session(1_785_000_200_000, titolo="Dopo")

    trovate = store.cerca_call(da_ms=1_785_000_100_000)
    assert [r["titolo"] for r in trovate] == ["Dopo"]


def test_lo_stato_registrata_copre_ready_e_transcribing(tmp_path: Path) -> None:
    """Uno stato mostrato può nascerne da più d'uno nel database."""
    store = _store(tmp_path)
    a = store.create_session(1_785_000_000_000, titolo="Pronta")
    b = store.create_session(1_785_000_100_000, titolo="In trascrizione")
    store.set_session_state(a, "ready")
    store.set_session_state(b, "transcribing")

    trovate = store.cerca_call(stati=("ready", "transcribing"))
    assert sorted(r["titolo"] for r in trovate) == ["In trascrizione", "Pronta"]


def test_l_archivio_porta_il_nome_del_cliente(tmp_path: Path) -> None:
    store = _store(tmp_path)
    cid = store.crea_cliente("Acme")
    sid = store.create_session(1_785_000_000_000)
    store.assegna_cliente(sid, cid)

    assert store.cerca_call()[0]["cliente"] == "Acme"


# ----------------------------------------------------------------------- CSV


def test_csv_con_intestazione() -> None:
    assert leggi_csv("nome,note\nAcme,cliente storico\nGlobex,\n") == [
        ("Acme", "cliente storico"),
        ("Globex", None),
    ]


def test_csv_col_punto_e_virgola() -> None:
    """Excel italiano esporta così, ed è il caso più probabile di tutti."""
    assert leggi_csv("nome;note\nAcme;primo\n") == [("Acme", "primo")]


def test_csv_senza_intestazione() -> None:
    """Un elenco di nomi e basta: la prima colonna è l'unica lettura sensata."""
    assert leggi_csv("Acme\nGlobex\n") == [("Acme", None), ("Globex", None)]


def test_csv_riconosce_intestazioni_diverse() -> None:
    assert leggi_csv("Ragione sociale,Descrizione\nAcme,primo\n") == [("Acme", "primo")]


def test_csv_salta_le_righe_senza_nome() -> None:
    assert leggi_csv("nome,note\nAcme,x\n,y\n") == [("Acme", "x")]


def test_csv_vuoto() -> None:
    assert leggi_csv("") == []
    assert leggi_csv("   \n  ") == []


def test_csv_con_bom() -> None:
    """Il BOM di Excel finirebbe nel primo nome, e quel cliente non tornerebbe più."""
    assert leggi_csv("﻿nome,note\nAcme,x\n") == [("Acme", "x")]
