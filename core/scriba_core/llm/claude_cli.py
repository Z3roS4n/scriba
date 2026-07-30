"""Analisi tramite l'abbonamento Claude, usando la riga di comando `claude`.

Chi ha già un abbonamento paga due volte se l'applicazione usa l'API: qui si
riusa quello, facendo girare `claude -p` in modo non interattivo.

Tre accortezze, imparate sul campo in un altro progetto e non ovvie leggendo la
documentazione. Sbagliarne una non dà errore: cambia in silenzio chi paga o cosa
il modello può fare.

1. **Niente `--bare`.** Disabilita l'autenticazione OAuth, e la chiamata finisce
   fatturata sull'API invece che sull'abbonamento.
2. **`ANTHROPIC_API_KEY` va tolta dall'ambiente del processo figlio**, per lo
   stesso motivo: se la trova, la usa.
3. **`--strict-mcp-config`**, altrimenti il processo figlio eredita i server MCP
   configurati dall'utente e può mettersi a chiamare servizi esterni per conto
   suo.

Nota sul costo: `total_cost_usd` nella risposta è sempre valorizzato anche in
abbonamento. È una stima di quanto sarebbe costato via API, non un addebito.

**L'eseguibile nel PATH non basta.** Un abbonamento scollegato (sessione OAuth
scaduta) lascia `claude` al suo posto e perfettamente eseguibile: l'analisi
partiva, e moriva subito dopo con un errore che non diceva cosa fare. Per questo
`available()` chiede alla CLI stessa se è collegata, e l'errore che ne esce
riporta la frase di Claude invece della busta JSON grezza.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .base import Completion, LLMError

log = logging.getLogger(__name__)

# Nessuno di questi serve per riassumere una trascrizione, e concederli
# significherebbe dare a un processo non sorvegliato accesso al disco e alla
# rete.
STRUMENTI_VIETATI = "Bash,Write,Edit,NotebookEdit,Read,Glob,Grep,WebSearch,WebFetch,Task"

# Come si riconosce un guasto di accesso fra i messaggi della CLI. Sono frasi
# sue, quindi in inglese.
_SEGNALI_ACCESSO = (
    "authenticate",
    "oauth",
    "not logged in",
    "unauthorized",
    "invalid api key",
    "/login",
)

RIMEDIO_ACCESSO = (
    "L'abbonamento Claude non è più collegato: la sessione è scaduta. "
    "Apri un terminale, lancia `claude auth login`, poi rilancia l'analisi."
)


def _ambiente() -> dict[str, str]:
    """L'ambiente del processo figlio, senza le credenziali dell'API.

    Se `claude` le trova, le usa: la chiamata finirebbe fatturata sull'API
    invece che sull'abbonamento, in silenzio. Vale anche per il controllo di
    `available()`, altrimenti si direbbe «collegato» per merito di una chiave
    che poi togliamo comunque.
    """
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


class ClaudeCliProvider:
    """Parla con Claude attraverso l'eseguibile `claude`."""

    name = "claude-cli"

    def __init__(self, model: str = "sonnet", timeout_s: float = 900.0) -> None:
        self.model = model
        self.timeout_s = timeout_s

    def available(self) -> bool:
        return shutil.which("claude") is not None and self._collegato()

    def _collegato(self) -> bool:
        """Se l'abbonamento risulta ancora collegato alla CLI.

        Serve a scoprirlo *prima*: l'eseguibile c'è ed è eseguibile anche con la
        sessione scaduta, quindi senza questo controllo l'analisi parte e muore
        dopo — e su una call di un'ora si scopre dopo aver aspettato.

        False solo quando la CLI dice di sé che non è collegata. Un controllo che
        non riesce (una versione senza `auth status`, un timeout) non deve far
        sembrare rotto un abbonamento che funziona: nel dubbio si prova, e se non
        va sarà l'errore dell'analisi a dirlo.
        """
        try:
            esito = subprocess.run(
                ["claude", "auth", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_ambiente(),
                timeout=20.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            stato = json.loads((esito.stdout or "").strip())
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return True
        if not isinstance(stato, dict):
            return True
        return stato.get("loggedIn") is not False

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> Completion:
        if not self.available():
            raise LLMError(
                "L'eseguibile `claude` non è nel PATH. Installa Claude Code, "
                "oppure scegli un altro provider nelle impostazioni."
            )

        istruzioni = system
        prompt = user
        if schema is not None:
            # Lo schema si mette nel prompt e non ci si affida al campo
            # strutturato della risposta: non è garantito, e quando manca resta
            # solo testo libero da interpretare.
            istruzioni += (
                "\n\nRispondi esclusivamente con JSON valido conforme a questo schema, "
                "senza testo introduttivo e senza racchiuderlo in un blocco di codice:\n"
                + json.dumps(schema, ensure_ascii=False)
            )

        # Il prompt viaggia sullo standard input, non come argomento. Windows
        # limita la riga di comando a circa 32.000 caratteri, e la trascrizione
        # di un'ora di riunione la supera: l'errore che ne veniva fuori era
        # "The filename or extension is too long", che non lascia intuire la
        # causa vera.
        comando = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--strict-mcp-config",
            "--disallowed-tools",
            STRUMENTI_VIETATI,
        ]
        if self.model:
            comando += ["--model", self.model]

        env = _ambiente()

        try:
            # Si esegue in una cartella vuota: da una cartella di progetto,
            # `claude` caricherebbe il CLAUDE.md e le impostazioni di quel
            # progetto, cambiando il comportamento in modi difficili da spiegare.
            with tempfile.TemporaryDirectory(prefix="scriba-claude-") as neutra:
                # Anche le istruzioni passano da un file: contengono lo schema
                # JSON e crescono, e come argomento concorrerebbero allo stesso
                # limite di lunghezza della riga di comando.
                percorso_istruzioni = Path(neutra) / "istruzioni.txt"
                percorso_istruzioni.write_text(istruzioni, encoding="utf-8")

                esito = subprocess.run(
                    comando + ["--system-prompt-file", str(percorso_istruzioni)],
                    input=prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    cwd=neutra,
                    timeout=self.timeout_s,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
        except subprocess.TimeoutExpired as exc:
            raise LLMError(
                f"`claude` non ha risposto entro {self.timeout_s / 60:.0f} minuti."
            ) from exc
        except OSError as exc:
            raise LLMError(f"Impossibile eseguire `claude`: {exc}") from exc

        busta = _busta(esito.stdout)
        if esito.returncode != 0 or (busta is not None and busta.get("is_error")):
            raise _errore_del_cli(esito, busta)
        if busta is None:
            raise LLMError(f"Risposta di `claude` illeggibile: {esito.stdout[:200]}")

        testo = (busta.get("result") or "").strip()
        if not testo:
            raise LLMError("`claude` ha risposto senza contenuto.")

        uso = busta.get("usage") or {}
        return Completion(
            text=testo,
            data=_estrai_json(testo) if schema else None,
            model=_modello_usato(busta) or self.model,
            provider=self.name,
            tokens_in=uso.get("input_tokens"),
            tokens_out=uso.get("output_tokens"),
            # Sempre 0: la stima che il CLI riporta è quanto sarebbe costato via
            # API, e riportarla farebbe credere di aver speso quella cifra.
            cost_usd=0.0,
        )


def _busta(stdout: str | None) -> dict[str, Any] | None:
    """La busta JSON del CLI, se l'ha scritta."""
    try:
        letto = json.loads((stdout or "").strip())
    except json.JSONDecodeError:
        return None
    return letto if isinstance(letto, dict) else None


def _errore_del_cli(
    esito: subprocess.CompletedProcess[str], busta: dict[str, Any] | None
) -> LLMError:
    """Il motivo leggibile, non la busta grezza.

    `claude` può uscire con codice diverso da zero e **comunque** aver scritto la
    sua busta su stdout: il perché sta in `result`. Mostrare il JSON tagliato a
    300 caratteri lo nasconde — è successo con una sessione OAuth scaduta, che
    l'utente ha letto come «uscito con codice 1: {"is_error":true,
    "duration_api_ms":0,…», dove la frase che diceva cosa fare cadeva appena
    oltre il taglio.
    """
    motivo = ""
    if busta is not None:
        motivo = str(busta.get("result") or busta.get("error") or "").strip()
    if not motivo:
        motivo = (esito.stderr or "").strip() or (esito.stdout or "").strip()

    if any(segnale in motivo.lower() for segnale in _SEGNALI_ACCESSO):
        return LLMError(f"{RIMEDIO_ACCESSO} (Claude ha detto: {motivo[:200]})")
    if esito.returncode != 0:
        return LLMError(f"`claude` è uscito con codice {esito.returncode}: {motivo[:300]}")
    return LLMError(f"`claude` ha segnalato un errore: {motivo[:300]}")


def _modello_usato(busta: dict) -> str:
    uso = busta.get("modelUsage")
    if isinstance(uso, dict) and uso:
        return next(iter(uso))
    return str(busta.get("model") or "")


def _estrai_json(testo: str) -> dict[str, Any]:
    """Ricava l'oggetto JSON dalla risposta.

    Qui non c'è una grammatica che vincoli la generazione come in locale, quindi
    la risposta può arrivare dentro un blocco di codice o preceduta da una frase
    di cortesia, nonostante le istruzioni.
    """
    ripulito = testo.strip()
    if ripulito.startswith("```"):
        righe = ripulito.splitlines()
        righe = righe[1:]
        if righe and righe[-1].strip().startswith("```"):
            righe = righe[:-1]
        ripulito = "\n".join(righe).strip()

    try:
        return json.loads(ripulito)
    except json.JSONDecodeError:
        pass

    inizio, fine = ripulito.find("{"), ripulito.rfind("}")
    if inizio >= 0 and fine > inizio:
        try:
            return json.loads(ripulito[inizio : fine + 1])
        except json.JSONDecodeError:
            pass
    raise LLMError(f"Nessun JSON valido nella risposta: {ripulito[:200]}")
