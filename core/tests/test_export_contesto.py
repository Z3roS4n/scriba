"""Test del documento pensato per essere dato a un modello.

Il criterio con cui questi test sono scelti: un documento che un modello legge
per ragionarci sopra ha un modo di essere sbagliato che gli altri export non
hanno — **può far sembrare verificato quello che non lo è**. Se una task senza
citazioni viene mostrata come le altre, il modello che legge la tratta come le
altre, e l'ipotesi del primo modello diventa la premessa del secondo.

Metà di questi test guardano lì.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.db.store import Store  # noqa: E402
from scriba_core.export import contesto  # noqa: E402


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "scriba.sqlite")


def _call(store: Store, titolo: str = "Allineamento") -> int:
    sid = store.create_session(1_785_000_000_000, titolo=titolo, piattaforma="zoom")
    store.end_session(sid, 1_785_003_600_000)
    store.add_segment(sid, "loopback", 0, 4_000, "ti mando il preventivo lunedì", is_final=True)
    store.add_segment(sid, "mic", 60_000, 64_000, "perfetto, grazie", is_final=True)
    return sid


def _task_con_prova(store: Store, sid: int) -> int:
    seg = store.segments(sid, only_final=True)[0]
    return store.add_task(
        sid,
        "Mandare il preventivo",
        assignee_text="Marco",
        due_date="2026-09-01",
        due_raw="lunedì",
        priorita="alta",
        confidence=0.82,
        evidence=[
            {"segment_id": seg.id, "supports": "esistenza"},
            {"segment_id": seg.id, "supports": "due_date"},
        ],
    )


# ------------------------------------------------------------- le fonti


def test_la_citazione_sta_accanto_a_cio_che_sostiene(store: Store) -> None:
    """È tutto il punto: nessun id da incrociare."""
    sid = _call(store)
    _task_con_prova(store, sid)
    testo = contesto.costruisci(store, [sid])
    assert "«ti mando il preventivo lunedì»" in testo
    assert "che esista — [00:00]" in testo


def test_ogni_campo_dice_da_dove_viene(store: Store) -> None:
    sid = _call(store)
    _task_con_prova(store, sid)
    testo = contesto.costruisci(store, [sid])
    assert "che esista" in testo
    assert "la scadenza" in testo


def test_una_task_senza_prove_lo_dichiara(store: Store) -> None:
    """Il difetto peggiore possibile qui: farla sembrare ancorata come le altre."""
    sid = _call(store)
    store.add_task(sid, "Impegno dedotto dal nulla")
    testo = contesto.costruisci(store, [sid])
    assert "nessuna citazione" in testo
    assert "ipotesi" in testo


def test_l_intestazione_spiega_come_leggere_le_fonti(store: Store) -> None:
    """Senza, «nessuna citazione» sembra una dimenticanza invece di un dato."""
    sid = _call(store)
    testo = contesto.costruisci(store, [sid])
    assert "trascrizione letterale" in testo
    assert "interpretazione" in testo


def test_una_task_non_confermata_e_segnalata(store: Store) -> None:
    sid = _call(store)
    store.add_task(sid, "Da rivedere", needs_review=True, review_reason="responsabile incerto")
    testo = contesto.costruisci(store, [sid])
    assert "non ancora confermata da una persona" in testo
    assert "responsabile incerto" in testo


def test_una_scadenza_detta_ma_non_risolta_resta_ambigua(store: Store) -> None:
    """Sceglierne una lettura al posto di chi legge sarebbe inventare un fatto."""
    sid = _call(store)
    store.add_task(sid, "Cosa vaga", due_raw="entro fine mese")
    testo = contesto.costruisci(store, [sid])
    assert "non risolta" in testo
    assert "«entro fine mese»" in testo


# --------------------------------------------------------------- contenuto


def test_le_task_rifiutate_non_ci_sono(store: Store) -> None:
    sid = _call(store)
    tid = store.add_task(sid, "Scartata")
    with store.tx() as conn:
        conn.execute("UPDATE tasks SET stato = 'rejected' WHERE id = ?", (tid,))
    assert "Scartata" not in contesto.costruisci(store, [sid])


def test_senza_task_lo_dice(store: Store) -> None:
    sid = _call(store)
    assert "Nessun impegno estratto" in contesto.costruisci(store, [sid])


def test_il_cliente_compare_se_c_e(store: Store) -> None:
    sid = _call(store)
    cid = store.crea_cliente("Acme")
    store.assegna_cliente(sid, cid)
    assert "cliente: Acme" in contesto.costruisci(store, [sid])


def test_dice_con_quale_modello_e_stata_analizzata(store: Store) -> None:
    """Chi legge deve poter pesare quanto fidarsi di quello che segue."""
    sid = _call(store)
    store.set_analysis_meta(
        sid,
        provider="local",
        etichetta_provider="Modello locale",
        modello="gemma-4-12b-it",
        costo_usd=0.0,
        durata_ms=1000,
        finita_at=1_785_003_700_000,
    )
    testo = contesto.costruisci(store, [sid])
    assert "Modello locale" in testo
    assert "gemma-4-12b-it" in testo


def test_il_testo_degli_screenshot_entra(store: Store) -> None:
    sid = _call(store)
    shot = store.add_screenshot(sid, 30_000, "C:/x/shot.png")
    store.set_screenshot_ocr(shot, "Fatturato Q3: 1,2M")
    testo = contesto.costruisci(store, [sid])
    assert "Fatturato Q3: 1,2M" in testo


# ------------------------------------------------------- la trascrizione


def test_senza_trascrizione_restano_solo_le_parti_citate(store: Store) -> None:
    sid = _call(store)
    _task_con_prova(store, sid)
    testo = contesto.costruisci(store, [sid], con_trascrizione=False)
    assert "Trascrizione integrale" not in testo
    # La frase citata c'e' comunque: e' una fonte, non trascrizione.
    assert "ti mando il preventivo" in testo
    # Quella non citata no.
    assert "perfetto, grazie" not in testo


def test_con_trascrizione_c_e_tutto(store: Store) -> None:
    sid = _call(store)
    testo = contesto.costruisci(store, [sid], con_trascrizione=True)
    assert "Trascrizione integrale" in testo
    assert "perfetto, grazie" in testo


def test_l_intestazione_dice_se_la_trascrizione_manca(store: Store) -> None:
    sid = _call(store)
    assert "non è inclusa" in contesto.costruisci(store, [sid], con_trascrizione=False)


def test_la_trascrizione_pesa_e_si_vede_prima(store: Store) -> None:
    """La scelta «la includo?» si fa guardando un numero, non a naso."""
    sid = _call(store)
    senza = contesto.anteprima(store, [sid], con_trascrizione=False)
    con = contesto.anteprima(store, [sid], con_trascrizione=True)
    assert con["token_stimati"] > senza["token_stimati"]
    assert senza["call"] == 1


# ------------------------------------------------------------- piu' call


def test_piu_call_in_un_documento_solo(store: Store) -> None:
    """La domanda vera e' «dammi tutto quello che ci siamo detti con questo cliente»."""
    a = _call(store, "Primo incontro")
    b = _call(store, "Secondo incontro")
    testo = contesto.costruisci(store, [a, b])
    assert "Primo incontro" in testo
    assert "Secondo incontro" in testo
    assert "2 riunioni" in testo


def test_una_call_sola_si_dice_al_singolare(store: Store) -> None:
    sid = _call(store)
    assert "1 riunione," in contesto.costruisci(store, [sid])


def test_nessuna_call_e_un_errore(store: Store) -> None:
    with pytest.raises(ValueError, match="Nessuna call"):
        contesto.costruisci(store, [])


def test_una_call_inesistente_e_un_errore(store: Store) -> None:
    with pytest.raises(ValueError, match="inesistente"):
        contesto.costruisci(store, [999])


# ---------------------------------------------------------------- il file


def test_scrive_un_file_leggibile(store: Store, tmp_path: Path) -> None:
    sid = _call(store)
    _task_con_prova(store, sid)
    percorso = contesto.esporta(store, [sid], tmp_path / "fuori")
    assert percorso.exists()
    assert percorso.suffix == ".md"
    assert "Mandare il preventivo" in percorso.read_text(encoding="utf-8")


def test_il_nome_dice_che_e_un_contesto(store: Store, tmp_path: Path) -> None:
    sid = _call(store)
    percorso = contesto.esporta(store, [sid], tmp_path / "fuori")
    assert "contesto" in percorso.name


def test_con_piu_call_il_nome_lo_dice(store: Store, tmp_path: Path) -> None:
    a, b = _call(store, "Uno"), _call(store, "Due")
    percorso = contesto.esporta(store, [a, b], tmp_path / "fuori")
    assert "2-call" in percorso.name


def test_la_stima_dei_token_e_un_ordine_di_grandezza(store: Store) -> None:
    assert contesto.stima_token("a" * 400) == 100
    # Mai zero: un documento vuoto non esiste, e uno zero si legge come «gratis».
    assert contesto.stima_token("") == 1


def test_la_data_e_in_italiano(store: Store) -> None:
    """`strftime("%B")` segue la locale del processo: dentro un documento
    italiano uscirebbe «July», e la prima stesura lo faceva."""
    sid = _call(store)
    testo = contesto.costruisci(store, [sid])
    assert "luglio" in testo
    assert "July" not in testo


def test_lo_stato_della_task_e_in_italiano(store: Store) -> None:
    """Un valore grezzo del database dentro un testo italiano fa credere a chi
    legge che sia un termine tecnico da preservare."""
    sid = _call(store)
    store.add_task(sid, "Qualcosa")
    testo = contesto.costruisci(store, [sid])
    assert "proposta dal modello" in testo
    assert "proposed" not in testo
