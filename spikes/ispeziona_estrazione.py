"""Mostra cosa produce davvero il modello in fase di estrazione.

Serve quando l'estrazione fallisce per troncamento: invece di alzare il tetto
dei token alla cieca, si guarda dove finiscono.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from scriba_core.ai import prompts  # noqa: E402
from scriba_core.ai.analyze import formatta_segmenti  # noqa: E402
from scriba_core.db.store import Segment  # noqa: E402
from scriba_core.llm.providers import LocalProvider  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prova_analisi import RIUNIONE  # noqa: E402


def main() -> int:
    segmenti = [
        Segment(
            id=i + 1,
            session_id=1,
            source="mic" if chi == "me" else "loopback",
            t_start_ms=int(minuti * 60_000),
            t_end_ms=int(minuti * 60_000) + 2000,
            testo=testo,
            is_final=True,
            revision=0,
        )
        for i, (minuti, chi, testo) in enumerate(RIUNIONE)
    ]

    provider = LocalProvider()
    if not provider.available():
        print("llama-server non risponde.")
        return 1

    print(f"Finestra: {len(segmenti)} righe\n")

    # Chiamata diretta invece che tramite il provider: quando la risposta viene
    # troncata il provider solleva un errore e butta via il testo, che e'
    # esattamente quello che serve guardare.
    import httpx

    r = httpx.post(
        f"{provider.base_url}/v1/chat/completions",
        json={
            "model": provider.model,
            "messages": [
                {"role": "system", "content": prompts.SYSTEM_ESTRAZIONE},
                {
                    "role": "user",
                    "content": prompts.EXTRACT_CANDIDATES_PROMPT.format(
                        finestra=formatta_segmenti(segmenti)
                    ),
                },
            ],
            "max_tokens": 6000,
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "risposta",
                    "schema": prompts.SCHEMA_CANDIDATES,
                    "strict": True,
                },
            },
        },
        timeout=httpx.Timeout(3600.0, connect=10.0),
    )
    body = r.json()
    scelta = body["choices"][0]
    testo = scelta["message"].get("content") or ""
    uso = body.get("usage", {})

    print(f"motivo fine : {scelta.get('finish_reason')}")
    print(f"token in    : {uso.get('prompt_tokens')}")
    print(f"token out   : {uso.get('completion_tokens')}")
    print(f"caratteri   : {len(testo)}\n")
    print("--- risposta grezza (ultimi 1500 caratteri) ---")
    print(testo[-1500:])

    try:
        dati = json.loads(testo)
    except json.JSONDecodeError:
        print("\n(JSON incompleto: il conteggio dei candidati non e' possibile)")
        print(f"occorrenze di 'temp_id': {testo.count('temp_id')}")
        return 1

    if dati:
        candidati = dati.get("candidati", [])
        print(f"\n--- {len(candidati)} candidati ---")
        for cand in candidati:
            print(f"\n{json.dumps(cand, ensure_ascii=False, indent=2)}")
        # Quanto costa ciascuno, per capire dove finiscono i token.
        if candidati:
            medio = len(json.dumps(candidati, ensure_ascii=False)) / len(candidati)
            print(f"\ncaratteri medi per candidato: {medio:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
