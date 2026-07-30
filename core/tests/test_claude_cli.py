"""Test del provider che usa l'abbonamento Claude via riga di comando.

Le tre accortezze verificate qui — niente `--bare`, chiave API tolta
dall'ambiente, `--strict-mcp-config` — non danno errore se sbagliate: cambiano
in silenzio chi paga o cosa il modello può fare. Per questo hanno un test.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.llm.base import LLMError  # noqa: E402
from scriba_core.llm.claude_cli import ClaudeCliProvider, _estrai_json  # noqa: E402


def busta(risultato: str, **extra) -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": risultato,
            "usage": {"input_tokens": 1200, "output_tokens": 300},
            "total_cost_usd": 0.17,
            "modelUsage": {"claude-sonnet-5": {}},
            **extra,
        }
    )


@pytest.fixture()
def chiamata(monkeypatch):
    """Cattura il comando e l'ambiente con cui `claude` verrebbe eseguito."""
    catturato = {}

    def finto_run(comando, **kwargs):
        catturato["comando"] = comando
        catturato["env"] = kwargs.get("env", {})
        catturato["cwd"] = kwargs.get("cwd")
        catturato["input"] = kwargs.get("input")
        # Le istruzioni arrivano da un file: si legge finché la cartella
        # temporanea esiste, cioè adesso.
        if "--system-prompt-file" in comando:
            percorso = comando[comando.index("--system-prompt-file") + 1]
            catturato["istruzioni"] = Path(percorso).read_text(encoding="utf-8")
        return subprocess.CompletedProcess(comando, 0, catturato.get("stdout", busta("ciao")), "")

    monkeypatch.setattr(subprocess, "run", finto_run)
    monkeypatch.setattr("shutil.which", lambda _: "C:/fake/claude.exe")
    return catturato


class TestChiPaga:
    """Errori che non si vedono: la risposta arriva lo stesso, ma la paghi."""

    def test_la_chiave_api_viene_tolta_dall_ambiente(self, chiamata, monkeypatch) -> None:
        # Se `claude` trova la chiave nell'ambiente la usa, e la chiamata finisce
        # fatturata sull'API invece che sull'abbonamento.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-qualcosa")
        ClaudeCliProvider().complete(system="s", user="u")
        assert "ANTHROPIC_API_KEY" not in chiamata["env"]

    def test_anche_il_token_di_autenticazione(self, chiamata, monkeypatch) -> None:
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token")
        ClaudeCliProvider().complete(system="s", user="u")
        assert "ANTHROPIC_AUTH_TOKEN" not in chiamata["env"]

    def test_mai_bare(self, chiamata) -> None:
        # `--bare` disabilita OAuth: stesso effetto, la chiamata viene fatturata.
        ClaudeCliProvider().complete(system="s", user="u")
        assert "--bare" not in chiamata["comando"]

    def test_il_costo_riportato_e_zero(self, chiamata) -> None:
        # Il CLI riporta sempre una stima di quanto sarebbe costato via API.
        # Riportarla farebbe credere di aver speso quella cifra.
        assert ClaudeCliProvider().complete(system="s", user="u").cost_usd == 0.0


class TestIsolamento:
    def test_gli_mcp_dell_utente_non_vengono_ereditati(self, chiamata) -> None:
        # Senza, il processo figlio eredita i server MCP configurati e puo'
        # mettersi a chiamare servizi esterni per conto suo.
        ClaudeCliProvider().complete(system="s", user="u")
        assert "--strict-mcp-config" in chiamata["comando"]

    def test_gli_strumenti_sono_vietati(self, chiamata) -> None:
        # Riassumere una trascrizione non richiede disco ne' rete.
        ClaudeCliProvider().complete(system="s", user="u")
        i = chiamata["comando"].index("--disallowed-tools")
        vietati = chiamata["comando"][i + 1]
        for strumento in ("Bash", "Write", "Read", "WebFetch"):
            assert strumento in vietati

    def test_gira_fuori_da_una_cartella_di_progetto(self, chiamata) -> None:
        # Da una cartella di progetto verrebbe caricato il suo CLAUDE.md,
        # cambiando il comportamento in modi difficili da spiegare.
        ClaudeCliProvider().complete(system="s", user="u")
        cwd = str(chiamata["cwd"] or "")
        assert "scriba-claude-" in cwd


class TestLunghezza:
    """Windows limita la riga di comando a ~32.000 caratteri.

    Passando la trascrizione come argomento, un'ora di riunione lo superava e
    l'errore era "The filename or extension is too long" — che non lascia
    intuire la causa. Emerso alla prima analisi vera.
    """

    def test_la_trascrizione_non_finisce_nella_riga_di_comando(self, chiamata) -> None:
        trascrizione = "una battuta di riunione. " * 4000  # ~100.000 caratteri
        ClaudeCliProvider().complete(system="s", user=trascrizione)

        assert chiamata["input"] == trascrizione
        assert not any(len(str(a)) > 8000 for a in chiamata["comando"])

    def test_nemmeno_le_istruzioni_con_lo_schema(self, chiamata, tmp_path) -> None:
        # Le istruzioni contengono lo schema JSON e crescono: come argomento
        # concorrerebbero allo stesso limite.
        chiamata["stdout"] = busta('{"a": 1}')
        schema = {"type": "object", "properties": {f"campo_{i}": {} for i in range(400)}}
        ClaudeCliProvider().complete(system="s" * 5000, user="u", schema=schema)

        assert not any(len(str(a)) > 8000 for a in chiamata["comando"])
        assert "--system-prompt-file" in chiamata["comando"]

    def test_le_istruzioni_non_vengono_perse(self, chiamata) -> None:
        # Scartarle quando sono lunghe sarebbe peggio del problema: il modello
        # lavorerebbe senza sapere cosa gli si chiede.
        chiamata["stdout"] = busta('{"a": 1}')
        ClaudeCliProvider().complete(
            system="ISTRUZIONE-RICONOSCIBILE", user="u", schema={"type": "object"}
        )
        assert "ISTRUZIONE-RICONOSCIBILE" in chiamata["istruzioni"]
        assert "type" in chiamata["istruzioni"]


class TestRisposta:
    def test_il_testo_viene_restituito(self, chiamata) -> None:
        c = ClaudeCliProvider().complete(system="s", user="u")
        assert c.text == "ciao"
        assert c.tokens_in == 1200 and c.tokens_out == 300
        assert c.provider == "claude-cli"

    def test_lo_schema_finisce_nelle_istruzioni(self, chiamata) -> None:
        # Il campo strutturato della risposta non e' garantito: lo schema va
        # ripetuto nelle istruzioni.
        chiamata["stdout"] = busta('{"a": 1}')
        ClaudeCliProvider().complete(
            system="s", user="u", schema={"type": "object", "properties": {"a": {}}}
        )
        assert "properties" in chiamata["istruzioni"]

    def test_un_errore_segnalato_diventa_un_errore(self, chiamata) -> None:
        chiamata["stdout"] = json.dumps({"is_error": True, "result": "quota esaurita"})
        with pytest.raises(LLMError, match="quota esaurita"):
            ClaudeCliProvider().complete(system="s", user="u")

    def test_una_risposta_vuota_non_passa_inosservata(self, chiamata) -> None:
        chiamata["stdout"] = busta("   ")
        with pytest.raises(LLMError, match="senza contenuto"):
            ClaudeCliProvider().complete(system="s", user="u")

    def test_senza_claude_installato_lo_dice(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _: None)
        p = ClaudeCliProvider()
        assert p.available() is False
        with pytest.raises(LLMError, match="PATH"):
            p.complete(system="s", user="u")


class TestAccessoScaduto:
    """Una sessione OAuth scaduta lascia `claude` al suo posto ed eseguibile.

    È capitato su una call di un'ora: l'analisi è partita, è morta subito, e il
    messaggio mostrava 300 caratteri di JSON che tagliavano via l'unica frase
    utile — «Failed to authenticate: OAuth session expired».
    """

    # La busta vera, ridotta a quello che conta: il CLI esce con 1 e scrive
    # comunque il suo JSON su stdout, con `result` in fondo.
    BUSTA_SCADUTA = json.dumps(
        {
            "is_error": True,
            "duration_api_ms": 0,
            "num_turns": 1,
            "stop_reason": "stop_sequence",
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "terminal_reason": "api_error",
            "subtype": "success",
            "result": "Failed to authenticate: OAuth session expired and could not be refreshed",
        }
    )

    def test_il_motivo_arriva_all_utente_invece_del_json(self, chiamata, monkeypatch) -> None:
        def finto_run(comando, **kwargs):
            return subprocess.CompletedProcess(comando, 1, self.BUSTA_SCADUTA, "")

        monkeypatch.setattr(subprocess, "run", finto_run)
        with pytest.raises(LLMError) as errore:
            ClaudeCliProvider().complete(system="s", user="u")

        messaggio = str(errore.value)
        assert "claude auth login" in messaggio
        # Il JSON grezzo non è un messaggio d'errore.
        assert not messaggio.lstrip().startswith("`claude` è uscito con codice 1: {")
        assert "duration_api_ms" not in messaggio

    def test_un_altro_errore_resta_quello_che_e(self, chiamata, monkeypatch) -> None:
        busta_quota = json.dumps({"is_error": True, "result": "Usage limit reached"})

        def finto_run(comando, **kwargs):
            return subprocess.CompletedProcess(comando, 1, busta_quota, "")

        monkeypatch.setattr(subprocess, "run", finto_run)
        with pytest.raises(LLMError, match="Usage limit reached"):
            ClaudeCliProvider().complete(system="s", user="u")

    def test_lo_dice_prima_di_far_partire_l_analisi(self, monkeypatch) -> None:
        # Senza questo controllo l'abbonamento risulta disponibile solo perché
        # l'eseguibile c'è, e il guasto si scopre a analisi avviata.
        monkeypatch.setattr("shutil.which", lambda _: "C:/fake/claude.exe")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda comando, **kwargs: subprocess.CompletedProcess(
                comando, 0, json.dumps({"loggedIn": False, "authMethod": "none"}), ""
            ),
        )
        assert ClaudeCliProvider().available() is False

    def test_collegato_resta_disponibile(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _: "C:/fake/claude.exe")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda comando, **kwargs: subprocess.CompletedProcess(
                comando, 0, json.dumps({"loggedIn": True, "authMethod": "oauth"}), ""
            ),
        )
        assert ClaudeCliProvider().available() is True

    def test_un_controllo_che_non_riesce_non_blocca(self, monkeypatch) -> None:
        # Una versione del CLI senza `auth status` non deve far sembrare rotto un
        # abbonamento che funziona: nel dubbio si prova.
        monkeypatch.setattr("shutil.which", lambda _: "C:/fake/claude.exe")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda comando, **kwargs: subprocess.CompletedProcess(
                comando, 1, "", "error: unknown command 'auth'"
            ),
        )
        assert ClaudeCliProvider().available() is True

    def test_la_chiave_api_non_falsa_il_controllo(self, monkeypatch) -> None:
        # Se il controllo la vedesse, direbbe «collegato» per merito di una
        # chiave che l'analisi poi toglie comunque dall'ambiente.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-qualcosa")
        monkeypatch.setattr("shutil.which", lambda _: "C:/fake/claude.exe")
        visto = {}

        def finto_run(comando, **kwargs):
            visto["env"] = kwargs.get("env", {})
            return subprocess.CompletedProcess(comando, 0, json.dumps({"loggedIn": True}), "")

        monkeypatch.setattr(subprocess, "run", finto_run)
        ClaudeCliProvider().available()
        assert "ANTHROPIC_API_KEY" not in visto["env"]


class TestEstrazioneJson:
    """Qui manca la grammatica che in locale rende il JSON impossibile da
    sbagliare: la risposta va ripulita."""

    def test_json_pulito(self) -> None:
        assert _estrai_json('{"a": 1}') == {"a": 1}

    def test_dentro_un_blocco_di_codice(self) -> None:
        assert _estrai_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_blocco_senza_linguaggio(self) -> None:
        assert _estrai_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_preceduto_da_una_frase(self) -> None:
        assert _estrai_json('Ecco il risultato:\n{"a": 1}') == {"a": 1}

    def test_senza_json_solleva(self) -> None:
        with pytest.raises(LLMError):
            _estrai_json("non c'e' nulla qui")
