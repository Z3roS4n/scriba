"""Test della ricerca semantica: divisione in passaggi, indice, catene.

Nessuno di questi test carica il modello vero. Non è una scorciatoia: il
modello è 470 MB, ci vuole un secondo e mezzo solo a caricarlo, e quello che
c'è da verificare qui — che i passaggi si spezzino dove devono, che l'indice si
accorga di essere vecchio, che la ricerca metta in ordine — non dipende affatto
da *quali* numeri produca il modello, solo dal fatto che ne produca. Al suo
posto c'è `EmbedderLessicale`, venti righe che danno vettori veri con una
proprietà utile: testi che condividono parole si somigliano.

Quanto trovi il modello vero è un'altra domanda, e ha un altro strumento:
`spikes/bench_semantica.py`, che si esegue a mano e stampa dei numeri.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.db.store import Segment, Store  # noqa: E402
from scriba_core.semantica.catene import catene  # noqa: E402
from scriba_core.semantica.indice import MARGINE, Indice, IndiceVuoto  # noqa: E402
from scriba_core.semantica.spezza import in_passaggi  # noqa: E402

GIORNO = 86_400_000


class EmbedderLessicale:
    """Un modello finto che però somiglia a un modello.

    Ogni parola finisce in una casella scelta dal suo hash e la conta ci
    aggiunge uno; poi si normalizza. Due testi che condividono parole hanno
    quindi un coseno alto, due che non ne condividono nessuna ce l'hanno a
    zero. È abbastanza per verificare l'ordinamento, la soglia relativa e il
    passaggio dei vettori dentro e fuori dal database — cioè tutto quello che
    è codice nostro.
    """

    id = "lessicale-di-prova"
    dim = 64

    def vettori(self, testi: list[str], *, come: str) -> np.ndarray:
        assert come in ("passaggio", "domanda")
        fuori = np.zeros((len(testi), self.dim), dtype=np.float32)
        for i, testo in enumerate(testi):
            for parola in testo.lower().split():
                pulita = parola.strip(".,:;?!«»")
                if not pulita:
                    continue
                casella = int(hashlib.sha1(pulita.encode()).hexdigest()[:8], 16) % self.dim
                fuori[i, casella] += 1.0
        lunghezze = np.linalg.norm(fuori, axis=1, keepdims=True)
        return fuori / np.clip(lunghezze, 1e-9, None)


def seg(id_: int, testo: str, *, t: int = 0, eco: bool = False) -> Segment:
    return Segment(
        id=id_,
        session_id=1,
        source="mic",
        t_start_ms=t,
        t_end_ms=t + 1000,
        testo=testo,
        is_final=True,
        revision=0,
        eco=eco,
    )


# --------------------------------------------------------------- i passaggi


class TestDivisioneInPassaggi:
    def test_niente_da_dividere_non_produce_niente(self) -> None:
        assert in_passaggi([]) == []
        assert in_passaggi([seg(1, "   ")]) == []

    def test_una_call_corta_resta_un_passaggio_solo(self) -> None:
        passaggi = in_passaggi([seg(1, "buongiorno a tutti", t=0), seg(2, "cominciamo", t=1000)])
        assert len(passaggi) == 1
        assert passaggi[0].testo == "buongiorno a tutti cominciamo"
        # Gli estremi vengono dai segmenti, non dal passaggio: servono a
        # riportare chi legge al punto della call in cui è stato detto.
        assert (passaggi[0].t_start_ms, passaggi[0].t_end_ms) == (0, 2000)

    def test_il_parlato_lungo_si_spezza_e_ogni_pezzo_resta_leggibile(self) -> None:
        segmenti = [seg(i, f"frase numero {i} di una call molto lunga", t=i * 1000) for i in range(60)]
        passaggi = in_passaggi(segmenti, caratteri=200)

        assert len(passaggi) > 3
        assert [p.ord for p in passaggi] == list(range(len(passaggi)))
        # Nessun passaggio enorme: il taglio serve proprio a questo.
        assert all(len(p.testo) < 400 for p in passaggi)
        # E il tempo va sempre avanti.
        assert all(a.t_start_ms <= b.t_start_ms for a, b in zip(passaggi, passaggi[1:]))

    def test_le_frasi_sul_confine_stanno_in_tutti_e_due_i_passaggi(self) -> None:
        # Senza sovrapposizione, «il prezzo lo rivediamo / a settembre» diventa
        # due passaggi che nessuna delle due domande possibili trova.
        #
        # Ogni segmento ha parole che non compaiono in nessun altro: se avessero
        # parole in comune — «con», «di», «parole» — i due passaggi
        # risulterebbero sovrapposti anche togliendo la sovrapposizione, e
        # questo test passerebbe sempre senza verificare niente.
        segmenti = [seg(i, f"alfa{i} beta{i} gamma{i} delta{i}", t=i * 1000) for i in range(20)]
        passaggi = in_passaggi(segmenti, caratteri=120, minimo=40, coda=1)

        assert len(passaggi) > 2
        for prima, dopo in zip(passaggi, passaggi[1:]):
            comune = set(prima.testo.split()) & set(dopo.testo.split())
            assert comune, f"nessuna sovrapposizione fra {prima.ord} e {dopo.ord}"

    def test_la_coda_troppo_corta_non_diventa_un_risultato_da_due_parole(self) -> None:
        segmenti = [seg(i, "una battuta lunga il giusto per riempire", t=i * 1000) for i in range(10)]
        segmenti.append(seg(99, "ciao", t=10_000))
        passaggi = in_passaggi(segmenti, caratteri=120, minimo=80)

        assert all(len(p.testo) >= 80 for p in passaggi)
        assert passaggi[-1].testo.endswith("ciao")

    def test_un_segmento_piu_lungo_del_taglio_non_manda_in_stallo(self) -> None:
        # La sovrapposizione fa ripartire il gruppo successivo indietro: se il
        # passo indietro fosse grande quanto il gruppo, il ciclo non finirebbe.
        segmenti = [seg(i, "parola " * 300, t=i * 1000) for i in range(4)]
        passaggi = in_passaggi(segmenti, caratteri=100, coda=3)
        assert len(passaggi) == 4


# ------------------------------------------------------------ il database


@pytest.fixture()
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "test.sqlite")


@pytest.fixture()
def call(store: Store) -> int:
    sid = store.create_session(1_700_000_000_000, titolo="Prima call")
    store.add_segment(sid, "mic", 0, 2000, "parliamo del prezzo del progetto", is_final=True)
    store.add_segment(sid, "loopback", 2000, 4000, "per noi è troppo alto", is_final=True)
    return sid


class TestStatoDellIndice:
    def test_una_call_mai_indicizzata_risulta_da_fare(self, store: Store, call: int) -> None:
        assert store.da_indicizzare("qualunque") == [call]

    def test_dopo_averla_salvata_non_risulta_piu_da_fare(self, store: Store, call: int) -> None:
        firma = store.firme_trascrizioni()[call]
        store.salva_passaggi(
            call, [(0, 0, 4000, "tutto", b"\x00" * 8)], modello="m", dim=2, firma=firma
        )
        assert store.da_indicizzare("m") == []

    def test_una_parola_rifinita_rende_vecchio_l_indice(self, store: Store, call: int) -> None:
        firma = store.firme_trascrizioni()[call]
        store.salva_passaggi(call, [], modello="m", dim=2, firma=firma)
        assert store.da_indicizzare("m") == []

        # La rifinitura riscrive il testo e alza `revision`: i passaggi salvati
        # descrivono parole che non ci sono più.
        segmento = store.segments(call, only_final=True)[0]
        store.refine_segment(segmento.id, "parliamo del preventivo del progetto")
        assert store.da_indicizzare("m") == [call]

    def test_una_riga_marcata_come_eco_rende_vecchio_l_indice(self, store: Store, call: int) -> None:
        firma = store.firme_trascrizioni()[call]
        store.salva_passaggi(call, [], modello="m", dim=2, firma=firma)
        segmento = store.segments(call, only_final=True)[1]
        store.marca_eco(segmento.id)
        assert store.da_indicizzare("m") == [call]

    def test_cambiare_modello_rende_vecchio_tutto(self, store: Store, call: int) -> None:
        firma = store.firme_trascrizioni()[call]
        store.salva_passaggi(call, [], modello="vecchio", dim=2, firma=firma)
        # Due modelli producono vettori che non si possono confrontare fra
        # loro: mescolarli darebbe punteggi plausibili e senza significato.
        assert store.da_indicizzare("nuovo") == [call]

    def test_una_call_senza_parlato_non_viene_proposta_in_eterno(self, store: Store) -> None:
        muta = store.create_session(1_700_000_000_000, titolo="Nessuno ha parlato")
        assert muta not in store.da_indicizzare("m")

    def test_salvare_di_nuovo_sostituisce_invece_di_accumulare(self, store: Store, call: int) -> None:
        firma = store.firme_trascrizioni()[call]
        store.salva_passaggi(
            call,
            [(0, 0, 1000, "primo", b"\x00" * 8), (1, 1000, 2000, "secondo", b"\x00" * 8)],
            modello="m",
            dim=2,
            firma=firma,
        )
        store.salva_passaggi(
            call, [(0, 0, 2000, "rifatto", b"\x00" * 8)], modello="m", dim=2, firma=firma
        )
        righe = store.passaggi([call])
        assert [r["testo"] for r in righe] == ["rifatto"]

    def test_dimenticare_l_indice_lo_toglie_davvero(self, store: Store, call: int) -> None:
        firma = store.firme_trascrizioni()[call]
        store.salva_passaggi(
            call, [(0, 0, 1000, "x", b"\x00" * 8)], modello="m", dim=2, firma=firma
        )
        assert store.dimentica_indice() == 1
        assert store.passaggi() == []
        assert store.da_indicizzare("m") == [call]

    def test_cancellare_la_call_porta_via_i_suoi_passaggi(self, store: Store, call: int) -> None:
        firma = store.firme_trascrizioni()[call]
        store.salva_passaggi(
            call, [(0, 0, 1000, "x", b"\x00" * 8)], modello="m", dim=2, firma=firma
        )
        store.elimina_sessione(call)
        assert store.passaggi() == []
        assert store.stato_indice() == {}


# -------------------------------------------------------------- la ricerca


@pytest.fixture()
def indice(store: Store) -> Indice:
    return Indice(store, EmbedderLessicale())


def scrivi_call(store: Store, titolo: str, battute: list[str], *, quando: int = 1_700_000_000_000) -> int:
    sid = store.create_session(quando, titolo=titolo)
    for i, battuta in enumerate(battute):
        store.add_segment(sid, "mic", i * 2000, i * 2000 + 2000, battuta, is_final=True)
    return sid


class TestRicercaSemantica:
    def test_cercare_senza_indice_lo_dice_invece_di_non_trovare_niente(
        self, indice: Indice, store: Store
    ) -> None:
        scrivi_call(store, "Mai indicizzata", ["si parla di qualcosa"])
        # Zero risultati sarebbe indistinguibile da «non c'è»: è il modo più
        # veloce per far credere che l'archivio sia vuoto.
        with pytest.raises(IndiceVuoto):
            indice.cerca("qualcosa")

    def test_indicizza_e_ritrova(self, indice: Indice, store: Store) -> None:
        prezzi = scrivi_call(store, "Prezzi", ["la tariffa oraria va rivista in aumento"])
        consegne = scrivi_call(store, "Consegne", ["la spedizione arriva lunedì mattina"])
        riepilogo = indice.aggiorna()

        assert riepilogo.call == 2
        assert riepilogo.passaggi == 2
        trovati = indice.cerca("tariffa aumento")
        assert trovati[0].session_id == prezzi
        assert consegne not in [t.session_id for t in trovati]

    def test_indicizzare_due_volte_non_rifa_il_lavoro(self, indice: Indice, store: Store) -> None:
        scrivi_call(store, "Una", ["prima battuta della call"])
        assert indice.aggiorna().call == 1
        # Su un archivio di duecento ore, rifare tutto a ogni avvio vorrebbe
        # dire non finire mai.
        assert indice.aggiorna().call == 0

    def test_i_filtri_dell_archivio_valgono_anche_qui(self, indice: Indice, store: Store) -> None:
        dentro = scrivi_call(store, "Dentro", ["parliamo del prezzo"])
        fuori = scrivi_call(store, "Fuori", ["parliamo del prezzo anche qui"])
        indice.aggiorna()

        trovati = indice.cerca("prezzo", session_ids=[dentro])
        assert {t.session_id for t in trovati} == {dentro}
        assert fuori not in {t.session_id for t in trovati}

    def test_la_soglia_e_relativa_al_migliore(self, indice: Indice, store: Store) -> None:
        vicino = scrivi_call(store, "Vicino", ["prezzo tariffa preventivo sconto"])
        lontano = scrivi_call(store, "Lontano", ["cartoline francobolli affrancatura elefanti"])
        indice.aggiorna()

        trovati = indice.cerca("prezzo tariffa", margine=MARGINE)
        assert [t.session_id for t in trovati] == [vicino]
        # Con la rete larghissima ci entra anche quello che non c'entra: è la
        # prova che a filtrare è la soglia e non il caso.
        assert lontano in {t.session_id for t in indice.cerca("prezzo tariffa", margine=2.0)}

    def test_i_risultati_arrivano_in_ordine(self, indice: Indice, store: Store) -> None:
        scrivi_call(store, "A", ["prezzo prezzo prezzo tariffa"])
        scrivi_call(store, "B", ["prezzo altro discorso lungo eccetera"])
        indice.aggiorna()
        punteggi = [t.punteggio for t in indice.cerca("prezzo tariffa", margine=2.0)]
        assert punteggi == sorted(punteggi, reverse=True)

    def test_un_indice_di_un_altro_modello_non_si_confronta(
        self, indice: Indice, store: Store
    ) -> None:
        call = scrivi_call(store, "Vecchia", ["qualcosa"])
        firma = store.firme_trascrizioni()[call]
        # Otto byte, cioè due float: non è la dimensione di questo modello.
        store.salva_passaggi(
            call, [(0, 0, 1000, "x", b"\x00" * 8)], modello="altro", dim=2, firma=firma
        )
        with pytest.raises(IndiceVuoto):
            indice.cerca("qualcosa")

    def test_si_puo_fermare_a_meta_e_quello_che_e_fatto_resta_fatto(
        self, indice: Indice, store: Store
    ) -> None:
        for i in range(4):
            scrivi_call(store, f"Call {i}", [f"battuta numero {i}"])

        visti = 0

        def basta() -> bool:
            nonlocal visti
            visti += 1
            return visti > 2

        riepilogo = indice.aggiorna(fermati=basta)
        assert riepilogo.interrotta
        assert riepilogo.call == 2
        # E il giro dopo riprende da dove si era rimasti, senza rifare le due.
        assert indice.aggiorna().call == 2

    def test_lo_stato_dice_quanto_manca(self, indice: Indice, store: Store) -> None:
        scrivi_call(store, "Fatta", ["prima call"])
        indice.aggiorna()
        scrivi_call(store, "Da fare", ["seconda call"])

        stato = indice.stato()
        assert stato["call_con_parlato"] == 2
        assert stato["call_indicizzate"] == 1
        assert stato["modello"] == "lessicale-di-prova"


# --------------------------------------------------------------- le catene


class TestCatene:
    def test_due_call_vicine_dello_stesso_cliente_sono_lo_stesso_discorso(self) -> None:
        risultato = catene([(1, 7, 0), (2, 7, 10 * GIORNO)])
        assert len(risultato) == 1
        assert risultato[0].session_ids == [1, 2]
        assert risultato[0].unita

    def test_troppo_tempo_in_mezzo_e_sono_due_discorsi(self) -> None:
        risultato = catene([(1, 7, 0), (2, 7, 200 * GIORNO)])
        assert sorted(c.session_ids for c in risultato) == [[1], [2]]

    def test_la_catena_arriva_in_ordine_di_tempo(self) -> None:
        # L'archivio le restituisce dalla più recente; una catena letta al
        # contrario racconterebbe la storia alla rovescia, e la decisione
        # superata sembrerebbe quella finale.
        risultato = catene([(3, 7, 20 * GIORNO), (1, 7, 0), (2, 7, 10 * GIORNO)])
        assert risultato[0].session_ids == [1, 2, 3]

    def test_clienti_diversi_non_si_mescolano(self) -> None:
        risultato = catene([(1, 7, 0), (2, 8, GIORNO)])
        assert sorted(c.session_ids for c in risultato) == [[1], [2]]

    def test_le_call_senza_cliente_restano_da_sole(self) -> None:
        # Due riunioni con due persone diverse capitate lo stesso giorno non
        # sono lo stesso discorso, e senza cliente non c'è modo di saperlo.
        risultato = catene([(1, None, 0), (2, None, GIORNO)])
        assert sorted(c.session_ids for c in risultato) == [[1], [2]]

    def test_una_catena_lunga_non_si_spezza_se_i_passi_sono_corti(self) -> None:
        righe = [(i, 7, i * 20 * GIORNO) for i in range(1, 6)]
        risultato = catene(righe)
        assert len(risultato) == 1
        assert risultato[0].session_ids == [1, 2, 3, 4, 5]

    def test_si_spezza_dove_c_e_il_buco(self) -> None:
        righe = [(1, 7, 0), (2, 7, 5 * GIORNO), (3, 7, 300 * GIORNO), (4, 7, 305 * GIORNO)]
        risultato = catene(righe)
        assert sorted(c.session_ids for c in risultato) == [[1, 2], [3, 4]]
