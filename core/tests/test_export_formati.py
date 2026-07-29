"""Test dei formati di export mancanti (testo, JSON), della cartella/formato
delle impostazioni, e dei connettori Notion/HTTP generico.

`test_export_markdown.py` copre già il Markdown a fondo: qui si verifica
soprattutto quello che è nuovo — che gli altri due formati esistano davvero,
che la scelta salvata nelle impostazioni venga rispettata invece di essere
ignorata, e che rieseguire l'invio a Notion non duplichi la pagina della call
né le righe delle task.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.api import Contesto  # noqa: E402
from scriba_core.api.export import crea_router  # noqa: E402
from scriba_core.db.store import Store  # noqa: E402
from scriba_core.export import esporta  # noqa: E402
from scriba_core.export import http_generico, json_export, notion  # noqa: E402
from scriba_core.settings import Settings  # noqa: E402


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "p.sqlite")


@pytest.fixture()
def session_id(store: Store) -> int:
    sid = store.create_session(
        1_785_000_000_000,
        titolo="Revisione portale clienti",
        piattaforma="meet",
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
    tid = store.add_task(
        sid, "Preparare i mockup della dashboard",
        descrizione="Desktop e mobile",
        assignee_text="Marco", due_date="2026-08-14", due_raw="entro il quattordici",
        priorita="alta", confidence=0.85, needs_review=False,
        evidence=[{"segment_id": s1, "supports": "titolo"},
                  {"segment_id": s2, "supports": "due_date"}],
    )
    store.conn.execute("UPDATE tasks SET stato = 'confirmed' WHERE id = ?", (tid,))
    return sid


# --------------------------------------------------------------------- testo


class TestTesto:
    def test_contiene_la_trascrizione_coi_minuti(self, store: Store, session_id: int, tmp_path: Path) -> None:
        from scriba_core.export.testo import esporta as esporta_testo

        testo = esporta_testo(store, session_id, tmp_path).read_text(encoding="utf-8")
        assert "Revisione portale clienti" in testo
        assert "[05:00] Altri: dovremmo preparare i mockup della dashboard" in testo
        assert "[32:00] Io: diciamo entro il quattordici" in testo

    def test_niente_frivolezze_markdown(self, store: Store, session_id: int, tmp_path: Path) -> None:
        from scriba_core.export.testo import esporta as esporta_testo

        testo = esporta_testo(store, session_id, tmp_path).read_text(encoding="utf-8")
        # Il formato testo non è quello lossless: niente titoli/sezioni markdown.
        assert "##" not in testo
        assert testo.count(".txt") == 0

    def test_nome_file_ha_estensione_txt(self, store: Store, session_id: int, tmp_path: Path) -> None:
        from scriba_core.export.testo import esporta as esporta_testo

        percorso = esporta_testo(store, session_id, tmp_path)
        assert percorso.suffix == ".txt"

    def test_sessione_inesistente_solleva(self, store: Store, tmp_path: Path) -> None:
        from scriba_core.export.testo import esporta as esporta_testo

        with pytest.raises(ValueError, match="inesistente"):
            esporta_testo(store, 9999, tmp_path)


# ---------------------------------------------------------------------- json


class TestJson:
    def test_contiene_tutto_comprese_le_prove_per_campo(
        self, store: Store, session_id: int, tmp_path: Path
    ) -> None:
        percorso = json_export.esporta(store, session_id, tmp_path)
        assert percorso.suffix == ".json"
        dati = json.loads(percorso.read_text(encoding="utf-8"))

        assert dati["sessione"]["titolo"] == "Revisione portale clienti"
        assert dati["sessione"]["piattaforma"] == "meet"
        assert len(dati["segmenti"]) == 2
        assert "Mockup prima di sviluppare" in dati["riassunto_md"]
        assert "decisione presa" in dati["punti_salienti_md"]

        assert len(dati["task"]) == 1
        task = dati["task"][0]
        assert task["titolo"] == "Preparare i mockup della dashboard"
        assert task["assignee_text"] == "Marco"
        campi_provati = {e["supports"] for e in task["evidence"]}
        assert {"titolo", "due_date"} <= campi_provati
        for e in task["evidence"]:
            assert e["quote"]  # la citazione, non solo il campo che sostiene
            assert e["t_ms"] is not None

    def test_le_task_scartate_non_compaiono(self, store: Store, tmp_path: Path) -> None:
        sid = store.create_session(1_785_000_000_000, titolo="X")
        tid = store.add_task(sid, "Scartata")
        store.conn.execute("UPDATE tasks SET stato = 'rejected' WHERE id = ?", (tid,))
        dati = json.loads(json_export.esporta(store, sid, tmp_path).read_text(encoding="utf-8"))
        assert dati["task"] == []

    def test_costruisci_payload_e_esporta_concordano(self, store: Store, session_id: int, tmp_path: Path) -> None:
        # I connettori usano `costruisci_payload` direttamente: deve essere lo
        # stesso identico contenuto del file, non una versione ridotta.
        dal_payload = json_export.costruisci_payload(store, session_id)
        dal_file = json.loads(json_export.esporta(store, session_id, tmp_path).read_text(encoding="utf-8"))
        assert dal_payload == dal_file

    def test_sessione_inesistente_solleva(self, store: Store, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="inesistente"):
            json_export.esporta(store, 9999, tmp_path)


# ------------------------------------------------------------- dispatcher __init__


class TestDispatcher:
    def test_formato_sconosciuto_solleva(self, store: Store, session_id: int, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="sconosciuto"):
            esporta(session_id, store, formato="pdf", destinazione=tmp_path)

    def test_la_cartella_delle_impostazioni_viene_onorata(
        self, store: Store, session_id: int, tmp_path: Path
    ) -> None:
        # Prima di questo lavoro la rotta scriveva sempre in dati/export,
        # ignorando `export.cartella`: qui si verifica che non sia più così.
        cartella_scelta = tmp_path / "dove-dico-io"
        Settings(Path(store.path).with_name("settings.json")).aggiorna(
            {"export": {"cartella": str(cartella_scelta), "formato": "testo"}}
        )
        percorso = esporta(session_id, store)
        assert percorso.parent == cartella_scelta
        assert percorso.suffix == ".txt"  # anche il formato salvato viene onorato

    def test_senza_impostazioni_salvate_usa_markdown_accanto_al_db(
        self, store: Store, session_id: int, tmp_path: Path
    ) -> None:
        percorso = esporta(session_id, store)
        assert percorso.suffix == ".md"
        assert percorso.parent == Path(store.path).parent / "export"

    def test_formato_esplicito_prevale_su_quello_salvato(
        self, store: Store, session_id: int, tmp_path: Path
    ) -> None:
        Settings(Path(store.path).with_name("settings.json")).aggiorna({"export": {"formato": "json"}})
        percorso = esporta(session_id, store, formato="markdown", destinazione=tmp_path)
        assert percorso.suffix == ".md"


# ------------------------------------------------------------------- API router


@pytest.fixture()
def client(store: Store, tmp_path: Path) -> TestClient:
    ctx = Contesto(
        store=store,
        settings=Settings(tmp_path / "p.settings.json"),
        db_path=store.path,
        publish=lambda _evento: None,
        state={},
    )
    app = FastAPI()
    app.include_router(crea_router(ctx))
    return TestClient(app)


class TestRotta:
    def test_esporta_scrive_secondo_le_impostazioni_salvate(
        self, client: TestClient, store: Store, session_id: int, tmp_path: Path
    ) -> None:
        cartella = tmp_path / "cartella-utente"
        Settings(Path(store.path).with_name("settings.json")).aggiorna(
            {"export": {"cartella": str(cartella), "formato": "json"}}
        )
        r = client.post(f"/sessions/{session_id}/export", json={})
        assert r.status_code == 200
        percorso = Path(r.json()["percorso"])
        assert percorso.parent == cartella
        assert percorso.suffix == ".json"

    def test_una_sessione_inesistente_da_404(self, client: TestClient) -> None:
        r = client.post("/sessions/9999/export", json={})
        assert r.status_code == 404

    def test_stato_notion_di_default_non_collegato(self, client: TestClient) -> None:
        assert client.get("/export/notion/stato").json() == {"collegato": False, "database_id": None}

    def test_collega_e_scollega_notion(self, client: TestClient) -> None:
        r = client.post("/export/notion/collega", json={"token": "segreto", "database_id": "db1"})
        assert r.json() == {"collegato": True, "database_id": "db1"}
        # Il token non torna mai indietro verso l'interfaccia.
        assert "segreto" not in r.text

        r2 = client.get("/export/notion/stato")
        assert r2.json()["collegato"] is True

        r3 = client.post("/export/notion/scollega")
        assert r3.json() == {"collegato": False, "database_id": None}

    def test_un_token_vuoto_non_cancella_quello_salvato(self, client: TestClient, store: Store) -> None:
        # Stesso comportamento di llm.api_key in settings.py: l'interfaccia non
        # rimanda mai indietro il token, quindi un campo vuoto non lo cancella.
        client.post("/export/notion/collega", json={"token": "segreto", "database_id": "db1"})
        client.post("/export/notion/collega", json={"token": "", "database_id": "db2"})
        salvato = notion.leggi_config(store)
        assert salvato["token"] == "segreto"
        assert salvato["database_id"] == "db2"


# --------------------------------------------------------------- http generico


class TestHttpGenerico:
    def test_manda_lo_stesso_json_dell_export(
        self, store: Store, session_id: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ricevuto: dict[str, Any] = {}

        class FakeResp:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

        def fake_post(url, *, json=None, headers=None, timeout=None):
            ricevuto["url"] = url
            ricevuto["json"] = json
            ricevuto["headers"] = headers
            return FakeResp()

        monkeypatch.setattr(httpx, "post", fake_post)

        esito = http_generico.invia(session_id, store, {"url": "https://esempio.test/webhook", "token": "abc"})
        assert esito["url"] == "https://esempio.test/webhook"
        assert esito["creati"] == 1
        assert ricevuto["json"] == json_export.costruisci_payload(store, session_id)
        assert ricevuto["headers"]["Authorization"] == "Bearer abc"

    def test_senza_url_solleva(self, store: Store, session_id: int) -> None:
        with pytest.raises(http_generico.HttpGenericoError):
            http_generico.invia(session_id, store, {})


# --------------------------------------------------------------------- notion
#
# Un finto Notion in memoria: basta per verificare la logica (idempotenza,
# proprietà scelte in base allo schema) senza un vero account. Non è stato
# possibile verificare questo connettore contro l'API reale di Notion in
# questo giro: nessuna credenziale disponibile.


class _FakeResp:
    def __init__(self, status_code: int, corpo: dict[str, Any]) -> None:
        self.status_code = status_code
        self._corpo = corpo

    def json(self) -> dict[str, Any]:
        return self._corpo

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("errore finto", request=None, response=None)  # type: ignore[arg-type]


class FakeNotion:
    """Database e pagine in memoria, con lo stesso contratto REST di Notion
    per le sole operazioni che `notion.py` usa."""

    def __init__(self) -> None:
        self.databases = {
            "db1": {"properties": {"Nome": {"type": "title"}, "Fatto": {"type": "checkbox"}}}
        }
        self.pages: dict[str, dict[str, Any]] = {}
        self._contatore = 0

    def _nuovo_id(self, prefisso: str) -> str:
        self._contatore += 1
        return f"{prefisso}-{self._contatore}"

    def get(self, url: str, *, headers=None, params=None, timeout=None) -> _FakeResp:
        if "/databases/" in url:
            db_id = url.rsplit("/", 1)[-1]
            return _FakeResp(200, self.databases[db_id])
        if url.endswith("/children"):
            page_id = url.split("/blocks/")[1].split("/children")[0]
            figli = self.pages[page_id]["children"]
            return _FakeResp(200, {"results": [{"id": bid} for bid in figli], "has_more": False})
        raise AssertionError(f"GET non atteso: {url}")

    def post(self, url: str, *, headers=None, json=None, timeout=None) -> _FakeResp:
        if url.endswith("/pages"):
            pid = self._nuovo_id("pagina")
            figli = [self._nuovo_id("blocco") for _ in json.get("children", [])]
            self.pages[pid] = {"properties": json["properties"], "children": figli}
            return _FakeResp(200, {"id": pid})
        raise AssertionError(f"POST non atteso: {url}")

    def patch(self, url: str, *, headers=None, json=None, timeout=None) -> _FakeResp:
        if "/pages/" in url and not url.endswith("/children"):
            pid = url.rsplit("/", 1)[-1]
            if "properties" in json:
                self.pages[pid]["properties"].update(json["properties"])
            return _FakeResp(200, {"id": pid})
        if url.endswith("/children"):
            page_id = url.split("/blocks/")[1].split("/children")[0]
            nuovi = [self._nuovo_id("blocco") for _ in json.get("children", [])]
            self.pages[page_id]["children"].extend(nuovi)
            return _FakeResp(200, {})
        raise AssertionError(f"PATCH non atteso: {url}")

    def delete(self, url: str, *, headers=None, timeout=None) -> _FakeResp:
        bid = url.rsplit("/", 1)[-1]
        for pagina in self.pages.values():
            if bid in pagina["children"]:
                pagina["children"].remove(bid)
        return _FakeResp(200, {})


@pytest.fixture()
def notion_finto(monkeypatch: pytest.MonkeyPatch) -> FakeNotion:
    finto = FakeNotion()
    monkeypatch.setattr(httpx, "get", finto.get)
    monkeypatch.setattr(httpx, "post", finto.post)
    monkeypatch.setattr(httpx, "patch", finto.patch)
    monkeypatch.setattr(httpx, "delete", finto.delete)
    return finto


class TestNotion:
    def test_senza_token_o_database_solleva(self, store: Store, session_id: int) -> None:
        with pytest.raises(notion.NotionError):
            notion.invia(session_id, store, {})

    def test_due_invii_creano_una_sola_pagina_della_call(
        self, store: Store, session_id: int, notion_finto: FakeNotion
    ) -> None:
        config = {"token": "segreto", "database_id": "db1"}
        notion.invia(session_id, store, config)
        assert len(notion_finto.pages) == 2  # la pagina della call + 1 riga task

        notion.invia(session_id, store, config)
        # Rieseguire non deve aggiungere né la pagina della call né la riga
        # della task, che c'era già: duplicare le task di qualcuno è un danno
        # vero, non solo rumore nei dati.
        assert len(notion_finto.pages) == 2

    def test_le_task_confermate_diventano_righe_idempotenti(
        self, store: Store, session_id: int, notion_finto: FakeNotion
    ) -> None:
        config = {"token": "segreto", "database_id": "db1"}
        esito1 = notion.invia(session_id, store, config)
        assert esito1["creati"] == 1
        assert esito1["aggiornati"] == 0

        riga = store.conn.execute("SELECT export_ref, export_status FROM tasks").fetchone()
        assert riga["export_status"] == "synced"
        assert riga["export_ref"] is not None

        esito2 = notion.invia(session_id, store, config)
        assert esito2["creati"] == 0
        assert esito2["aggiornati"] == 1

    def test_una_nuova_task_confermata_produce_una_riga_in_piu(
        self, store: Store, session_id: int, notion_finto: FakeNotion
    ) -> None:
        config = {"token": "segreto", "database_id": "db1"}
        notion.invia(session_id, store, config)
        assert len(notion_finto.pages) == 2

        tid = store.add_task(store.conn.execute("SELECT session_id FROM tasks LIMIT 1").fetchone()[0], "Seconda task")
        store.conn.execute("UPDATE tasks SET stato = 'confirmed' WHERE id = ?", (tid,))

        notion.invia(session_id, store, config)
        assert len(notion_finto.pages) == 3  # la pagina della call + 2 righe task

    def test_il_token_salvato_si_usa_senza_ripassarlo(
        self, store: Store, session_id: int, notion_finto: FakeNotion
    ) -> None:
        notion.collega(store, token="segreto", database_id="db1")
        esito = notion.invia(session_id, store, {})
        assert esito["creati"] == 1

    def test_configurazione_rovinata_non_impedisce_di_ricollegare(self, store: Store) -> None:
        percorso = notion._percorso_stato(store)
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_text("{ non e' json", encoding="utf-8")
        assert notion.stato(store) == {"collegato": False, "database_id": None}
