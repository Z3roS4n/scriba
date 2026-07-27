"""Test dell'export in Markdown.

È l'export senza perdite: deve sopravvivere all'applicazione. Quello che si
verifica qui è che nel file ci sia davvero tutto, non solo il riassunto.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.db.store import Store  # noqa: E402
from scriba_core.export.markdown import esporta  # noqa: E402


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "export.sqlite")


@pytest.fixture()
def session_id(store: Store) -> int:
    sid = store.create_session(
        1_785_000_000_000,
        titolo="Revisione portale clienti",
        consenso_confermato_at=1_785_000_000_000,
    )
    store.end_session(sid, 1_785_003_180_000)

    s1 = store.add_segment(sid, "loopback", 300_000, 306_000,
                           "dovremmo preparare i mockup della dashboard", is_final=True)
    s2 = store.add_segment(sid, "mic", 1_920_000, 1_924_000,
                           "diciamo entro il quattordici", is_final=True)
    store.add_ai_output(sid, "summary", "## In breve\n\n* Mockup prima di sviluppare.",
                        model="gemma", provider="local", prompt_id="summary", prompt_version="v2")
    store.add_ai_output(sid, "highlights", "[05:00] **Mockup** — decisione presa.",
                        model="gemma", provider="local", prompt_id="highlights", prompt_version="v1")
    store.add_task(
        sid, "Preparare i mockup della dashboard",
        descrizione="Desktop e mobile",
        assignee_text="Marco", due_date="2026-08-14", due_raw="entro il quattordici",
        priorita="alta", confidence=0.85, needs_review=False,
        evidence=[{"segment_id": s1, "supports": "titolo"},
                  {"segment_id": s2, "supports": "due_date"}],
    )
    return sid


class TestContenuto:
    def test_il_file_contiene_tutto(self, store: Store, session_id: int, tmp_path: Path) -> None:
        testo = esporta(store, session_id, tmp_path).read_text(encoding="utf-8")

        assert "# Revisione portale clienti" in testo
        assert "Mockup prima di sviluppare" in testo          # riassunto
        assert "## Punti salienti" in testo
        assert "**Preparare i mockup della dashboard**" in testo
        assert "Marco" in testo and "2026-08-14" in testo
        assert "## Trascrizione" in testo
        # La trascrizione integrale c'e' sempre: e' il documento originale, e un
        # riassunto non lo sostituisce.
        assert "dovremmo preparare i mockup della dashboard" in testo
        assert "diciamo entro il quattordici" in testo

    def test_le_prove_restano_nel_file(self, store: Store, session_id: int, tmp_path: Path) -> None:
        # E' la parte che rende una task verificabile invece che solo
        # plausibile: senza, resta l'affermazione di un modello.
        testo = esporta(store, session_id, tmp_path).read_text(encoding="utf-8")
        assert "`05:00` titolo:" in testo
        assert "`32:00` due_date:" in testo

    def test_chi_ha_parlato_e_distinguibile(self, store: Store, session_id: int, tmp_path: Path) -> None:
        testo = esporta(store, session_id, tmp_path).read_text(encoding="utf-8")
        assert "**Altri** — dovremmo preparare" in testo
        assert "**Io** — diciamo entro" in testo

    def test_le_task_da_confermare_sono_segnalate(self, store: Store, tmp_path: Path) -> None:
        sid = store.create_session(1_785_000_000_000, titolo="X")
        store.add_task(sid, "Incerta", needs_review=True)
        testo = esporta(store, sid, tmp_path).read_text(encoding="utf-8")
        assert "(da confermare)" in testo

    def test_le_task_scartate_non_compaiono(self, store: Store, tmp_path: Path) -> None:
        sid = store.create_session(1_785_000_000_000, titolo="X")
        tid = store.add_task(sid, "Scartata")
        store.conn.execute("UPDATE tasks SET stato = 'rejected' WHERE id = ?", (tid,))
        assert "Scartata" not in esporta(store, sid, tmp_path).read_text(encoding="utf-8")

    def test_il_consenso_mancante_viene_annotato(self, store: Store, tmp_path: Path) -> None:
        # Chi rilegge il documento fra sei mesi deve poterlo sapere.
        sid = store.create_session(1_785_000_000_000, titolo="Senza consenso")
        testo = esporta(store, sid, tmp_path).read_text(encoding="utf-8")
        assert "Non risulta confermato" in testo

    def test_il_consenso_dato_non_viene_annotato(self, store: Store, session_id: int, tmp_path: Path) -> None:
        testo = esporta(store, session_id, tmp_path).read_text(encoding="utf-8")
        assert "Non risulta confermato" not in testo


class TestSchermate:
    def test_le_schermate_compaiono_nella_trascrizione(self, store: Store, tmp_path: Path) -> None:
        sid = store.create_session(1_785_000_000_000, titolo="Con schermate")
        store.add_segment(sid, "mic", 0, 1000, "guardate qui", is_final=True)
        store.add_segment(sid, "mic", 20_000, 21_000, "come dicevo", is_final=True)
        shot = store.add_screenshot(sid, 10_000, "C:/scatti/a.png", nota_utente="il grafico")
        store.set_screenshot_ocr(shot, "Budget residuo 10.000 EUR")

        testo = esporta(store, sid, tmp_path).read_text(encoding="utf-8")
        assert "## Schermate" in testo
        assert "Budget residuo 10.000 EUR" in testo
        assert "il grafico" in testo
        # Intercalata nel punto giusto: fra le due battute, non in fondo.
        righe = testo.splitlines()
        i_prima = next(i for i, r in enumerate(righe) if "guardate qui" in r)
        i_shot = next(i for i, r in enumerate(righe) if "schermata: a.png" in r)
        i_dopo = next(i for i, r in enumerate(righe) if "come dicevo" in r)
        assert i_prima < i_shot < i_dopo


class TestNomeFile:
    def test_il_nome_deriva_da_data_e_titolo(self, store: Store, session_id: int, tmp_path: Path) -> None:
        percorso = esporta(store, session_id, tmp_path)
        assert percorso.name.startswith("2026-")
        assert "revisione-portale-clienti" in percorso.name

    def test_i_caratteri_scomodi_spariscono(self, store: Store, tmp_path: Path) -> None:
        sid = store.create_session(1_785_000_000_000, titolo='Call: "urgente" / 50% <sconto>')
        nome = esporta(store, sid, tmp_path).name
        assert not set(nome) & set('<>:"/\\|?*')

    def test_un_titolo_solo_di_simboli_non_lascia_il_nome_vuoto(self, store: Store, tmp_path: Path) -> None:
        sid = store.create_session(1_785_000_000_000, titolo="???")
        assert esporta(store, sid, tmp_path).stem.endswith(f"call-{sid}")

    def test_si_puo_indicare_il_file_preciso(self, store: Store, session_id: int, tmp_path: Path) -> None:
        atteso = tmp_path / "mio-nome.md"
        assert esporta(store, session_id, atteso) == atteso
        assert atteso.exists()

    def test_una_sessione_inesistente_solleva(self, store: Store, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="inesistente"):
            esporta(store, 9999, tmp_path)
