"""Test del riconoscimento dell'eco dall'altoparlante.

Il caso è preso da una call vera: l'interlocutore dice una frase, e tre secondi
dopo la stessa frase compare attribuita a chi registra. Il microfono aveva
ripreso l'altoparlante.

È un difetto peggiore del rumore: non produce testo sbagliato, produce testo
giusto attribuito alla persona sbagliata, e un riassunto costruito su quello
inverte chi ha detto cosa.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.stt.eco import FiltroEco, ripassa, somiglianza  # noqa: E402


@dataclass
class Riga:
    """Una riga di trascrizione, ridotta a cio' che serve per giudicarla."""

    id: int
    t_start_ms: int
    testo: str

# Le due righe come sono comparse davvero, a tre secondi di distanza.
DETTO_DA_LORO = (
    "Tutta la durata del presente accordo, nessuna parte contatterà direttamente un "
    "cliente segnalato, dall'altra parte per proporgli senza il convolgimento del "
    "partner segnalante servizi propri concorrenti rispetto a quelli offerti dal "
    "partner segnalante stesso."
)
TORNATO_DAL_MICROFONO = (
    "Nessuna parte contatterà direttamente un cliente segnalato dall'altra parte per "
    "proporci senza il convolgimento del partner segnalante servizi propri concorrenti "
    "rispetto a quelli offerti dal partner segnalante stesso."
)


class TestCasoReale:
    def test_l_eco_della_call_vera_viene_riconosciuto(self) -> None:
        f = FiltroEco()
        f.registra_uscita(729_000, DETTO_DA_LORO)
        assert f.e_eco(732_000, TORNATO_DAL_MICROFONO)

    def test_la_somiglianza_e_alta_pur_essendo_trascrizioni_diverse(self) -> None:
        # L'eco è più smorzato e qualche parola cambia ("proporgli" ->
        # "proporci"): confrontare i caratteri non basterebbe.
        assert somiglianza(TORNATO_DAL_MICROFONO, DETTO_DA_LORO) > 0.9


class TestQuandoNonSopprimere:
    def test_una_risposta_non_e_un_eco(self) -> None:
        f = FiltroEco()
        f.registra_uscita(1_000, "secondo me dovremmo rimandare la migrazione a settembre")
        assert not f.e_eco(4_000, "non sono d'accordo, settembre è troppo tardi per il cliente")

    def test_ripetere_qualche_parola_non_basta(self) -> None:
        # Capita di riprendere le parole dell'altro senza che sia eco.
        f = FiltroEco()
        f.registra_uscita(1_000, "il budget complessivo è di cinquantamila euro sul progetto")
        assert not f.e_eco(3_000, "cinquantamila mi sembra ragionevole, procediamo pure così")

    def test_le_frasi_brevi_non_si_giudicano(self) -> None:
        # "sì", "certo", "esatto" compaiono su entrambe le tracce di continuo.
        f = FiltroEco()
        f.registra_uscita(1_000, "sì certo")
        assert not f.e_eco(2_000, "sì certo")

    def test_fuori_dalla_finestra_e_una_coincidenza(self) -> None:
        # La stessa frase mezz'ora dopo è qualcuno che la ripete davvero.
        f = FiltroEco()
        f.registra_uscita(1_000, DETTO_DA_LORO)
        assert not f.e_eco(1_800_000, TORNATO_DAL_MICROFONO)

    def test_l_eco_non_precede_la_causa(self) -> None:
        # Se il microfono l'ha detto molto prima dell'altoparlante, non può
        # esserne l'eco: è la persona che ha parlato per prima.
        f = FiltroEco()
        f.registra_uscita(60_000, DETTO_DA_LORO)
        assert not f.e_eco(20_000, TORNATO_DAL_MICROFONO)


class TestSomiglianza:
    def test_identiche(self) -> None:
        assert somiglianza("una frase qualunque", "una frase qualunque") == 1.0

    def test_senza_nulla_in_comune(self) -> None:
        assert somiglianza("gatto cane topo", "sedia tavolo lampada") == 0.0

    def test_gli_accenti_non_contano(self) -> None:
        assert somiglianza("perché città", "perche citta") == 1.0

    def test_le_ripetizioni_non_gonfiano_il_punteggio(self) -> None:
        # Senza contare le occorrenze, "sì sì sì sì" somiglierebbe a tutto ciò
        # che contiene un "sì".
        assert somiglianza("si si si si", "si va bene") == 0.25

    def test_testo_vuoto(self) -> None:
        assert somiglianza("", "qualcosa") == 0.0


# Il caso che il filtro lasciava passare, preso dalla sessione 11: un unico
# intervento dell'interlocutore lungo 26 secondi, di cui il microfono ha
# prodotto due pezzi, chiusi venti secondi prima che l'originale finisse.
LUNGA_DELL_ALTRO = "Ok. Quindi ora io devo dividere, mi sento vincolato di fare tutto insieme."
PEZZI_DAL_MICROFONO = [
    (158_400, "Quindi ora io devo dividere."),
    (160_900, "mi sento vincolato di fare tutto"),
]


class TestGiudicatoTroppoPresto:
    """Il difetto #59: si giudicava prima che la frase dell'altro finisse."""

    def test_aspettare_il_definitivo_rende_il_filtro_cieco(self) -> None:
        # Com'era: la frase dell'altoparlante entra solo quando si chiude, a
        # 183 s. I pezzi del microfono sono stati giudicati a 158 e 160 s.
        f = FiltroEco()
        for t, testo in PEZZI_DAL_MICROFONO:
            assert not f.e_eco(t, testo), "senza le ipotesi provvisorie non puo' saperlo"
        f.registra_uscita(157_200, LUNGA_DELL_ALTRO)

    def test_con_le_ipotesi_provvisorie_li_riconosce(self) -> None:
        # Com'e': l'altoparlante annota man mano. A 158 s ha gia' detto la
        # prima meta', a 161 s anche la seconda.
        f = FiltroEco()
        f.registra_uscita(157_200, "Ok. Quindi ora io devo dividere,")
        assert f.e_eco(158_400, PEZZI_DAL_MICROFONO[0][1])
        f.registra_uscita(157_200, LUNGA_DELL_ALTRO)
        assert f.e_eco(160_900, PEZZI_DAL_MICROFONO[1][1])

    def test_l_ipotesi_nuova_sostituisce_la_vecchia(self) -> None:
        # Sono la stessa frase, non due: se si accumulassero, un'ora di call
        # riempirebbe la memoria di versioni parziali della stessa cosa.
        f = FiltroEco()
        f.registra_uscita(1_000, "il budget complessivo")
        f.registra_uscita(1_000, "il budget complessivo e' di cinquantamila euro")
        assert len(f._uscite) == 1
        assert f._uscite[0][1].endswith("cinquantamila euro")


class TestRipasso:
    """A call finita esiste tutto, e il giudizio si rifa' per intero."""

    def test_prende_quello_che_dal_vivo_era_impossibile_sapere(self) -> None:
        mic = [Riga(i, t, testo) for i, (t, testo) in enumerate(PEZZI_DAL_MICROFONO, start=1)]
        loopback = [Riga(90, 157_200, LUNGA_DELL_ALTRO)]
        assert ripassa(mic, loopback) == [1, 2]

    def test_non_tocca_quello_che_e_stato_detto_davvero(self) -> None:
        mic = [
            Riga(1, 4_000, "non sono d'accordo, settembre e' troppo tardi per il cliente"),
            Riga(2, 9_000, "cinquantamila mi sembra ragionevole, procediamo pure cosi'"),
        ]
        loopback = [
            Riga(90, 1_000, "secondo me dovremmo rimandare la migrazione a settembre"),
            Riga(91, 6_000, "il budget complessivo e' di cinquantamila euro sul progetto"),
        ]
        assert ripassa(mic, loopback) == []

    def test_la_stessa_frase_mezz_ora_dopo_resta(self) -> None:
        # Fuori dalla finestra e' qualcuno che la ripete davvero.
        mic = [Riga(1, 1_800_000, TORNATO_DAL_MICROFONO)]
        loopback = [Riga(90, 1_000, DETTO_DA_LORO)]
        assert ripassa(mic, loopback) == []

    def test_senza_traccia_dell_altro_non_giudica_niente(self) -> None:
        mic = [Riga(1, 1_000, DETTO_DA_LORO)]
        assert ripassa(mic, []) == []

    def test_il_livello_scelto_vale_anche_qui(self) -> None:
        # Un giudizio che dal vivo e a fine call usa soglie diverse darebbe
        # trascrizioni diverse a seconda di quando la si guarda.
        mic = [Riga(1, 3_000, "gestione delle scadenze e del processo interno")]
        loopback = [Riga(90, 1_000, "gestione delle scadenze, il processo interno, tutto qui")]
        assert ripassa(mic, loopback, soglia=0.55) == [1]
        assert ripassa(mic, loopback, soglia=0.99) == []


class TestMemoria:
    def test_il_filtro_non_cresce_all_infinito(self) -> None:
        # Una call di due ore non deve accumulare tutto il parlato in memoria.
        f = FiltroEco(finestra_ms=10_000)
        for i in range(5_000):
            f.registra_uscita(i * 1_000, f"frase numero {i} della riunione di oggi")
        assert len(f._uscite) < 60
