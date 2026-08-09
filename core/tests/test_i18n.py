"""La lingua dell'interfaccia arriva al core, e cambia solo quello che si legge.

Il rischio di questa funzione non è che non traduca: è che traduca **troppo**.
Un identificatore tradotto — `local` che diventa `local model`, `alta` che
diventa `high` in una richiesta — non si vede finché qualcosa non smette di
combaciare, e allora sembra un difetto di tutt'altro.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.i18n import fase, lingua_da_header, motore  # noqa: E402
from scriba_core.server import FASI_ANALISI, PROVIDERS_INFO  # noqa: E402


class TestQualeLingua:
    def test_le_forme_regionali_valgono(self) -> None:
        # `en-GB` è inglese. Rifiutarlo vorrebbe dire ripiegare sull'italiano
        # per un'interfaccia che la sua lingua l'aveva dichiarata.
        assert lingua_da_header("en-GB") == "en"
        assert lingua_da_header("it_IT") == "it"

    def test_si_prende_la_prima_conosciuta(self) -> None:
        assert lingua_da_header("de-DE,en;q=0.9,it;q=0.8") == "en"

    def test_senza_intestazione_resta_l_italiano(self) -> None:
        # Il comportamento di sempre: una richiesta che non dice niente non
        # deve cambiare quello che l'utente vedeva prima.
        assert lingua_da_header(None) == "it"
        assert lingua_da_header("") == "it"
        assert lingua_da_header("de,fr") == "it"


class TestMotori:
    def test_in_inglese_cambiano_i_tre_testi(self) -> None:
        info = motore(PROVIDERS_INFO["local"], "local", "en")
        assert info["etichetta"] == "Local model"
        assert "leaves the computer" in info["descrizione"]
        assert "Settings" in info["rimedio"]

    def test_gli_identificatori_non_si_traducono(self) -> None:
        """È il punto: si traduce dove si mostra, mai dove si confronta."""
        it = PROVIDERS_INFO["anthropic"]
        en = motore(it, "anthropic", "en")
        assert en["model"] == it["model"]
        assert en["esce_dal_computer"] == it["esce_dal_computer"]
        assert en["costo_ora_usd"] == it["costo_ora_usd"]
        assert en["minuti_per_ora"] == it["minuti_per_ora"]

    def test_l_italiano_resta_quello_di_prima(self) -> None:
        for id_, info in PROVIDERS_INFO.items():
            assert motore(info, id_, "it") == info

    def test_la_tabella_condivisa_non_viene_scritta(self) -> None:
        # Senza la copia, la prima richiesta in inglese lascerebbe la tabella
        # inglese per tutti — compreso chi guarda in italiano.
        prima = PROVIDERS_INFO["local"]["etichetta"]
        motore(PROVIDERS_INFO["local"], "local", "en")
        assert PROVIDERS_INFO["local"]["etichetta"] == prima

    def test_ogni_motore_ha_la_sua_traduzione(self) -> None:
        # Un motore aggiunto e non tradotto uscirebbe in italiano dentro
        # un'interfaccia inglese, e sembrerebbe una scelta.
        for id_, info in PROVIDERS_INFO.items():
            en = motore(info, id_, "en")
            assert en["etichetta"] != info["etichetta"], id_


class TestFasi:
    @pytest.mark.parametrize("chiave,titolo", list(FASI_ANALISI))
    def test_ogni_fase_ha_un_titolo_inglese(self, chiave: str, titolo: str) -> None:
        assert fase(chiave, titolo, "en") != titolo

    def test_una_fase_sconosciuta_non_sparisce(self, ) -> None:
        # Meglio il titolo italiano che una casella vuota nell'avanzamento.
        assert fase("inventata", "Inventata", "en") == "Inventata"
