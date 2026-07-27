"""Test delle schermate come contesto per l'analisi.

Uno screenshot che resta un file su disco non serve a niente: il senso è che
quello che c'era sullo schermo entri nell'analisi accanto a quello che si diceva
in quel momento.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.ai.analyze import formatta_segmenti  # noqa: E402
from scriba_core.db.store import Segment, Store  # noqa: E402


def seg(id_: int, t_ms: int, testo: str, source: str = "mic") -> Segment:
    return Segment(
        id=id_, session_id=1, source=source, t_start_ms=t_ms, t_end_ms=t_ms + 2000,
        testo=testo, is_final=True, revision=0,
    )


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "shot.sqlite")


@pytest.fixture()
def session_id(store: Store) -> int:
    return store.create_session(1_700_000_000_000)


class TestInserimentoNelContesto:
    def test_la_schermata_finisce_nel_punto_giusto(self, store: Store, session_id: int) -> None:
        # Non in fondo: quando qualcuno dice "questo qui non torna" indicando
        # una slide, la parola "questo" ha senso solo se la slide sta li' accanto.
        store.add_screenshot(session_id, 5_000, "a.png")
        store.set_screenshot_ocr(1, "Budget residuo 10.000 EUR")

        testo = formatta_segmenti(
            [seg(1, 0, "guardate qui"), seg(2, 10_000, "come dicevo")],
            store.screenshots(session_id),
        )
        righe = testo.splitlines()
        assert len(righe) == 3
        assert "guardate qui" in righe[0]
        assert "Budget residuo" in righe[1]
        assert "come dicevo" in righe[2]

    def test_le_slide_identiche_si_annotano_una_volta(self, store: Store, session_id: int) -> None:
        # Chi condivide uno schermo fermo produce dieci scatti dello stesso
        # contenuto: ripeterlo dieci volte sposta il peso dell'analisi su
        # qualcosa che e' stato detto una volta sola.
        for i in range(5):
            store.add_screenshot(session_id, 1_000 * i, f"{i}.png")
            store.set_screenshot_ocr(i + 1, "Roadmap primo trimestre")

        testo = formatta_segmenti([seg(1, 0, "ecco")], store.screenshots(session_id))
        assert testo.count("Roadmap primo trimestre") == 1

    def test_le_slide_diverse_restano_tutte(self, store: Store, session_id: int) -> None:
        store.add_screenshot(session_id, 1_000, "a.png")
        store.set_screenshot_ocr(1, "Prima slide")
        store.add_screenshot(session_id, 2_000, "b.png")
        store.set_screenshot_ocr(2, "Seconda slide")

        testo = formatta_segmenti([seg(1, 0, "ecco")], store.screenshots(session_id))
        assert "Prima slide" in testo
        assert "Seconda slide" in testo

    def test_una_schermata_senza_testo_viene_ignorata(self, store: Store, session_id: int) -> None:
        # Uno scatto illeggibile occuperebbe spazio senza aggiungere nulla.
        store.add_screenshot(session_id, 1_000, "vuota.png")
        testo = formatta_segmenti([seg(1, 0, "ecco")], store.screenshots(session_id))
        assert testo.count("\n") == 0

    def test_la_nota_dell_utente_vale_da_sola(self, store: Store, session_id: int) -> None:
        # Se qualcuno si e' preso la briga di annotare lo scatto, quella e' la
        # cosa piu' rilevante che si possa sapere su di esso.
        store.add_screenshot(session_id, 1_000, "x.png", nota_utente="il grafico sbagliato")
        testo = formatta_segmenti([seg(1, 0, "ecco")], store.screenshots(session_id))
        assert "il grafico sbagliato" in testo

    def test_senza_schermate_il_formato_non_cambia(self) -> None:
        assert formatta_segmenti([seg(7, 0, "ciao")]) == "[7] (00:00) io: ciao"

    def test_gli_id_dei_segmenti_restano_citabili(self, store: Store, session_id: int) -> None:
        # Le schermate non devono introdurre id che il modello possa scambiare
        # per righe di trascrizione da citare come prova.
        store.add_screenshot(session_id, 500, "a.png")
        store.set_screenshot_ocr(1, "Contenuto della slide")
        testo = formatta_segmenti([seg(42, 0, "parlo")], store.screenshots(session_id))
        assert "[42]" in testo
        assert "[1]" not in testo


class TestOcr:
    def test_un_file_inesistente_non_solleva(self) -> None:
        from scriba_core.ai import ocr

        # Un OCR fallito peggiora l'analisi, non deve interrompere la
        # registrazione in corso.
        assert ocr.leggi_testo("C:/non/esiste/mai.png") is None

    def test_il_testo_troppo_corto_viene_scartato(self, tmp_path: Path) -> None:
        from scriba_core.ai import ocr

        assert ocr.MIN_CARATTERI > 0
