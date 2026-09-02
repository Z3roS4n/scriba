"""Test delle rotte delle tre ricerche, viste dall'interfaccia.

`test_semantica.py` e `test_ricerca_contestuale.py` coprono la logica; qui si
verifica quello che la logica da sola non dice: che i filtri dell'archivio
valgano anche per le altre due modalità, che una call trovata torni nella
stessa forma in cui la manda `/archivio`, e che «manca il modello» arrivi come
errore invece che come elenco vuoto.

Il modello vero non si carica mai: al suo posto si mette lo stesso
`EmbedderLessicale` dei test della logica, infilato nello stato del server —
che è esattamente il punto in cui il codice vero lo tiene in cache.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.llm.base import Completion  # noqa: E402
from scriba_core.server import create_app  # noqa: E402
from test_semantica import EmbedderLessicale  # noqa: E402

TOKEN = "token-di-prova"
QUANDO = 1_785_000_000_000
GIORNO = 86_400_000


class ModelloFinto:
    name = "finto"
    model = "finto-1"
    risposta: dict = {}

    def available(self) -> bool:
        return True

    def complete(self, *, system, user, schema=None, max_tokens=2048, temperature=0.2):
        return Completion(text="", data=self.risposta, model=self.model, provider=self.name)


@pytest.fixture()
def client(tmp_path: Path):
    app = create_app(db_path=tmp_path / "r.sqlite", token=TOKEN, engine_factory=lambda: None)
    with TestClient(app) as c:
        # Il modello finto entra dove il codice vero mette quello vero: così si
        # esercita anche la cache, invece di scavalcarla.
        c.app.state.stato_server["embedder"] = EmbedderLessicale()
        yield c


def auth(path: str) -> str:
    return f"{path}{'&' if '?' in path else '?'}token={TOKEN}"


def call_con(client: TestClient, titolo: str, battute: list[str], **extra) -> int:
    store = client.app.state.store
    sid = store.create_session(extra.get("quando", QUANDO), titolo=titolo)
    for i, battuta in enumerate(battute):
        store.add_segment(sid, "mic", i * 2000, i * 2000 + 2000, battuta, is_final=True)
    if extra.get("client_id"):
        store.assegna_cliente(sid, extra["client_id"])
    return sid


def indicizza(client: TestClient) -> dict:
    """Avvia l'indicizzazione e aspetta che finisca.

    L'attesa serve: la rotta fa partire un task e torna subito, perché su un
    archivio vero il lavoro dura minuti e nessuna richiesta HTTP può restare
    appesa tanto. Chi usa l'applicazione lo scopre dagli eventi; qui si
    interroga lo stato finché non è fermo.
    """
    r = client.post(auth("/ricerca/indicizza"), json={})
    assert r.status_code == 200, r.text
    for _ in range(100):
        stato = client.get(auth("/ricerca/stato")).json()
        if not stato["in_corso"] and stato["call_indicizzate"] == stato["call_con_parlato"]:
            return stato
    raise AssertionError(f"l'indicizzazione non è finita: {stato}")


class TestStatoDellIndice:
    def test_dice_quante_call_mancano_prima_di_averne_indicizzata_una(
        self, client: TestClient
    ) -> None:
        call_con(client, "Una", ["si parla del prezzo"])
        stato = client.get(auth("/ricerca/stato")).json()
        assert stato["call_con_parlato"] == 1
        assert stato["call_indicizzate"] == 0

    def test_dopo_l_indicizzazione_il_conto_torna(self, client: TestClient) -> None:
        call_con(client, "Una", ["si parla del prezzo e della tariffa"])
        stato = indicizza(client)
        assert stato["call_indicizzate"] == 1
        assert stato["passaggi"] >= 1
        assert stato["in_corso"] is False

    def test_dimenticare_l_indice_riporta_tutto_da_fare(self, client: TestClient) -> None:
        call_con(client, "Una", ["prezzo tariffa"])
        indicizza(client)
        assert client.post(auth("/ricerca/dimentica"), json={}).json()["call"] == 1
        assert client.get(auth("/ricerca/stato")).json()["call_indicizzate"] == 0

    def test_non_si_indicizza_mentre_si_registra(self, client: TestClient) -> None:
        # Prendersi metà dei core per qualche minuto mentre la trascrizione
        # dal vivo sta lavorando è un rischio che può aspettare la fine.
        call_con(client, "Una", ["prezzo"])
        client.app.state.stato_server["recorder"] = object()
        r = client.post(auth("/ricerca/indicizza"), json={})
        assert r.status_code == 409
        client.app.state.stato_server["recorder"] = None


class TestIndiceAutomatico:
    """Una call nuova entra nell'indice da sola, ma solo se l'indice c'è già.

    La condizione non è pignoleria: senza, la prima riunione dopo
    l'aggiornamento caricherebbe mezzo gigabyte di pesi per una funzione che
    nessuno ha chiesto. Indicizzare una volta è il gesto con cui la si chiede.
    """

    @staticmethod
    async def _fine_call(client: TestClient, session_id: int) -> None:
        await client.app.state.stato_server["indicizza_call"](session_id)

    def test_una_call_nuova_entra_da_sola(self, client: TestClient) -> None:
        call_con(client, "Vecchia", ["prezzo tariffa"])
        indicizza(client)

        nuova = call_con(client, "Appena finita", ["si parla di consegne"])
        assert client.get(auth("/ricerca/stato")).json()["call_indicizzate"] == 1
        _esegui(self._fine_call(client, nuova))
        assert client.get(auth("/ricerca/stato")).json()["call_indicizzate"] == 2

    def test_senza_indice_non_si_carica_niente(self, client: TestClient) -> None:
        # Nessuno ha mai indicizzato: la call resta fuori, e la barra
        # dell'archivio lo dirà. È l'unico modo perché mezzo giga di modello
        # non si carichi alle spalle di chi non lo ha chiesto.
        nuova = call_con(client, "Appena finita", ["si parla di consegne"])
        _esegui(self._fine_call(client, nuova))
        assert client.get(auth("/ricerca/stato")).json()["call_indicizzate"] == 0


def _esegui(coroutine) -> None:
    """Esegue una coroutine del server da un test sincrono."""
    import asyncio

    asyncio.run(coroutine)


class TestRicercaSemantica:
    def test_trova_la_call_che_parla_dell_argomento(self, client: TestClient) -> None:
        prezzi = call_con(client, "Prezzi", ["la tariffa oraria va rivista in aumento"])
        call_con(client, "Altro", ["parliamo di cartoline e francobolli"])
        indicizza(client)

        r = client.post(auth("/ricerca/semantica"), json={"testo": "tariffa aumento"})
        assert r.status_code == 200, r.text
        call = r.json()["call"]
        assert [c["id"] for c in call] == [prezzi]
        assert "tariffa oraria" in call[0]["frammento"]

        # Nella stessa forma dell'archivio, campo per campo: chi cambia
        # modalità deve ritrovare la stessa schermata, non impararne una nuova.
        # Confrontata con quella vera invece che con una scritta qui, così se
        # l'archivio cambia forma questo test se ne accorge.
        dall_archivio = next(
            c for c in client.get(auth("/archivio")).json() if c["id"] == prezzi
        )
        aggiunte = {"frammento", "quando_ms"}
        assert {k: v for k, v in call[0].items() if k not in aggiunte} == {
            k: v for k, v in dall_archivio.items() if k not in aggiunte
        }

    def test_i_filtri_dell_archivio_valgono_anche_qui(self, client: TestClient) -> None:
        store = client.app.state.store
        cliente = store.crea_cliente("Rossi")
        suo = call_con(client, "Suo", ["prezzo tariffa"], client_id=cliente)
        call_con(client, "Di un altro", ["prezzo tariffa"])
        indicizza(client)

        r = client.post(
            auth("/ricerca/semantica"), json={"testo": "prezzo tariffa", "client_id": cliente}
        )
        assert [c["id"] for c in r.json()["call"]] == [suo]

    def test_una_call_compare_una_volta_sola(self, client: TestClient) -> None:
        # Una conversazione lunga produce molti passaggi vicini alla domanda:
        # mostrarla una volta per passaggio riempirebbe l'elenco di righe
        # uguali con dentro pezzi diversi della stessa call.
        call_con(client, "Fiume", [f"prezzo tariffa numero {i} " * 30 for i in range(10)])
        indicizza(client)
        call = client.post(auth("/ricerca/semantica"), json={"testo": "prezzo tariffa"}).json()["call"]
        assert len(call) == len({c["id"] for c in call}) == 1

    def test_senza_indice_lo_dice_invece_di_rispondere_vuoto(self, client: TestClient) -> None:
        call_con(client, "Mai indicizzata", ["prezzo tariffa"])
        fuori = client.post(auth("/ricerca/semantica"), json={"testo": "prezzo"}).json()
        assert fuori["call"] == []
        # Il conto è la differenza fra «non c'è» e «non l'ho ancora letta».
        assert fuori["da_indicizzare"] == 1

    def test_uno_stato_inventato_e_un_errore(self, client: TestClient) -> None:
        r = client.post(auth("/ricerca/semantica"), json={"testo": "x", "stato": "boh"})
        assert r.status_code == 400


@pytest.fixture()
def finto(monkeypatch) -> ModelloFinto:
    """Il modello di linguaggio, sostituito per tutta la durata del test.

    Come fixture e non dentro ogni test: `costruisci` è una funzione di modulo
    e rimetterla a posto a mano, in sei test, è una cosa che prima o poi si
    dimentica — e un modello finto lasciato acceso fa passare per verdi i test
    di qualcun altro.
    """
    import scriba_core.llm.providers as providers

    modello = ModelloFinto()
    monkeypatch.setattr(providers, "costruisci", lambda conf: modello)
    return modello


class TestRicercaContestuale:
    def test_risponde_citando_le_call(self, client: TestClient, finto: ModelloFinto) -> None:
        sid = call_con(client, "Consegne", ["la consegna slitta a inizio maggio"])
        indicizza(client)
        finto.risposta = {
            "risposta": "Inizio maggio.",
            "call": [{"session_id": sid, "perche": "lo dice qui", "passaggi": [1]}],
        }

        r = client.post(auth("/ricerca/contestuale"), json={"domanda": "consegna"})
        assert r.status_code == 200, r.text
        fuori = r.json()
        assert fuori["risposta"] == "Inizio maggio."
        assert [c["id"] for c in fuori["call"]] == [sid]
        assert fuori["call"][0]["perche"] == "lo dice qui"
        assert fuori["call"][0]["passaggi"][0]["testo"] == "la consegna slitta a inizio maggio"

    def test_le_catene_arrivano_all_interfaccia_con_i_titoli(
        self, client: TestClient, finto: ModelloFinto
    ) -> None:
        # Se la risposta viene da tre call e se ne mostra una, si e' appena
        # costruito un modo silenzioso di attribuire a una call quello che e'
        # stato detto in un'altra (#106).
        store = client.app.state.store
        cliente = store.crea_cliente("Rossi")
        prima = call_con(client, "Marzo", ["consegna prezzo aprile"], client_id=cliente)
        dopo = call_con(
            client,
            "Aprile",
            ["consegna prezzo maggio"],
            client_id=cliente,
            quando=QUANDO + 10 * GIORNO,
        )
        indicizza(client)
        finto.risposta = {
            "risposta": "Maggio.",
            "call": [{"session_id": dopo, "perche": "la piu' recente", "passaggi": []}],
        }

        fuori = client.post(
            auth("/ricerca/contestuale"), json={"domanda": "consegna prezzo"}
        ).json()
        # Coppie id/titolo e non due elenchi affiancati: affiancati si
        # disallineano al primo elemento che manca da uno dei due, e una
        # catena con i titoli sfalsati non si distingue da una giusta.
        assert fuori["catene"] == [
            {"call": [{"id": prima, "titolo": "Marzo"}, {"id": dopo, "titolo": "Aprile"}]}
        ]

    def test_si_puo_chiedere_di_non_unirle(
        self, client: TestClient, finto: ModelloFinto
    ) -> None:
        store = client.app.state.store
        cliente = store.crea_cliente("Rossi")
        call_con(client, "Marzo", ["consegna prezzo aprile"], client_id=cliente)
        dopo = call_con(
            client,
            "Aprile",
            ["consegna prezzo maggio"],
            client_id=cliente,
            quando=QUANDO + 10 * GIORNO,
        )
        indicizza(client)
        finto.risposta = {
            "risposta": "x",
            "call": [{"session_id": dopo, "perche": "", "passaggi": []}],
        }

        fuori = client.post(
            auth("/ricerca/contestuale"),
            json={"domanda": "consegna prezzo", "unisci_catene": False},
        ).json()
        assert fuori["catene"] == []

    def test_senza_indice_e_un_errore_non_una_risposta_vuota(
        self, client: TestClient, finto: ModelloFinto
    ) -> None:
        call_con(client, "Mai indicizzata", ["consegna prezzo"])
        finto.risposta = {"risposta": "", "call": []}
        r = client.post(auth("/ricerca/contestuale"), json={"domanda": "consegna"})
        assert r.status_code == 412

    def test_una_domanda_vuota_e_un_errore(
        self, client: TestClient, finto: ModelloFinto
    ) -> None:
        finto.risposta = {"risposta": "", "call": []}
        r = client.post(auth("/ricerca/contestuale"), json={"domanda": "   "})
        assert r.status_code == 400

    def test_una_call_fuori_dai_filtri_non_rientra_dalla_risposta(
        self, client: TestClient, finto: ModelloFinto
    ) -> None:
        # Il modello riceve solo le call filtrate, ma se ne citasse una fuori
        # elenco l'interfaccia mostrerebbe qualcosa che l'utente aveva escluso.
        store = client.app.state.store
        cliente = store.crea_cliente("Rossi")
        suo = call_con(client, "Suo", ["consegna prezzo"], client_id=cliente)
        altrui = call_con(client, "Altrui", ["consegna prezzo"])
        indicizza(client)
        finto.risposta = {
            "risposta": "x",
            "call": [
                {"session_id": suo, "perche": "", "passaggi": []},
                {"session_id": altrui, "perche": "", "passaggi": []},
            ],
        }

        fuori = client.post(
            auth("/ricerca/contestuale"),
            json={"domanda": "consegna prezzo", "client_id": cliente},
        ).json()
        assert [c["id"] for c in fuori["call"]] == [suo]
