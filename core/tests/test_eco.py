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
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.stt.eco import FiltroEco, somiglianza  # noqa: E402

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


class TestMemoria:
    def test_il_filtro_non_cresce_all_infinito(self) -> None:
        # Una call di due ore non deve accumulare tutto il parlato in memoria.
        f = FiltroEco(finestra_ms=10_000)
        for i in range(5_000):
            f.registra_uscita(i * 1_000, f"frase numero {i} della riunione di oggi")
        assert len(f._uscite) < 60
