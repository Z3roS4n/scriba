"""Test della correzione dei nomi propri.

Metà di questi test verificano che il glossario **non** faccia niente. È la metà
che conta: correggere un nome giusto in un nome sbagliato è peggio del difetto
che si sta risolvendo, perché il primo lo si vede rileggendo e il secondo no.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.stt.base import TranscriptEvent  # noqa: E402
from scriba_core.stt.glossario import (  # noqa: E402
    correggi,
    distanza,
    normalizza,
    sottostringa_comune,
)


class TestMisure:
    def test_distanza(self) -> None:
        assert distanza("clotilde", "clotilde") == 0
        assert distanza("cotilde", "clotilde") == 1
        assert distanza("tilde", "clotilde") == 3
        assert distanza("protile", "clotilde") == 3
        assert distanza("", "giulia") == 6

    def test_sottostringa_comune(self) -> None:
        assert sottostringa_comune("protile", "clotilde") == 4  # "otil"
        assert sottostringa_comune("tilde", "clotilde") == 5
        assert sottostringa_comune("banana", "kiwi") == 0

    def test_normalizza_toglie_accenti_e_maiuscole(self) -> None:
        assert normalizza("Andrè") == normalizza("ANDRE") == "andre"


class TestPrudente:
    """Il livello di default: solo ciò che è quasi identico."""

    def test_una_lettera_di_scarto_si_corregge(self) -> None:
        fuori, cambi = correggi("il preventivo di Cotilde", ["Clotilde"])
        assert fuori == "il preventivo di Clotilde"
        assert (cambi[0].trovato, cambi[0].termine) == ("Cotilde", "Clotilde")

    def test_rimette_le_maiuscole_e_gli_accenti(self) -> None:
        fuori, cambi = correggi("ne parlo con andre", ["Andrè"])
        assert fuori == "ne parlo con Andrè"
        assert len(cambi) == 1

    def test_non_arriva_a_protile(self) -> None:
        # Tre modifiche su otto lettere: a questo livello, di proposito, no.
        fuori, cambi = correggi("ne parla Protile", ["Clotilde"])
        assert fuori == "ne parla Protile"
        assert cambi == []

    def test_una_parola_gia_giusta_non_e_una_correzione(self) -> None:
        fuori, cambi = correggi("il preventivo di Clotilde", ["Clotilde"])
        assert fuori == "il preventivo di Clotilde"
        assert cambi == []

    def test_le_parole_corte_devono_combaciare(self) -> None:
        # Con «Ivo» nel glossario, una lettera di scarto prenderebbe "ivi",
        # "uno", "ove": su tre lettere una modifica e' un'altra parola.
        fuori, _ = correggi("ci sono ivi delle note", ["Ivo"])
        assert fuori == "ci sono ivi delle note"


class TestNonFaDanni:
    def test_due_nomi_vicini_si_proteggono(self) -> None:
        # Il caso che rende pericoloso tutto questo modulo: se Clotilde e
        # Matilde stanno entrambe nel glossario, "Motilde" non diventa nessuna
        # delle due invece di diventare quella sbagliata.
        fuori, cambi = correggi(
            "ha risposto Motilde", ["Clotilde", "Matilde"], livello="aggressivo"
        )
        assert fuori == "ha risposto Motilde"
        assert cambi == []

    def test_una_parola_comune_non_diventa_un_nome(self) -> None:
        # «totale» dista una lettera da «Tonale»: senza il segnale della
        # maiuscola, ogni preventivo diventerebbe un'automobile.
        fuori, _ = correggi("il totale della fattura", ["Tonale"], livello="medio")
        assert fuori == "il totale della fattura"

    def test_senza_maiuscola_non_si_indovina(self) -> None:
        # È la regola che rende innocuo il livello aggressivo sulle parole
        # comuni. Il prezzo: una storpiatura minuscola non viene corretta.
        fuori, _ = correggi("ne parlava cotilde", ["Clotilde"], livello="aggressivo")
        assert fuori == "ne parlava cotilde"

    def test_ma_cio_che_combacia_si_corregge_lo_stesso(self) -> None:
        # Qui non si sta indovinando niente: è la stessa parola, scritta senza
        # maiuscola. Rimetterla a posto non può sbagliare.
        fuori, _ = correggi("ne parlava clotilde", ["Clotilde"])
        assert fuori == "ne parlava Clotilde"

    def test_glossario_vuoto_o_testo_vuoto(self) -> None:
        assert correggi("qualcosa", []) == ("qualcosa", [])
        assert correggi("", ["Clotilde"]) == ("", [])

    def test_termini_vuoti_vengono_ignorati(self) -> None:
        fuori, cambi = correggi("il preventivo", ["", "   "])
        assert (fuori, cambi) == ("il preventivo", [])


class TestLivelliPiuLarghi:
    def test_medio_arriva_a_tilde(self) -> None:
        fuori, _ = correggi("l'ha detto Tilde", ["Clotilde"], livello="medio")
        assert fuori == "l'ha detto Clotilde"

    def test_medio_non_arriva_a_protile(self) -> None:
        fuori, _ = correggi("l'ha detto Protile", ["Clotilde"], livello="medio")
        assert fuori == "l'ha detto Protile"

    def test_aggressivo_arriva_a_protile(self) -> None:
        fuori, cambi = correggi("l'ha detto Protile", ["Clotilde"], livello="aggressivo")
        assert fuori == "l'ha detto Clotilde"
        assert cambi[0].trovato == "Protile"

    @pytest.mark.parametrize("storpiatura", ["Tilde", "Cotilde", "Protile"])
    def test_le_tre_forme_della_stessa_call_tornano_una(self, storpiatura: str) -> None:
        fuori, _ = correggi(f"ne parlava {storpiatura}", ["Clotilde"], livello="aggressivo")
        assert fuori == "ne parlava Clotilde"

    def test_un_livello_inventato_ricade_sul_prudente(self) -> None:
        fuori, _ = correggi("l'ha detto Tilde", ["Clotilde"], livello="fantasia")
        assert fuori == "l'ha detto Tilde"


class TestFraseIntera:
    def test_piu_correzioni_nella_stessa_frase(self) -> None:
        fuori, cambi = correggi(
            "Giulio manda il preventivo a Cotilde entro venerdi",
            ["Giulia", "Clotilde"],
        )
        assert fuori == "Giulia manda il preventivo a Clotilde entro venerdi"
        assert [c.termine for c in cambi] == ["Giulia", "Clotilde"]

    def test_la_punteggiatura_resta_dov_era(self) -> None:
        fuori, _ = correggi("Sì, Cotilde: manda tu?", ["Clotilde"])
        assert fuori == "Sì, Clotilde: manda tu?"

    def test_un_termine_di_due_parole(self) -> None:
        fuori, cambi = correggi("il contratto con banca sela", ["Banca Sella"])
        assert fuori == "il contratto con Banca Sella"
        assert cambi[0].trovato == "banca sela"

    def test_il_termine_lungo_vince_su_quello_corto(self) -> None:
        # Con entrambi nel glossario, «Sella» da solo non deve prendersi la
        # seconda parola lasciando "banca" com'era.
        fuori, _ = correggi("firmato con banca sella", ["Sella", "Banca Sella"])
        assert fuori == "firmato con Banca Sella"

    def test_gli_indici_puntano_al_testo_di_partenza(self) -> None:
        testo = "chiedi a Cotilde"
        _, cambi = correggi(testo, ["Clotilde"])
        c = cambi[0]
        assert testo[c.inizio : c.fine] == "Cotilde"


class TestDentroLaRegistrazione:
    """Il glossario applicato dove serve: fra il modello e il database."""

    def _recorder(self, tmp_path: Path, conf: dict):
        from scriba_core.db.store import Store
        from scriba_core.recorder import Recorder
        from scriba_core.settings import Settings

        impostazioni = tmp_path / "impostazioni.json"
        impostazioni.write_text(json.dumps({"stt": conf}), encoding="utf-8")
        store = Store(tmp_path / "prova.sqlite")
        rec = Recorder(
            engine=type("E", (), {"name": "finto"})(),
            store=store,
            audio_dir=tmp_path / "audio",
            settings=Settings(impostazioni),
        )
        rec.session_id = store.create_session(0, titolo="Riunione")
        rec._glossario = rec._termini_glossario()
        rec._glossario_livello = conf.get("glossario_livello", "prudente")
        return rec

    def test_il_nome_arriva_corretto_al_database(self, tmp_path: Path) -> None:
        rec = self._recorder(tmp_path, {"glossario": ["Clotilde"], "glossario_clienti": False})
        rec._handle_event(
            TranscriptEvent("mic", 0, 2_000, "manda il preventivo a Cotilde", is_final=True)
        )
        seg = rec.store.segments(rec.session_id)[0]
        assert seg.testo == "manda il preventivo a Clotilde"
        # L'originale si conserva: l'app sta mettendo in bocca a qualcuno una
        # parola che il modello non ha sentito, e deve restare verificabile.
        assert seg.testo_originale == "manda il preventivo a Cotilde"

    def test_senza_correzioni_non_si_scrive_nessun_originale(self, tmp_path: Path) -> None:
        rec = self._recorder(tmp_path, {"glossario": ["Clotilde"], "glossario_clienti": False})
        rec._handle_event(TranscriptEvent("mic", 0, 2_000, "va bene così", is_final=True))
        assert rec.store.segments(rec.session_id)[0].testo_originale is None

    def test_i_provvisori_non_si_toccano(self, tmp_path: Path) -> None:
        # Una correzione che compare e sparisce mentre si legge è peggio del
        # nome sbagliato: sui provvisori il testo cambia a ogni ipotesi.
        rec = self._recorder(tmp_path, {"glossario": ["Clotilde"], "glossario_clienti": False})
        rec._handle_event(TranscriptEvent("mic", 0, 2_000, "a Cotilde", is_final=False))
        assert rec.store.segments(rec.session_id)[0].testo == "a Cotilde"

    def test_i_clienti_entrano_da_soli_nel_glossario(self, tmp_path: Path) -> None:
        rec = self._recorder(tmp_path, {"glossario": [], "glossario_clienti": True})
        rec.store.crea_cliente("Clotilde Ferrari")
        rec._glossario = rec._termini_glossario()
        assert "Clotilde Ferrari" in rec._glossario

    def test_si_possono_lasciare_fuori(self, tmp_path: Path) -> None:
        rec = self._recorder(tmp_path, {"glossario": [], "glossario_clienti": False})
        rec.store.crea_cliente("Clotilde Ferrari")
        assert rec._termini_glossario() == []

    def test_la_ricerca_trova_il_nome_corretto(self, tmp_path: Path) -> None:
        # È il punto di tutto il glossario: cercare «Clotilde» nell'archivio
        # deve trovare la call in cui il modello aveva scritto «Cotilde».
        rec = self._recorder(tmp_path, {"glossario": ["Clotilde"], "glossario_clienti": False})
        rec._handle_event(
            TranscriptEvent("mic", 0, 2_000, "il preventivo di Cotilde", is_final=True)
        )
        assert [r["testo"] for r in rec.store.search("Clotilde")] == ["il preventivo di Clotilde"]
