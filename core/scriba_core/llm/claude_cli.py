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


class ClaudeCliProvider:
    """Parla con Claude attraverso l'eseguibile `claude`."""

    name = "claude-cli"

    def __init__(self, model: str = "sonnet", timeout_s: float = 900.0) -> None:
        self.model = model
        self.timeout_s = timeout_s

    def available(self) -> bool:
        return shutil.which("claude") is not None

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

        env = os.environ.copy()
        # Se la trova, la usa: la chiamata finirebbe fatturata sull'API invece
        # che sull'abbonamento, in silenzio.
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)

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

        if esito.returncode != 0:
            dettaglio = (esito.stderr or esito.stdout or "").strip()
            raise LLMError(f"`claude` è uscito con codice {esito.returncode}: {dettaglio[:300]}")

        try:
            busta = json.loads(esito.stdout)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Risposta di `claude` illeggibile: {esito.stdout[:200]}") from exc

        if busta.get("is_error"):
            raise LLMError(f"`claude` ha segnalato un errore: {busta.get('result', '')[:300]}")

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
