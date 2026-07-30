"""Test dello scaricamento dei modelli.

Sette gigabyte si interrompono, e un file troncato che sembra completo produce
errori incomprensibili al primo avvio. Qui si verifica che la ripresa riprenda
davvero e che un file corrotto non passi.
"""

from __future__ import annotations

import hashlib
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.models_manager import CATALOGO, ModelloDisponibile, ModelsManager  # noqa: E402


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

    def test_lo_stato_elenca_ogni_modello_del_catalogo(
        self, manager: ModelsManager, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Il catalogo vero include Parakeet, il cui stato "installato" si legge
        # dalla cache reale di Hugging Face (vedi TestModelloGestito) e non da
        # `tmp_path`: senza isolarla, questo test dipende da cosa c'è già
        # scaricato sulla macchina di chi lo esegue, che è esattamente il tipo
        # di test fragile che va evitato.
        import scriba_core.models_manager as mm

        monkeypatch.setattr(mm, "_cache_hf", lambda: [])

        elenco = manager.elenco_modelli()
        assert len(elenco) == len(CATALOGO)
        assert all(m["stato"] == "non_installato" for m in elenco)


class TestAvvio:
    def test_non_si_avvia_senza_modello(self, manager: ModelsManager) -> None:
        with pytest.raises(RuntimeError, match="non è installato"):
            manager.avvia_server("gemma-4-12b")


class TestAvvioNonIstantaneo:
    """Il processo è vivo molto prima che il server risponda.

    Caricare un GGUF da 7-9 GB richiede decine di secondi. Chiamare «in uso» un
    modello che non risponde ancora lasciava l'interfaccia a dire «non
    disponibile» del motore appena avviato, senza modo di distinguerlo da uno
    rotto — è la issue #1.
    """

    @staticmethod
    def _installa(manager: ModelsManager) -> ModelloDisponibile:
        modello = next(m for m in manager.catalogo if m.uso == "analisi")
        manager.percorso(modello).write_bytes(b"finto gguf")
        (manager.dir_bin).mkdir(parents=True, exist_ok=True)
        manager.server_exe.write_bytes(b"finto llama-server")
        return modello

    @staticmethod
    def _finto_processo(monkeypatch, vivo: bool = True) -> None:
        class FintoPopen:
            pid = 4242

            def __init__(self, *a, **k) -> None:
                pass

            def poll(self):
                return None if vivo else 0

        import scriba_core.models_manager as mm

        monkeypatch.setattr(mm.subprocess, "Popen", FintoPopen)
        monkeypatch.setattr(mm, "_lega_al_processo_padre", lambda _p: None)

    def test_finche_non_risponde_e_in_avvio(self, manager: ModelsManager, monkeypatch) -> None:
        modello = self._installa(manager)
        self._finto_processo(monkeypatch)
        monkeypatch.setattr(ModelsManager, "server_attivo", lambda self, porta=8080: False)

        esito = manager.avvia_server(modello.id)
        assert esito["stato"] == "in_avvio"
        # L'endpoint non si dà prima che risponda: sarebbe un indirizzo che
        # rifiuta le connessioni, e chi lo riceve non ha modo di saperlo.
        assert esito["endpoint"] is None
        assert manager.server_in_avvio() is True

    def test_quando_risponde_diventa_in_uso_e_lo_dice(
        self, manager: ModelsManager, monkeypatch
    ) -> None:
        eventi: list[dict] = []
        manager._on_evento = eventi.append
        modello = self._installa(manager)
        self._finto_processo(monkeypatch)

        risposte = iter([False, False, True])
        monkeypatch.setattr(
            ModelsManager, "server_attivo", lambda self, porta=8080: next(risposte, True)
        )

        manager.avvia_server(modello.id)
        # Si aspetta la sorveglianza invece di dormire a caso: il thread è
        # quello che decide quando il modello è davvero utilizzabile.
        for _ in range(100):
            if manager.descrivi(modello)["stato"] == "in_uso":
                break
            time.sleep(0.05)

        descritto = manager.descrivi(modello)
        assert descritto["stato"] == "in_uso"
        assert descritto["endpoint"] == "http://127.0.0.1:8080"
        assert manager.server_in_avvio() is False
        # Due eventi: «sto partendo» e «adesso rispondo». Senza il secondo
        # l'interfaccia resta ferma a quello che sapeva al momento del clic.
        assert len(eventi) >= 2
        assert eventi[0]["modello"]["stato"] == "in_avvio"
        assert eventi[-1]["modello"]["stato"] == "in_uso"

    def test_fermarlo_lo_riporta_installato(self, manager: ModelsManager, monkeypatch) -> None:
        modello = self._installa(manager)
        self._finto_processo(monkeypatch)
        monkeypatch.setattr(ModelsManager, "server_attivo", lambda self, porta=8080: True)
        manager.avvia_server(modello.id)

        class FintoPopenFermabile:
            def terminate(self):
                pass

            def wait(self, timeout=None):
                return 0

        manager._server = FintoPopenFermabile()  # type: ignore[assignment]
        manager.ferma_server()
        assert manager.server_in_avvio() is False
        assert manager.descrivi(modello)["stato"] == "installato"


class TestModelloGestito:
    """Parakeet non passa da `_scarica`: è `onnx-asr` (via huggingface_hub) a
    scaricarlo e tenerlo in cache per conto suo. Qui si simula quella cache —
    non è nostra da scrivere per davvero in un test, il suo formato è interno
    a huggingface_hub — per verificare il contratto che conta: lo stato viene
    da lì, non da un flag; lo spazio si controlla prima; niente sospensione
    finta; l'eliminazione del motore di trascrizione viene rifiutata.
    """

    @staticmethod
    def _modello_gestito(
        *, size_bytes: int = 1000, scaricatore=None
    ) -> ModelloDisponibile:
        return ModelloDisponibile(
            id="stt-gestito",
            repo="qualcuno/modello-gestito",
            commit="",
            file="",
            etichetta="Modello gestito di prova",
            descrizione="Solo per i test.",
            size_bytes=size_bytes,
            uso="trascrizione",
            scaricatore=scaricatore or (lambda: None),
        )

    def test_parakeet_e_nel_catalogo_come_trascrizione_gestita(self) -> None:
        parakeet = next(m for m in CATALOGO if m.id == "parakeet-tdt-0.6b-v3")
        assert parakeet.uso == "trascrizione"
        assert parakeet.scaricatore is not None

    def test_risulta_installato_se_gia_nella_cache_hf(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Non un flag nostro: se la cache dice che c'è già, deve risultare
        # installato anche se nessuno lo ha "scaricato" da qui dentro — è
        # esattamente il caso di Parakeet, in uso da mesi prima di questo
        # catalogo.
        modello = self._modello_gestito(size_bytes=999)
        manager = ModelsManager(tmp_path, catalogo=[modello])

        import scriba_core.models_manager as mm

        monkeypatch.setattr(mm, "_cache_hf", lambda: [(modello.repo, 12_345, 1_700_000_000.0)])

        stato = manager.descrivi(modello)
        assert stato["stato"] == "installato"
        assert stato["size_bytes"] == 12_345  # la dimensione vera, non la stima nel catalogo
        assert stato["installato_at"] == 1_700_000_000_000
        assert manager.installato(modello) is True

    def test_non_installato_se_assente_dalla_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        modello = self._modello_gestito()
        manager = ModelsManager(tmp_path, catalogo=[modello])

        import scriba_core.models_manager as mm

        monkeypatch.setattr(mm, "_cache_hf", lambda: [])

        stato = manager.descrivi(modello)
        assert stato["stato"] == "non_installato"
        assert stato["size_bytes"] == modello.size_bytes  # solo la stima, non avendone una vera
        assert manager.installato(modello) is False

    def test_il_download_chiama_lo_scaricatore_e_poi_risulta_installato(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chiamato: list[bool] = []
        cache: list[tuple[str, int, float]] = []

        def scaricatore() -> None:
            chiamato.append(True)
            cache.append(("qualcuno/modello-gestito", 999, 1_700_000_000.0))

        modello = self._modello_gestito(scaricatore=scaricatore)
        manager = ModelsManager(tmp_path, catalogo=[modello])

        import scriba_core.models_manager as mm

        monkeypatch.setattr(mm, "_cache_hf", lambda: cache)
        monkeypatch.setattr(mm, "_cartella_cache_hf", lambda: tmp_path)

        risposta = manager.avvia_download(modello.id)
        # Mentre lavora non deve mai dirsi "in_download": in interfaccia quello
        # stato mostra il bottone "Sospendi", che qui non funzionerebbe.
        assert risposta["stato"] != "in_download"

        manager.attendi_download(modello.id, timeout=5.0)
        assert chiamato == [True]

        finale = manager.descrivi(modello)
        assert finale["stato"] == "installato"
        assert finale["errore"] is None

    def test_un_errore_dello_scaricatore_va_in_stato_errore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def scaricatore() -> None:
            raise RuntimeError("la libreria non ha trovato il modello")

        modello = self._modello_gestito(scaricatore=scaricatore)
        manager = ModelsManager(tmp_path, catalogo=[modello])

        import scriba_core.models_manager as mm

        monkeypatch.setattr(mm, "_cache_hf", lambda: [])
        monkeypatch.setattr(mm, "_cartella_cache_hf", lambda: tmp_path)

        manager.avvia_download(modello.id)
        manager.attendi_download(modello.id, timeout=5.0)

        finale = manager.descrivi(modello)
        assert finale["stato"] == "errore"
        assert finale["errore"] is not None
        assert "non ha trovato" in finale["errore"]

    def test_lo_spazio_si_controlla_prima_di_avviare_lo_scaricatore(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chiamato: list[bool] = []
        modello = self._modello_gestito(
            size_bytes=500_000_000_000, scaricatore=lambda: chiamato.append(True)
        )
        manager = ModelsManager(tmp_path, catalogo=[modello])

        import scriba_core.models_manager as mm

        monkeypatch.setattr(mm, "_cache_hf", lambda: [])
        monkeypatch.setattr(mm.shutil, "disk_usage", lambda _path: _DiscoQuasiPieno())

        risposta = manager.avvia_download(modello.id)

        assert risposta["stato"] == "spazio_insufficiente"
        assert risposta["errore"] is not None
        assert "GB" in risposta["errore"]
        assert chiamato == []  # non deve nemmeno aver provato a scaricare

    def test_sospendi_e_un_no_op_innocuo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        modello = self._modello_gestito()
        manager = ModelsManager(tmp_path, catalogo=[modello])

        import scriba_core.models_manager as mm

        monkeypatch.setattr(mm, "_cache_hf", lambda: [])

        # Non deve sollevare né restare bloccato: l'interfaccia non mostra mai
        # il bottone "Sospendi" per questi modelli, ma se la richiesta arriva
        # comunque (client diverso, stato UI stantio) deve restare innocua.
        risultato = manager.sospendi_download(modello.id)
        assert risultato["errore"] is None

    def test_eliminare_il_modello_di_trascrizione_viene_rifiutato(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        modello = self._modello_gestito()
        manager = ModelsManager(tmp_path, catalogo=[modello])

        import scriba_core.models_manager as mm

        monkeypatch.setattr(mm, "_cache_hf", lambda: [(modello.repo, 999, 1_700_000_000.0)])

        with pytest.raises(RuntimeError, match="trascrizione"):
            manager.elimina_modello(modello.id)


class _DiscoQuasiPieno:
    free = 2_000_000_000  # 2 GB liberi, molto meno del dovuto per un modello enorme
    total = 500_000_000_000
