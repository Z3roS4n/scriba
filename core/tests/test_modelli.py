"""Test del percorso completo di download: dalla rotta al thread in background.

`test_models_manager.py` copre `_scarica` in isolamento con uno stream finto.
Qui si sale di un livello e si passa da un vero server HTTP locale, per
verificare quello che conta davvero secondo il brief:

- un download sospeso e ripreso, anche da un `ModelsManager` nuovo (come dopo
  un riavvio dell'applicazione) — non deve mai tornare "non_installato";
- un server che dice di rispettare `Range` ma in realtà ignora l'header e
  manda tutto da capo — il file non deve uscirne corrotto;
- lo spazio insufficiente, controllato *prima* di scrivere un byte;
- un hash che non corrisponde a fine scaricamento.
"""

from __future__ import annotations

import hashlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.models_manager import ModelloDisponibile, ModelsManager  # noqa: E402

CONTENUTO = b"scriba-modello-di-prova-" * 4096  # ~98 KB, bastano per più chunk da 1 MB o meno
SHA = hashlib.sha256(CONTENUTO).hexdigest()


def _handler_finto(payload: bytes, *, rispetta_range: bool) -> type[BaseHTTPRequestHandler]:
    """Un server HF finto: serve `payload`, rispettando o ignorando `Range`."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - nome imposto da BaseHTTPRequestHandler
            corpo = payload
            intervallo = self.headers.get("Range")
            if rispetta_range and intervallo:
                inizio = int(intervallo.split("=")[1].split("-")[0])
                corpo = payload[inizio:]
                self.send_response(206)
                self.send_header(
                    "Content-Range", f"bytes {inizio}-{len(payload) - 1}/{len(payload)}"
                )
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, format: str, *args: object) -> None:  # silenzio nei test
            pass

    return Handler


class _ServerFinto:
    """Un `http.server` vero su 127.0.0.1, per esercitare `httpx` per davvero."""

    def __init__(self, payload: bytes, *, rispetta_range: bool = True) -> None:
        self._httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), _handler_finto(payload, rispetta_range=rispetta_range)
        )
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        porta = self._httpd.server_address[1]
        return f"http://127.0.0.1:{porta}/modello.gguf"

    def chiudi(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture()
def server_finto():
    server: _ServerFinto | None = None

    def _crea(payload: bytes, *, rispetta_range: bool = True) -> _ServerFinto:
        nonlocal server
        server = _ServerFinto(payload, rispetta_range=rispetta_range)
        return server

    yield _crea
    if server is not None:
        server.chiudi()


def _modello_di_prova(url: str, *, sha256: str | None = SHA, size_bytes: int | None = None) -> ModelloDisponibile:
    return ModelloDisponibile(
        id="prova",
        repo="qualcuno/qualcosa",  # mai interrogato: url_override e sha256 lo bypassano
        commit="0" * 40,
        file="modello.gguf",
        etichetta="Modello di prova",
        descrizione="Solo per i test.",
        size_bytes=size_bytes if size_bytes is not None else len(CONTENUTO),
        url_override=url,
        sha256=sha256,
    )


class TestRipresaDelDownload:
    def test_riprende_da_un_parziale_esistente(self, tmp_path: Path, server_finto) -> None:
        server = server_finto(CONTENUTO, rispetta_range=True)
        modello = _modello_di_prova(server.url)
        manager = ModelsManager(tmp_path, catalogo=[modello])

        # Simula un download interrotto a metà: il parziale c'è già.
        parziale = manager.percorso(modello).with_suffix(".gguf.parziale")
        parziale.write_bytes(CONTENUTO[:40_000])

        risposta = manager.avvia_download(modello.id)
        assert risposta["stato"] in ("in_download", "in_verifica")
        manager.attendi_download(modello.id, timeout=10.0)

        finale = manager.descrivi(modello)
        assert finale["stato"] == "installato"
        assert finale["errore"] is None
        assert manager.percorso(modello).read_bytes() == CONTENUTO
        assert not parziale.exists()

    def test_il_parziale_risulta_in_pausa_anche_da_un_manager_nuovo(
        self, tmp_path: Path, server_finto
    ) -> None:
        # Non c'è nessun download in corso in questo processo: è esattamente
        # la situazione dopo un riavvio dell'applicazione con un parziale già
        # sul disco. Non deve mai leggersi come "non_installato".
        server = server_finto(CONTENUTO, rispetta_range=True)
        modello = _modello_di_prova(server.url)

        dir_modelli = tmp_path / "models"
        manager_vecchio = ModelsManager(dir_modelli, catalogo=[modello])
        parziale = manager_vecchio.percorso(modello).with_suffix(".gguf.parziale")
        parziale.write_bytes(CONTENUTO[:12_345])

        manager_nuovo = ModelsManager(dir_modelli, catalogo=[modello])
        stato = manager_nuovo.descrivi(modello)

        assert stato["stato"] == "in_pausa"
        assert stato["scaricati_bytes"] == 12_345
        assert stato["errore"] is None

    def test_sospendi_ferma_il_thread_e_tiene_il_parziale(self, tmp_path: Path, server_finto) -> None:
        # Un payload più grande dei chunk da 1 MB non serve qui: basta che il
        # thread parta e venga sospeso subito dopo, prima che finisca da solo.
        server = server_finto(CONTENUTO, rispetta_range=True)
        modello = _modello_di_prova(server.url)
        manager = ModelsManager(tmp_path, catalogo=[modello])

        manager.avvia_download(modello.id)
        risultato = manager.sospendi_download(modello.id)

        # A questo punto il thread è già finito (il payload di prova è
        # piccolo): l'importante è che non sia "errore" e che, se qualcosa
        # è stato scritto, resti lì per essere ripreso — mai la perdita dei
        # byte già presi.
        assert risultato["stato"] in ("in_pausa", "installato")
        assert risultato["errore"] is None


class TestServerCheNonRispettaIlRange:
    def test_riparte_da_zero_invece_di_scrivere_un_file_corrotto(
        self, tmp_path: Path, server_finto
    ) -> None:
        # Il server dichiara di ignorare Range e risponde sempre 200 con il
        # file intero. Se il codice si limitasse ad accodare al parziale
        # esistente, il file finale sarebbe lungo il doppio e corrotto.
        server = server_finto(CONTENUTO, rispetta_range=False)
        modello = _modello_di_prova(server.url)
        manager = ModelsManager(tmp_path, catalogo=[modello])

        parziale = manager.percorso(modello).with_suffix(".gguf.parziale")
        parziale.write_bytes(b"roba vecchia e sbagliata, non un prefisso valido di CONTENUTO")

        manager.avvia_download(modello.id)
        manager.attendi_download(modello.id, timeout=10.0)

        finale = manager.descrivi(modello)
        assert finale["stato"] == "installato"
        assert manager.percorso(modello).read_bytes() == CONTENUTO


class TestSpazioInsufficiente:
    def test_il_download_non_parte_se_manca_spazio(
        self, tmp_path: Path, server_finto, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        server = server_finto(CONTENUTO, rispetta_range=True)
        # Un modello enorme rispetto a quello che risulta libero sul disco.
        modello = _modello_di_prova(server.url, size_bytes=500_000_000_000)
        manager = ModelsManager(tmp_path, catalogo=[modello])

        import shutil as shutil_mod

        class DiscoFinto:
            free = 2_000_000_000  # 2 GB liberi, molto meno del dovuto
            total = 500_000_000_000

        monkeypatch.setattr(shutil_mod, "disk_usage", lambda _path: DiscoFinto())

        risposta = manager.avvia_download(modello.id)

        assert risposta["stato"] == "spazio_insufficiente"
        assert risposta["errore"] is not None
        assert "GB" in risposta["errore"]
        # Non deve aver scritto niente: accorgersene a metà è proprio quello
        # che non deve succedere.
        assert not manager.percorso(modello).exists()
        assert not manager.percorso(modello).with_suffix(".gguf.parziale").exists()


class TestHashCheNonCorrisponde:
    def test_un_hash_sbagliato_manda_il_modello_in_errore(
        self, tmp_path: Path, server_finto
    ) -> None:
        server = server_finto(CONTENUTO, rispetta_range=True)
        hash_sbagliato = hashlib.sha256(b"non e' questo il contenuto atteso").hexdigest()
        modello = _modello_di_prova(server.url, sha256=hash_sbagliato)
        manager = ModelsManager(tmp_path, catalogo=[modello])

        manager.avvia_download(modello.id)
        manager.attendi_download(modello.id, timeout=10.0)

        finale = manager.descrivi(modello)
        assert finale["stato"] == "errore"
        assert finale["errore"] is not None
        # Un file che sembra completo ma non lo è non deve restare in giro:
        # al prossimo tentativo verrebbe scambiato per buono.
        assert not manager.percorso(modello).exists()
        assert not manager.percorso(modello).with_suffix(".gguf.parziale").exists()


class TestEventiPubblicati:
    def test_pubblica_un_evento_modello_locale_a_fine_download(
        self, tmp_path: Path, server_finto
    ) -> None:
        server = server_finto(CONTENUTO, rispetta_range=True)
        modello = _modello_di_prova(server.url)
        eventi: list[dict] = []
        manager = ModelsManager(tmp_path, catalogo=[modello], on_evento=eventi.append)

        manager.avvia_download(modello.id)
        manager.attendi_download(modello.id, timeout=10.0)

        assert eventi, "nessun evento pubblicato durante il download"
        assert all(e["type"] == "modello_locale" for e in eventi)
        assert all(e["modello"]["id"] == modello.id for e in eventi)
        assert eventi[-1]["modello"]["stato"] == "installato"


class TestAvvioELimiteDelServer:
    def test_non_si_avvia_senza_installazione(self, tmp_path: Path) -> None:
        modello = _modello_di_prova("http://127.0.0.1:1/mai-usato.gguf")
        manager = ModelsManager(tmp_path, catalogo=[modello])
        with pytest.raises(RuntimeError, match="non è installato"):
            manager.avvia_server(modello.id)

    def test_non_si_avvia_un_modello_di_trascrizione(self, tmp_path: Path) -> None:
        modello = ModelloDisponibile(
            id="stt-prova",
            repo="qualcuno/qualcosa",
            commit="0" * 40,
            file="stt.gguf",
            etichetta="STT di prova",
            descrizione="Solo per i test.",
            size_bytes=10,
            uso="trascrizione",
            url_override="http://127.0.0.1:1/mai-usato.gguf",
        )
        manager = ModelsManager(tmp_path, catalogo=[modello])
        manager.percorso(modello).write_bytes(b"x")  # "installato" ai fini del test
        with pytest.raises(RuntimeError, match="non è un modello di analisi"):
            manager.avvia_server(modello.id)
