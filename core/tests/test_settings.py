"""Test delle impostazioni.

Il comportamento che conta: non perdere una chiave API per sbaglio, e non
mostrarla a chi non deve vederla.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.settings import Settings  # noqa: E402


def test_valori_predefiniti(tmp_path: Path) -> None:
    s = Settings(tmp_path / "s.json")
    # Il locale e' il predefinito: le call non escono dalla macchina se non
    # serve.
    assert s.llm()["provider"] == "local"


def test_le_modifiche_si_conservano(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    Settings(path).aggiorna({"llm": {"provider": "anthropic", "api_key": "segreto"}})
    assert Settings(path).llm()["api_key"] == "segreto"


def test_una_chiave_vuota_non_cancella_quella_salvata(tmp_path: Path) -> None:
    # L'interfaccia rimanda l'intero blocco impostazioni a ogni salvataggio, e
    # il campo della chiave e' vuoto perche' non la mostriamo mai: interpretarlo
    # come "cancellala" farebbe perdere la chiave a chi cambia il modello.
    path = tmp_path / "s.json"
    s = Settings(path)
    s.aggiorna({"llm": {"api_key": "segreto"}})
    s.aggiorna({"llm": {"model": "gpt-5-mini", "api_key": ""}})
    assert s.llm()["api_key"] == "segreto"
    assert s.llm()["model"] == "gpt-5-mini"


def test_la_chiave_non_esce_verso_l_interfaccia(tmp_path: Path) -> None:
    s = Settings(tmp_path / "s.json")
    s.aggiorna({"llm": {"api_key": "segreto"}})
    pubbliche = s.tutto()
    assert "api_key" not in pubbliche["llm"]
    assert pubbliche["llm"]["api_key_presente"] is True
    # Ma internamente serve davvero.
    assert s.tutto(con_segreti=True)["llm"]["api_key"] == "segreto"


def test_un_file_rovinato_non_impedisce_l_avvio(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text("{ questo non e' json", encoding="utf-8")
    assert Settings(path).llm()["provider"] == "local"


def test_le_chiavi_nuove_arrivano_ai_file_vecchi(tmp_path: Path) -> None:
    # Un file salvato da una versione precedente non deve restare senza le
    # impostazioni aggiunte dopo.
    path = tmp_path / "s.json"
    path.write_text('{"llm": {"provider": "openai"}}', encoding="utf-8")
    s = Settings(path)
    assert s.llm()["provider"] == "openai"
    assert "base_url" in s.llm()
