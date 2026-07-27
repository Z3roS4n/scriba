"""I tre provider: locale, Anthropic, OpenAI.

Stanno insieme perché parlano quasi la stessa lingua — due su tre sono
letteralmente l'API OpenAI — e tenerli affiancati rende evidente dove
divergono.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .base import Completion, LLMError, LLMProvider

# Generoso di proposito. Un modello locale su CPU produce ~4,5 token al secondo:
# una singola estrazione può richiedere una decina di minuti, e interromperla a
# metà significa buttare via tutto il lavoro fatto fino a quel punto.
TIMEOUT = httpx.Timeout(1800.0, connect=10.0)


def _controlla_troncamento(motivo: str | None) -> None:
    """Distingue una risposta incompleta da una malformata.

    Sono due guasti diversi con due rimedi diversi, e confonderli fa perdere
    tempo: un JSON tagliato a metà perché sono finiti i token disponibili
    somiglia molto a un JSON scritto male, ma si risolve alzando un numero.
    """
    if motivo in ("length", "max_tokens"):
        raise LLMError(
            "La risposta è stata interrotta perché ha raggiunto il limite di token. "
            "Il JSON è incompleto: serve alzare max_tokens."
        )


def _estrai_json(testo: str) -> dict[str, Any]:
    """Ricava l'oggetto JSON da una risposta.

    Con la generazione vincolata il testo è già JSON puro. Le API a volte lo
    incorniciano in un blocco markdown nonostante le istruzioni, quindi si
    ritaglia dalla prima graffa all'ultima invece di arrendersi.
    """
    testo = testo.strip()
    if testo.startswith("```"):
        testo = testo.split("```")[1]
        if testo.startswith("json"):
            testo = testo[4:]
    inizio, fine = testo.find("{"), testo.rfind("}")
    if inizio == -1 or fine <= inizio:
        raise LLMError(f"Risposta senza JSON: {testo[:200]}")
    try:
        return json.loads(testo[inizio : fine + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON non valido: {exc}") from exc


class LocalProvider(LLMProvider):
    """Parla con `llama-server`, che espone l'API OpenAI.

    Si spedisce il binario invece di dipendere da Ollama o LM Studio installati
    dall'utente: così la versione del motore la controlliamo noi, e abbiamo
    accesso diretto alla generazione vincolata da schema.
    """

    name = "local"

    def __init__(self, base_url: str = "http://127.0.0.1:8080", model: str = "locale") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if schema is not None:
            # Vincola la generazione: i token che violerebbero lo schema hanno
            # probabilità zero. Costa un 30-80% di velocità e in cambio toglie
            # di mezzo un'intera categoria di errori.
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "risposta", "schema": schema, "strict": True},
            }

        try:
            r = httpx.post(f"{self.base_url}/v1/chat/completions", json=payload, timeout=TIMEOUT)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Il modello locale non risponde: {exc}") from exc

        body = r.json()
        scelta = body["choices"][0]
        if schema is not None:
            _controlla_troncamento(scelta.get("finish_reason"))
        messaggio = scelta["message"]
        testo = messaggio.get("content") or ""
        if not testo.strip():
            # I modelli con ragionamento separano il pensiero dalla risposta. Se
            # la risposta e' vuota hanno esaurito i token pensando: si ripiega
            # sul ragionamento, che almeno contiene qualcosa, invece di
            # restituire il nulla. Il rimedio vero e' avviare il server con
            # --reasoning-budget 0, che per l'estrazione strutturata e' solo
            # spreco.
            testo = messaggio.get("reasoning_content") or ""

        uso = body.get("usage", {})
        return Completion(
            text=testo,
            data=_estrai_json(testo) if schema else None,
            model=self.model,
            provider=self.name,
            tokens_in=uso.get("prompt_tokens"),
            tokens_out=uso.get("completion_tokens"),
            cost_usd=0.0,
        )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    # $ per milione di token, ingresso/uscita.
    PREZZI = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (3.0, 15.0)}

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-5") -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> Completion:
        if not self.api_key:
            raise LLMError("Manca la chiave Anthropic.")

        if schema is not None:
            # Si chiede lo schema nel prompt e si usa il precompilato della
            # risposta: il modello riprende da "{" e non ha modo di premettere
            # frasi di cortesia prima del JSON.
            user = f"{user}\n\nRispondi con un JSON conforme a questo schema:\n{json.dumps(schema, ensure_ascii=False)}"

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if schema is not None:
            payload["messages"].append({"role": "assistant", "content": "{"})

        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                timeout=TIMEOUT,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Anthropic: {exc}") from exc

        body = r.json()
        testo = "".join(b.get("text", "") for b in body.get("content", []))
        if schema is not None:
            _controlla_troncamento(body.get("stop_reason"))
            testo = "{" + testo  # si restituisce la graffa che avevamo messo noi

        uso = body.get("usage", {})
        tin, tout = uso.get("input_tokens"), uso.get("output_tokens")
        pin, pout = self.PREZZI.get(self.model, (0.0, 0.0))
        return Completion(
            text=testo,
            data=_estrai_json(testo) if schema else None,
            model=self.model,
            provider=self.name,
            tokens_in=tin,
            tokens_out=tout,
            cost_usd=((tin or 0) * pin + (tout or 0) * pout) / 1_000_000,
        )


class OpenAIProvider(LLMProvider):
    name = "openai"

    PREZZI = {"gpt-5": (1.25, 10.0), "gpt-5-mini": (0.25, 2.0)}

    def __init__(self, api_key: str | None = None, model: str = "gpt-5-mini") -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> Completion:
        if not self.api_key:
            raise LLMError("Manca la chiave OpenAI.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens": max_tokens,
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "risposta", "schema": schema, "strict": True},
            }

        try:
            r = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenAI: {exc}") from exc

        body = r.json()
        scelta = body["choices"][0]
        if schema is not None:
            _controlla_troncamento(scelta.get("finish_reason"))
        testo = scelta["message"]["content"] or ""
        uso = body.get("usage", {})
        tin, tout = uso.get("prompt_tokens"), uso.get("completion_tokens")
        pin, pout = self.PREZZI.get(self.model, (0.0, 0.0))
        return Completion(
            text=testo,
            data=_estrai_json(testo) if schema else None,
            model=self.model,
            provider=self.name,
            tokens_in=tin,
            tokens_out=tout,
            cost_usd=((tin or 0) * pin + (tout or 0) * pout) / 1_000_000,
        )


def costruisci(config: dict[str, Any]) -> LLMProvider:
    """Crea il provider indicato dalle impostazioni."""
    tipo = config.get("provider", "local")
    if tipo == "local":
        return LocalProvider(
            base_url=config.get("base_url", "http://127.0.0.1:8080"),
            model=config.get("model", "locale"),
        )
    if tipo == "anthropic":
        return AnthropicProvider(config.get("api_key"), config.get("model", "claude-sonnet-5"))
    if tipo == "openai":
        return OpenAIProvider(config.get("api_key"), config.get("model", "gpt-5-mini"))
    raise LLMError(f"Provider sconosciuto: {tipo}")
