"""Test della diarizzazione: chi ha parlato dentro «altri».

Tre cose deve garantire il brief, e sono i tre gruppi di test qui sotto:

- **il modello assente non rompe niente** — `disponibile()` non solleva mai, e
  senza pyannote/torch/token configurati (come in questo ambiente di test)
  `assegna()` fallisce in modo pulito, non con un'eccezione che risale;
- **l'assegnazione scrive `speaker_id` senza toccare `source`** — la colonna
  che dice da quale traccia è entrato il suono (il "speaker_raw" del brief)
  resta quella che era, per costruzione, per ogni segmento, mic compreso —
  e un segmento mic passato per errore in `assegnazioni` viene scartato;
- **il nome dato a una voce resta** — `rinomina_voce` scrive `nome_reale` e
  `confermato`, e si rilegge da `speakers()`.

Il quarto gruppo copre `assegna_etichette`, la logica di sovrapposizione
segmento/traccia diarizzata, e le rotte HTTP (`GET /diarizzazione/disponibile`,
l'avvio, l'elenco voci, la rinomina) con un modello finto — la pipeline vera
non gira nei test, per gli stessi motivi discussi in `stt/diarizzazione.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.api import Contesto  # noqa: E402
from scriba_core.api.diarizzazione import crea_router  # noqa: E402
from scriba_core.db.store import Store  # noqa: E402
from scriba_core.stt.diarizzazione import (  # noqa: E402
    Diarizzatore,
    DiarizzazioneNonDisponibile,
    assegna_etichette,
)


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "diarizzazione.sqlite")


@pytest.fixture()
def session_id(store: Store) -> int:
    return store.create_session(1_700_000_000_000, titolo="Call di prova")


# --------------------------------------------------------------------- modello assente


class TestModelloAssente:
    """Senza pyannote.audio/torch configurati (come in CI), non deve rompere nulla."""

    def test_disponibile_non_solleva_e_dice_falso(self) -> None:
        # Questo ambiente di test non ha un token Hugging Face configurato e
        # non ha i pesi di community-1 in cache: è esattamente lo scenario
        # "funzione non attivata" che il brief chiede di non far rompere.
        assert Diarizzatore().disponibile() is False

    def test_disponibile_falso_anche_se_le_librerie_non_ci_sono(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Si simula l'assenza delle librerie togliendole dai moduli importabili:
        # `disponibile()` importa `torch` e `huggingface_hub` dentro di sé, quindi
        # basta far fallire quell'import per esercitare lo stesso ramo di chi
        # non le ha mai installate.
        import builtins

        vero_import = builtins.__import__

        def import_che_rifiuta_torch(nome: str, *args: Any, **kwargs: Any) -> Any:
            if nome == "torch":
                raise ImportError("simulato: torch non installato")
            return vero_import(nome, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", import_che_rifiuta_torch)
        assert Diarizzatore().disponibile() is False

    def test_assegna_fallisce_pulito_invece_di_far_finta(
        self, store: Store, session_id: int
    ) -> None:
        with pytest.raises(DiarizzazioneNonDisponibile):
            Diarizzatore().assegna(session_id, store)

        # Il resto dell'applicazione non ne risente: la sessione è ancora
        # leggibile e "io"/"altri" ci sono sempre, com'erano prima del tentativo.
        assert store.get_session(session_id) is not None
        ruoli = {r["ruolo"] for r in store.speakers(session_id)}
        assert ruoli == {"me", "them"}

    def test_rotta_avvio_risponde_409_non_500(self, store: Store, tmp_path: Path) -> None:
        # Anche attraverso l'HTTP: un tentativo di avviare la diarizzazione
        # senza il modello configurato è un errore atteso (409), non un crash
        # del server (500) che farebbe sembrare rotta l'intera applicazione.
        session_id = store.create_session(0)
        client = _client(store, tmp_path)
        r = client.post(f"/sessions/{session_id}/diarizzazione")
        assert r.status_code == 409
        assert r.status_code != 500


# ------------------------------------------------------------- store: assegnazione


class TestApplicaDiarizzazione:
    """`store.applica_diarizzazione`: il cuore della scrittura, senza bisogno del modello vero."""

    def test_scrive_speaker_id_senza_toccare_source(
        self, store: Store, session_id: int
    ) -> None:
        mic = store.add_segment(session_id, "mic", 0, 1000, "dico io")
        loop_a = store.add_segment(session_id, "loopback", 1000, 2000, "dice Marco")
        loop_b = store.add_segment(session_id, "loopback", 2000, 3000, "dice Sofia")

        esito = store.applica_diarizzazione(
            session_id,
            {loop_a: "SPEAKER_00", loop_b: "SPEAKER_01"},
            quando_ms=1_700_000_100_000,
        )
        assert esito == {"voci": 2, "segmenti_assegnati": 2}

        segmenti = {s.id: s for s in store.segments(session_id)}
        # `source` — il "speaker_raw" del brief — è esattamente quello con cui
        # ogni segmento è nato: la diarizzazione non lo tocca mai.
        assert segmenti[mic].source == "mic"
        assert segmenti[loop_a].source == "loopback"
        assert segmenti[loop_b].source == "loopback"

        # speaker_id invece si è mosso, e le due voci diarizzate sono distinte.
        assert segmenti[loop_a].speaker_id != segmenti[loop_b].speaker_id
        assert segmenti[loop_a].speaker_label == "Voce 2"
        assert segmenti[loop_b].speaker_label == "Voce 3"
        # Il segmento mic non era nella mappa: resta sulla voce 'io' di sempre.
        assert segmenti[mic].speaker_label == "io"

    def test_un_segmento_mic_nella_mappa_viene_scartato(
        self, store: Store, session_id: int
    ) -> None:
        # Il microfono è per definizione una persona sola: anche se chi chiama
        # sbaglia e ce lo infila dentro, non deve mai finire assegnato a una
        # "voce" fra le altre.
        mic = store.add_segment(session_id, "mic", 0, 1000, "dico io")
        loop = store.add_segment(session_id, "loopback", 1000, 2000, "dice Marco")

        esito = store.applica_diarizzazione(
            session_id,
            {mic: "SPEAKER_00", loop: "SPEAKER_00"},
            quando_ms=1_700_000_100_000,
        )
        # Solo il segmento loopback è stato contato: quello mic è stato scartato.
        assert esito == {"voci": 1, "segmenti_assegnati": 1}

        segmenti = {s.id: s for s in store.segments(session_id)}
        assert segmenti[mic].speaker_label == "io"  # invariato
        assert segmenti[loop].speaker_label == "Voce 2"

    def test_stesso_cluster_stessa_voce(self, store: Store, session_id: int) -> None:
        a = store.add_segment(session_id, "loopback", 0, 1000, "a")
        b = store.add_segment(session_id, "loopback", 5000, 6000, "b")
        store.applica_diarizzazione(
            session_id, {a: "SPEAKER_00", b: "SPEAKER_00"}, quando_ms=1
        )
        segmenti = {s.id: s for s in store.segments(session_id)}
        assert segmenti[a].speaker_id == segmenti[b].speaker_id

    def test_numerazione_riparte_dopo_una_diarizzazione_precedente(
        self, store: Store, session_id: int
    ) -> None:
        # Rilanciare la diarizzazione (un altro tentativo, un audio più lungo)
        # non deve andare a sbattere sull'UNIQUE(session_id, label): si creano
        # voci nuove invece di riusare quelle già battezzate "Voce 2".
        a = store.add_segment(session_id, "loopback", 0, 1000, "a")
        store.applica_diarizzazione(session_id, {a: "SPEAKER_00"}, quando_ms=1)

        b = store.add_segment(session_id, "loopback", 2000, 3000, "b")
        esito = store.applica_diarizzazione(session_id, {b: "SPEAKER_00"}, quando_ms=2)
        assert esito["voci"] == 1

        etichette = {r["label"] for r in store.speakers(session_id)}
        assert etichette == {"io", "altri", "Voce 2", "Voce 3"}

    def test_voci_in_ordine_di_comparsa_nel_tempo(
        self, store: Store, session_id: int
    ) -> None:
        # I segmenti si passano fuori ordine: l'ordine che conta per "Voce 2"
        # contro "Voce 3" è quello temporale (t_start_ms), non quello di
        # inserimento nel dict.
        tardi = store.add_segment(session_id, "loopback", 9000, 9500, "dopo")
        presto = store.add_segment(session_id, "loopback", 100, 600, "prima")
        store.applica_diarizzazione(
            session_id,
            {tardi: "SPEAKER_B", presto: "SPEAKER_A"},
            quando_ms=1,
        )
        segmenti = {s.id: s for s in store.segments(session_id)}
        assert segmenti[presto].speaker_label == "Voce 2"
        assert segmenti[tardi].speaker_label == "Voce 3"

    def test_segna_la_sessione_come_diarizzata_anche_a_vuoto(
        self, store: Store, session_id: int
    ) -> None:
        # Una call senza nessuno sul loopback è comunque "diarizzata": lo
        # stato serve a chi costruisce /sessions/{id}/segments per sapere
        # quando smettere di mandare `speaker: null`.
        assert store.get_session(session_id)["diarizzata_at"] is None
        esito = store.applica_diarizzazione(session_id, {}, quando_ms=42)
        assert esito == {"voci": 0, "segmenti_assegnati": 0}
        assert store.get_session(session_id)["diarizzata_at"] == 42


# --------------------------------------------------------------------- rinominare


class TestRinominaVoce:
    def test_il_nome_dato_resta(self, store: Store, session_id: int) -> None:
        voce = next(r for r in store.speakers(session_id) if r["ruolo"] == "them")
        assert voce["nome_reale"] is None
        assert bool(voce["confermato"]) is False

        assert store.rinomina_voce(voce["id"], "Marco Rossi") is True

        rilette = {r["id"]: r for r in store.speakers(session_id)}
        assert rilette[voce["id"]]["nome_reale"] == "Marco Rossi"
        assert bool(rilette[voce["id"]]["confermato"]) is True

    def test_voce_inesistente_torna_falso_non_eccezione(self, store: Store) -> None:
        assert store.rinomina_voce(999_999, "Nessuno") is False

    def test_rinominare_di_nuovo_sovrascrive(self, store: Store, session_id: int) -> None:
        voce = next(r for r in store.speakers(session_id) if r["ruolo"] == "them")
        store.rinomina_voce(voce["id"], "Primo nome")
        store.rinomina_voce(voce["id"], "Nome corretto")
        rilette = {r["id"]: r for r in store.speakers(session_id)}
        assert rilette[voce["id"]]["nome_reale"] == "Nome corretto"

    def test_rotta_rinomina_e_rotta_elenco(self, store: Store, tmp_path: Path) -> None:
        session_id = store.create_session(0)
        loop = store.add_segment(session_id, "loopback", 0, 1000, "ciao")
        store.applica_diarizzazione(session_id, {loop: "SPEAKER_00"}, quando_ms=1)
        voce = next(r for r in store.speakers(session_id) if r["label"] == "Voce 2")

        client = _client(store, tmp_path)
        r = client.patch(
            f"/sessions/{session_id}/voci/{voce['id']}", json={"nome_reale": "Marco"}
        )
        assert r.status_code == 200
        assert r.json()["nome_reale"] == "Marco"

        r = client.get(f"/sessions/{session_id}/voci")
        assert r.status_code == 200
        etichette = {v["label"]: v["nome_reale"] for v in r.json()}
        assert etichette["Voce 2"] == "Marco"
        assert etichette["io"] is None

    def test_rotta_rinomina_voce_inesistente_e_404(
        self, store: Store, tmp_path: Path
    ) -> None:
        session_id = store.create_session(0)
        client = _client(store, tmp_path)
        r = client.patch(
            f"/sessions/{session_id}/voci/999999", json={"nome_reale": "Chiunque"}
        )
        assert r.status_code == 404

    def test_rotta_rinomina_nome_vuoto_e_400(self, store: Store, tmp_path: Path) -> None:
        session_id = store.create_session(0)
        voce = next(r for r in store.speakers(session_id) if r["ruolo"] == "them")
        client = _client(store, tmp_path)
        r = client.patch(
            f"/sessions/{session_id}/voci/{voce['id']}", json={"nome_reale": "   "}
        )
        assert r.status_code == 400


# ---------------------------------------------------------- assegna_etichette (puro)


class TestAssegnaEtichette:
    """La logica di sovrapposizione, sganciata dal modello vero."""

    def test_sceglie_la_traccia_con_piu_sovrapposizione(self) -> None:
        segmenti = [_seg(1, 1000, 3000)]
        tracce = [(0.0, 1.5, "A"), (1.5, 4.0, "B")]  # B copre 1.5s del segmento, A solo 0.5s
        assert assegna_etichette(tracce, segmenti) == {1: "B"}

    def test_nessuna_sovrapposizione_resta_senza_etichetta(self) -> None:
        segmenti = [_seg(1, 1000, 2000)]
        tracce = [(5.0, 6.0, "A")]
        assert assegna_etichette(tracce, segmenti) == {}

    def test_piu_segmenti_stesso_cluster(self) -> None:
        segmenti = [_seg(1, 0, 1000), _seg(2, 1000, 2000)]
        tracce = [(0.0, 2.0, "A")]
        assert assegna_etichette(tracce, segmenti) == {1: "A", 2: "A"}


# -------------------------------------------------------------------------- rotte


class TestRottaDisponibile:
    def test_get_disponibile(self, store: Store, tmp_path: Path) -> None:
        client = _client(store, tmp_path)
        r = client.get("/diarizzazione/disponibile")
        assert r.status_code == 200
        assert r.json() == {"disponibile": False}


class TestRottaAvvio:
    def test_sessione_inesistente_e_404(self, store: Store, tmp_path: Path) -> None:
        client = _client(store, tmp_path)
        r = client.post("/sessions/999999/diarizzazione")
        assert r.status_code == 404


# ------------------------------------------------------------------------- utilità


def _seg(id_: int, t_start_ms: int, t_end_ms: int) -> Any:
    from scriba_core.db.store import Segment

    return Segment(
        id=id_,
        session_id=1,
        source="loopback",
        t_start_ms=t_start_ms,
        t_end_ms=t_end_ms,
        testo="x",
        is_final=True,
        revision=0,
    )


def _client(store: Store, tmp_path: Path) -> TestClient:
    ctx = Contesto(
        store=store,
        settings=None,  # type: ignore[arg-type]  # queste rotte non leggono le impostazioni
        db_path=tmp_path / "db.sqlite",
        publish=lambda _payload: None,
        state={},
    )
    app = FastAPI()
    app.include_router(crea_router(ctx))
    return TestClient(app)
