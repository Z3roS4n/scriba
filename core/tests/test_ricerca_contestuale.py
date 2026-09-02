"""Test della ricerca contestuale.

Con un modello finto, come `test_analyze.py` e per la stessa ragione: qui si
verifica cosa il codice fa della risposta del modello, non quanto il modello
sia bravo. In particolare che una risposta plausibile ma inventata — una call
che non gli è stata data, la citazione di un passaggio di un'altra call — non
riesca ad arrivare sotto gli occhi di chi ha fatto la domanda.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.ai.contesto import (  # noqa: E402
    PER_CALL,
    IndiceMancante,
    RicercaContestuale,
)
from scriba_core.db.store import Store  # noqa: E402
from scriba_core.llm.base import Completion  # noqa: E402
from scriba_core.semantica.indice import Indice  # noqa: E402
from test_semantica import EmbedderLessicale  # noqa: E402

GIORNO = 86_400_000
QUANDO = 1_700_000_000_000


class ModelloFinto:
    """Risponde quello che gli si dice, e si ricorda cosa gli è stato chiesto."""

    name = "finto"
    model = "finto-1"

    def __init__(self, risposta: dict) -> None:
        self.risposta = risposta
        self.sistema = ""
        self.chiesto = ""

    def available(self) -> bool:
        return True

    def complete(self, *, system, user, schema=None, max_tokens=2048, temperature=0.2):
        self.sistema = system
        self.chiesto = user
        return Completion(text="", data=self.risposta, model=self.model, provider=self.name)


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "test.sqlite")


def call_con(
    store: Store,
    titolo: str,
    battute: list[str],
    *,
    client_id: int | None = None,
    quando: int = QUANDO,
) -> int:
    sid = store.create_session(quando, titolo=titolo)
    for i, battuta in enumerate(battute):
        store.add_segment(sid, "mic", i * 2000, i * 2000 + 2000, battuta, is_final=True)
    if client_id is not None:
        store.assegna_cliente(sid, client_id)
    return sid


def _passaggi_di(prompt: str, session_id: int) -> int:
    """Quanti passaggi di una certa call sono finiti nel prompt.

    Si conta leggendo il prompt come lo legge il modello: dall'intestazione
    della call fino alla successiva, le righe che cominciano con `[`.
    """
    quanti, dentro = 0, False
    for riga in prompt.splitlines():
        if riga.startswith("call "):
            dentro = riga.startswith(f"call {session_id} ")
        elif dentro and riga.startswith("["):
            quanti += 1
    return quanti


def cercatore(store: Store, risposta: dict) -> tuple[RicercaContestuale, ModelloFinto]:
    indice = Indice(store, EmbedderLessicale())
    indice.aggiorna()
    modello = ModelloFinto(risposta)
    return RicercaContestuale(store, indice, modello), modello


class TestSenzaIndice:
    def test_lo_dice_invece_di_rispondere_su_niente(self, store: Store) -> None:
        # Senza materiale il modello risponderebbe lo stesso, e sarebbe tutta
        # invenzione: è il modo peggiore di fallire, perché non si vede.
        call_con(store, "Mai indicizzata", ["parliamo del prezzo"])
        cercatore_ = RicercaContestuale(
            store, Indice(store, EmbedderLessicale()), ModelloFinto({})
        )
        with pytest.raises(IndiceMancante):
            cercatore_.rispondi("di cosa abbiamo parlato")


class TestCosaArrivaAlModello:
    def test_i_passaggi_arrivano_numerati_e_con_la_call_scritta_sopra(
        self, store: Store
    ) -> None:
        sid = call_con(store, "Preventivo", ["la tariffa oraria va rivista in aumento"])
        cerca, modello = cercatore(store, {"risposta": "", "call": []})
        cerca.rispondi("tariffa aumento")

        assert f"call {sid}" in modello.chiesto
        assert "«Preventivo»" in modello.chiesto
        assert "[1]" in modello.chiesto
        assert "tariffa oraria" in modello.chiesto

    def test_una_call_loquace_non_si_prende_tutti_i_posti(self, store: Store) -> None:
        # Senza il tetto per call, quella in cui si è parlato a lungo
        # dell'argomento riempie da sola il contesto e le altre non arrivano
        # nemmeno sotto gli occhi del modello: cioè il difetto che questa
        # ricerca dovrebbe risolvere.
        #
        # La call loquace produce da sola più passaggi di quanti ne stiano nel
        # contesto: senza tetto si prende tutti i posti e la seconda call non
        # compare affatto nel prompt.
        loquace = call_con(
            store, "Fiume", [f"prezzo prezzo tariffa numero {i} " * 30 for i in range(60)]
        )
        altra = call_con(store, "Breve", ["anche qui si parla di prezzo e tariffa"])
        cerca, modello = cercatore(store, {"risposta": "", "call": []})
        cerca.rispondi("prezzo tariffa")

        assert f"call {altra}" in modello.chiesto
        # E i passaggi della loquace sono quelli concessi, non tutti.
        suoi = _passaggi_di(modello.chiesto, loquace)
        assert 0 < suoi <= PER_CALL, f"{suoi} passaggi dalla call loquace"

    def test_la_lingua_arriva_al_modello(self, store: Store) -> None:
        call_con(store, "Una", ["parliamo del prezzo"])
        cerca, modello = cercatore(store, {"risposta": "", "call": []})
        cerca.rispondi("prezzo", lingua="en")
        assert "inglese" in modello.sistema


class TestCatene:
    def test_due_call_dello_stesso_cliente_arrivano_come_un_discorso_solo(
        self, store: Store
    ) -> None:
        cliente = store.crea_cliente("Rossi")
        prima = call_con(store, "Marzo", ["la consegna è per aprile"], client_id=cliente, quando=QUANDO)
        dopo = call_con(
            store,
            "Aprile",
            ["la consegna slitta, facciamo maggio"],
            client_id=cliente,
            quando=QUANDO + 20 * GIORNO,
        )
        cerca, modello = cercatore(
            store,
            {
                "risposta": "Maggio: ad aprile la data è stata spostata.",
                "call": [
                    {"session_id": dopo, "perche": "è la più recente", "passaggi": []},
                    {"session_id": prima, "perche": "diceva aprile", "passaggi": []},
                ],
            },
        )
        risposta = cerca.rispondi("consegna")

        assert "catena" in modello.chiesto
        assert "corregge" in modello.chiesto
        assert len(risposta.catene) == 1
        assert risposta.catene[0].session_ids == [prima, dopo]

    def test_si_puo_chiedere_di_non_unirle(self, store: Store) -> None:
        cliente = store.crea_cliente("Rossi")
        call_con(store, "Marzo", ["la consegna è per aprile"], client_id=cliente)
        call_con(
            store,
            "Aprile",
            ["la consegna slitta a maggio"],
            client_id=cliente,
            quando=QUANDO + 20 * GIORNO,
        )
        cerca, modello = cercatore(store, {"risposta": "", "call": []})
        risposta = cerca.rispondi("consegna", unisci_catene=False)

        assert "catena" not in modello.chiesto
        assert risposta.catene == []

    def test_le_catene_riportate_sono_solo_quelle_davvero_citate(self, store: Store) -> None:
        cliente = store.crea_cliente("Rossi")
        prima = call_con(store, "Marzo", ["consegna prezzo aprile"], client_id=cliente)
        call_con(
            store,
            "Aprile",
            ["consegna prezzo maggio"],
            client_id=cliente,
            quando=QUANDO + 10 * GIORNO,
        )
        muto = call_con(store, "Senza cliente", ["consegna prezzo settembre"])
        cerca, _ = cercatore(
            store,
            {"risposta": "x", "call": [{"session_id": muto, "perche": "questa", "passaggi": []}]},
        )
        risposta = cerca.rispondi("consegna prezzo")

        # La catena c'è, ma nessuna delle sue call è finita nella risposta:
        # dichiararla confonderebbe il materiale letto con quello usato.
        assert [c.session_id for c in risposta.call] == [muto]
        assert prima not in [s for c in risposta.catene for s in c.session_ids]


class TestCosaTornaIndietro:
    def test_una_call_inventata_non_arriva_a_chi_ha_chiesto(self, store: Store) -> None:
        vera = call_con(store, "Vera", ["parliamo del prezzo e della tariffa"])
        cerca, _ = cercatore(
            store,
            {
                "risposta": "eccola",
                "call": [
                    {"session_id": vera, "perche": "ci sta scritto", "passaggi": [1]},
                    # Un numero che il modello non ha mai ricevuto: mostrarlo
                    # manderebbe qualcuno ad aprire una conversazione che non
                    # c'entra, o che non esiste.
                    {"session_id": 9999, "perche": "anche qui", "passaggi": []},
                ],
            },
        )
        risposta = cerca.rispondi("prezzo tariffa")
        assert [c.session_id for c in risposta.call] == [vera]

    def test_un_passaggio_di_un_altra_call_non_viene_attribuito(self, store: Store) -> None:
        una = call_con(store, "Una", ["prezzo tariffa preventivo"])
        altra = call_con(store, "Altra", ["prezzo tariffa sconto"])
        cerca, _ = cercatore(
            store,
            {
                "risposta": "x",
                # Tutti i numeri di passaggio esistenti, appesi a una call sola:
                # se passassero, si mostrerebbe come detto in questa call
                # qualcosa che è stato detto nell'altra.
                "call": [{"session_id": una, "perche": "y", "passaggi": [1, 2, 3, 4]}],
            },
        )
        risposta = cerca.rispondi("prezzo tariffa")
        assert risposta.call[0].passaggi
        assert all(p.session_id == una for p in risposta.call[0].passaggi)
        assert altra not in [p.session_id for p in risposta.call[0].passaggi]

    def test_il_testo_dei_passaggi_lo_rilegge_l_archivio(self, store: Store) -> None:
        # Il modello non scrive mai le citazioni: le parafraserebbe credendo di
        # aiutare, ed è la regola che vale per tutta l'estrazione.
        una = call_con(store, "Una", ["il preventivo lo rivediamo a settembre"])
        cerca, _ = cercatore(
            store,
            {"risposta": "x", "call": [{"session_id": una, "perche": "y", "passaggi": [1]}]},
        )
        risposta = cerca.rispondi("preventivo settembre")
        assert risposta.call[0].passaggi[0].testo == "il preventivo lo rivediamo a settembre"

    def test_la_risposta_porta_con_se_di_chi_e_e_quanto_e_costata(self, store: Store) -> None:
        una = call_con(store, "Una", ["prezzo"])
        cerca, _ = cercatore(
            store, {"risposta": "risposta breve", "call": [{"session_id": una, "perche": "", "passaggi": []}]}
        )
        risposta = cerca.rispondi("prezzo")
        assert risposta.testo == "risposta breve"
        assert risposta.provider == "finto"
        assert risposta.passaggi_letti >= 1
