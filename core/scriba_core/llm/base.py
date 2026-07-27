"""Interfaccia comune ai modelli di linguaggio.

Locale e API stanno dietro la stessa forma. Il locale è il predefinito: una call
di lavoro contiene nomi, cifre e questioni che non c'è motivo di mandare fuori se
la macchina può fare il lavoro da sola.

L'unica cosa che si pretende da un provider è di restituire JSON conforme a uno
schema. Chi gira in locale lo ottiene vincolando la generazione con una
grammatica: i token che romperebbero lo schema hanno probabilità zero, quindi
l'output *non può* essere malformato. Le API lo ottengono con i loro meccanismi
di structured output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(RuntimeError):
    """Il provider non è riuscito a produrre una risposta utilizzabile."""


@dataclass(frozen=True)
class Completion:
    text: str
    data: dict[str, Any] | None = None
    model: str = ""
    provider: str = ""
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> Completion:
        """Genera una risposta. Con `schema`, il risultato è JSON conforme."""
        ...

    def available(self) -> bool:
        """Il provider è utilizzabile adesso (chiave presente, server acceso)."""
        ...
