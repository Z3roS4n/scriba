"""Test dello scaricamento dei modelli.

Sette gigabyte si interrompono, e un file troncato che sembra completo produce
errori incomprensibili al primo avvio. Qui si verifica che la ripresa riprenda
davvero e che un file corrotto non passi.
"""

from __future__ import annotations

import hashlib
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.models_manager import CATALOGO, ModelsManager  # noqa: E402


class FintaRisposta:
    def __init__(self, contenuto: bytes, *, status: int = 200, totale: int | None = None) -> None:
        self.contenuto = contenuto
        self.status_code = status
        self.headers = {"content-length": str(totale if totale is not None else len(contenuto))}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_bytes(self, size: int = 1024):
        for i in range(0, len(self.contenuto), size):
            yield self.contenuto[i : i + size]


@contextmanager
def finto_stream(risposta: FintaRisposta, registro: list[dict]):
    def stream(metodo, url, *, headers=None, **kwargs):
        registro.append({"url": url, "headers": headers or {}})

        @contextmanager
        def ctx():
            yield risposta

        return ctx()

    import scriba_core.models_manager as mm

    originale = mm.httpx.stream
    mm.httpx.stream = stream
    try:
        yield registro
    finally:
        mm.httpx.stream = originale


@pytest.fixture()
def manager(tmp_path: Path) -> ModelsManager:
    return ModelsManager(tmp_path / "models")


CONTENUTO = b"x" * 5000
SHA = hashlib.sha256(CONTENUTO).hexdigest()


class TestDownload:
    def test_scarica_e_verifica(self, manager: ModelsManager, tmp_path: Path) -> None:
        dest = tmp_path / "modello.gguf"
        with finto_stream(FintaRisposta(CONTENUTO), []):
            manager._scarica("http://esempio/x", dest, sha256=SHA)
        assert dest.read_bytes() == CONTENUTO
        # Il file provvisorio non deve restare in giro.
        assert not dest.with_suffix(".gguf.parziale").exists()

    def test_un_file_corrotto_non_passa(self, manager: ModelsManager, tmp_path: Path) -> None:
        dest = tmp_path / "modello.gguf"
        with finto_stream(FintaRisposta(b"contenuto sbagliato"), []):
            with pytest.raises(RuntimeError, match="non corrisponde"):
                manager._scarica("http://esempio/x", dest, sha256=SHA)
        # E non deve restare un mezzo file che al prossimo tentativo verrebbe
        # scambiato per un download da riprendere.
        assert not dest.exists()
        assert not dest.with_suffix(".gguf.parziale").exists()

    def test_riprende_da_dove_si_era_interrotto(
        self, manager: ModelsManager, tmp_path: Path
    ) -> None:
        dest = tmp_path / "modello.gguf"
        parziale = dest.with_suffix(".gguf.parziale")
        parziale.write_bytes(CONTENUTO[:2000])

        registro: list[dict] = []
        with finto_stream(FintaRisposta(CONTENUTO[2000:], status=206), registro):
            manager._scarica("http://esempio/x", dest, sha256=SHA)

        assert registro[0]["headers"].get("Range") == "bytes=2000-"
        assert dest.read_bytes() == CONTENUTO

    def test_se_il_server_ignora_la_ripresa_si_ricomincia(
        self, manager: ModelsManager, tmp_path: Path
    ) -> None:
        # Alcuni server rispondono 200 con il file intero anche a fronte di una
        # richiesta Range: accodare produrrebbe un file lungo il doppio.
        dest = tmp_path / "modello.gguf"
        dest.with_suffix(".gguf.parziale").write_bytes(CONTENUTO[:2000])

        with finto_stream(FintaRisposta(CONTENUTO, status=200), []):
            manager._scarica("http://esempio/x", dest, sha256=SHA)

        assert dest.read_bytes() == CONTENUTO

    def test_un_download_gia_completo(self, manager: ModelsManager, tmp_path: Path) -> None:
        # 416 significa "hai gia' tutto".
        dest = tmp_path / "modello.gguf"
        dest.with_suffix(".gguf.parziale").write_bytes(CONTENUTO)

        with finto_stream(FintaRisposta(b"", status=416), []):
            manager._scarica("http://esempio/x", dest, sha256=SHA)

        assert dest.read_bytes() == CONTENUTO

    def test_il_progresso_viene_riportato(self, manager: ModelsManager, tmp_path: Path) -> None:
        letture = []
        with finto_stream(FintaRisposta(CONTENUTO), []):
            manager._scarica(
                "http://esempio/x", tmp_path / "m.gguf", on_progress=letture.append
            )
        assert letture
        assert letture[-1].scaricati == len(CONTENUTO)
        assert letture[-1].percentuale == pytest.approx(100.0)


class TestCatalogo:
    def test_il_predefinito_esiste(self) -> None:
        assert any(m.id == "gemma-4-12b" for m in CATALOGO)

    def test_gli_identificativi_sono_unici(self) -> None:
        ids = [m.id for m in CATALOGO]
        assert len(ids) == len(set(ids))

    def test_ogni_modello_dichiara_quanto_pesa(self) -> None:
        # Serve a controllare lo spazio su disco prima di iniziare, e a dirlo
        # all'utente prima di fargli scaricare sette gigabyte.
        assert all(m.size_bytes > 0 for m in CATALOGO)

    def test_un_modello_sconosciuto_viene_rifiutato(self, manager: ModelsManager) -> None:
        with pytest.raises(ValueError, match="sconosciuto"):
            manager.installa_modello("modello-che-non-esiste")

    def test_lo_stato_elenca_ogni_modello_del_catalogo(self, manager: ModelsManager) -> None:
        elenco = manager.elenco_modelli()
        assert len(elenco) == len(CATALOGO)
        assert all(m["stato"] == "non_installato" for m in elenco)


class TestAvvio:
    def test_non_si_avvia_senza_modello(self, manager: ModelsManager) -> None:
        with pytest.raises(RuntimeError, match="non è installato"):
            manager.avvia_server("gemma-4-12b")
