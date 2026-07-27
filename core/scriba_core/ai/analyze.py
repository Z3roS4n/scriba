"""Analisi di una call: riassunto, punti salienti, estrazione delle task.

L'estrazione delle task è il motivo per cui questo progetto esiste. In una
riunione vera il lavoro si nomina al minuto 5, la scadenza si concorda al 32 e il
responsabile si decide al 48: un'estrazione in un colpo solo o produce tre
frammenti scollegati o ne perde due terzi. Qui si fa in due passaggi — prima si
raccoglie tutto senza pretendere che sia completo, poi si ricompone — e ogni
campo si porta dietro il punto della call da cui viene.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from ..db.store import Segment, Store
from ..llm.base import Completion, LLMError, LLMProvider
from . import prompts

# Ampiezza delle finestre di estrazione. Volutamente molto sotto al contesto che
# i modelli dichiarano di reggere: la qualità del recall cala ben prima del
# limite, e su una finestra corta un modello locale se la cava quanto uno grande.
FINESTRA_TOKEN = 5_000
SOVRAPPOSIZIONE_TOKEN = 500
# L'italiano fa circa 1,6 token per parola. Stima grossolana, ma serve solo a
# decidere dove tagliare.
TOKEN_PER_PAROLA = 1.6

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


@dataclass
class Analisi:
    """Cosa è stato prodotto, e quanto è costato."""

    riassunto: str = ""
    punti_salienti: str = ""
    tasks: list[dict] = field(default_factory=list)
    scartati: list[dict] = field(default_factory=list)
    costo_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    modello: str = ""
    provider: str = ""


def formatta_segmenti(segmenti: list[Segment]) -> str:
    """Prepara la trascrizione per il modello.

    Ogni riga porta l'id del segmento: è l'aggancio con cui il modello indica le
    proprie fonti senza dover copiare il testo.
    """
    righe = []
    for s in segmenti:
        minuti, secondi = divmod(s.t_start_ms // 1000, 60)
        chi = "io" if s.source == "mic" else "altri"
        righe.append(f"[{s.id}] ({minuti:02d}:{secondi:02d}) {chi}: {s.testo}")
    return "\n".join(righe)


def finestre(segmenti: list[Segment]) -> list[list[Segment]]:
    """Spezza la trascrizione in finestre che si sovrappongono.

    La sovrapposizione serve a non perdere gli impegni enunciati a cavallo di un
    taglio, che altrimenti finirebbero divisi a metà e irriconoscibili.
    """
    if not segmenti:
        return []

    finestre_out: list[list[Segment]] = []
    corrente: list[Segment] = []
    token = 0

    for s in segmenti:
        costo = len(s.testo.split()) * TOKEN_PER_PAROLA
        if token + costo > FINESTRA_TOKEN and corrente:
            finestre_out.append(corrente)
            # Si riparte tenendo la coda della finestra appena chiusa.
            coda: list[Segment] = []
            token_coda = 0.0
            for prec in reversed(corrente):
                costo_prec = len(prec.testo.split()) * TOKEN_PER_PAROLA
                if token_coda + costo_prec > SOVRAPPOSIZIONE_TOKEN:
                    break
                coda.insert(0, prec)
                token_coda += costo_prec
            corrente, token = coda, token_coda
        corrente.append(s)
        token += costo

    if corrente:
        finestre_out.append(corrente)
    return finestre_out


class Analizzatore:
    def __init__(self, provider: LLMProvider, store: Store) -> None:
        self.provider = provider
        self.store = store

    # ------------------------------------------------------------------ utili

    def _chiedi(self, sistema: str, testo: str, schema=None, max_tokens: int = 2048) -> Completion:
        return self.provider.complete(
            system=sistema, user=testo, schema=schema, max_tokens=max_tokens
        )

    @staticmethod
    def _somma(analisi: Analisi, c: Completion) -> None:
        analisi.tokens_in += c.tokens_in or 0
        analisi.tokens_out += c.tokens_out or 0
        analisi.costo_usd += c.cost_usd or 0.0
        analisi.modello = c.model
        analisi.provider = c.provider

    # ------------------------------------------------------------- redazione

    def riassumi(self, segmenti: list[Segment]) -> Completion:
        return self._chiedi(
            prompts.SYSTEM_REDAZIONE,
            prompts.SUMMARY_PROMPT.format(trascrizione=formatta_segmenti(segmenti)),
            max_tokens=1200,
        )

    def punti_salienti(self, segmenti: list[Segment]) -> Completion:
        return self._chiedi(
            prompts.SYSTEM_REDAZIONE,
            prompts.HIGHLIGHTS_PROMPT.format(trascrizione=formatta_segmenti(segmenti)),
            max_tokens=1200,
        )

    # ------------------------------------------------------------------ task

    def candidati(self, segmenti: list[Segment]) -> tuple[list[dict], list[Completion]]:
        """Primo passaggio: raccoglie tutto, finestra per finestra."""
        tutti: list[dict] = []
        completions: list[Completion] = []

        for i, finestra in enumerate(finestre(segmenti)):
            c = self._chiedi(
                prompts.SYSTEM_ESTRAZIONE,
                prompts.EXTRACT_CANDIDATES_PROMPT.format(finestra=formatta_segmenti(finestra)),
                schema=prompts.SCHEMA_CANDIDATES,
                max_tokens=3000,
            )
            completions.append(c)
            for n, cand in enumerate((c.data or {}).get("candidati", [])):
                # Gli identificativi provvisori sono unici solo dentro la
                # finestra che li ha prodotti: senza prefisso, il passaggio di
                # unione confonderebbe candidati diversi con lo stesso nome.
                # Si costruisce un dizionario nuovo invece di modificare quello
                # ricevuto: rinominare sul posto significherebbe accumulare
                # prefissi se lo stesso oggetto passasse di qui due volte.
                tutti.append({**cand, "temp_id": f"f{i}_{cand.get('temp_id', n)}"})

        return tutti, completions

    def unisci(self, candidati: list[dict], quando: datetime) -> Completion:
        """Secondo passaggio: ricompone gli impegni sparsi.

        Riceve solo i candidati, non la trascrizione: sono poche migliaia di
        token invece di venticinquemila, e il modello può concentrarsi sul
        confronto invece di rileggere tutto.
        """
        return self._chiedi(
            prompts.SYSTEM_ESTRAZIONE,
            prompts.MERGE_TASKS_PROMPT.format(
                candidati=json.dumps(candidati, ensure_ascii=False, indent=1),
                data_riunione=quando.strftime("%Y-%m-%d"),
                giorno_settimana=GIORNI[quando.weekday()],
            ),
            schema=prompts.SCHEMA_MERGE,
            max_tokens=4000,
        )

    # --------------------------------------------------------------- insieme

    def analizza(self, session_id: int) -> Analisi:
        """Analizza una call e salva tutto nel database."""
        segmenti = self.store.segments(session_id, only_final=True)
        analisi = Analisi()
        if not segmenti:
            return analisi

        sessione = self.store.conn.execute(
            "SELECT started_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        quando = datetime.fromtimestamp((sessione["started_at"] if sessione else 0) / 1000)

        riassunto = self.riassumi(segmenti)
        analisi.riassunto = riassunto.text.strip()
        self._somma(analisi, riassunto)
        self._salva_output(session_id, "summary", analisi.riassunto, riassunto, prompts.SUMMARY)

        salienti = self.punti_salienti(segmenti)
        analisi.punti_salienti = salienti.text.strip()
        self._somma(analisi, salienti)
        self._salva_output(
            session_id, "highlights", analisi.punti_salienti, salienti, prompts.HIGHLIGHTS
        )

        candidati, completions = self.candidati(segmenti)
        for c in completions:
            self._somma(analisi, c)

        if candidati:
            unione = self.unisci(candidati, quando)
            self._somma(analisi, unione)
            dati = unione.data or {}
            analisi.scartati = dati.get("scartati", [])
            output_id = self._salva_output(
                session_id,
                "custom",
                json.dumps(dati, ensure_ascii=False),
                unione,
                prompts.MERGE_TASKS,
            )
            analisi.tasks = self._salva_tasks(session_id, dati.get("tasks", []), output_id)

        self.store.set_session_state(session_id, "analyzed")
        return analisi

    def _salva_output(
        self, session_id: int, kind: str, contenuto: str, c: Completion, prompt: tuple[str, str]
    ) -> int:
        return self.store.add_ai_output(
            session_id,
            kind,
            contenuto,
            model=c.model,
            provider=c.provider,
            prompt_id=prompt[0],
            prompt_version=prompt[1],
            tokens_in=c.tokens_in,
            tokens_out=c.tokens_out,
            cost_usd=c.cost_usd,
        )

    def _salva_tasks(self, session_id: int, tasks: list[dict], output_id: int) -> list[dict]:
        """Scrive le task con le loro prove.

        Le citazioni non arrivano da qui: `add_task` rilegge il testo dal
        segmento indicato, e scarta i riferimenti che non esistono.
        """
        salvate = []
        validi = {s.id for s in self.store.segments(session_id)}

        for t in tasks:
            evidence = [
                {"segment_id": e["segment_id"], "supports": e.get("supports", "esistenza")}
                for e in t.get("evidence", [])
                if e.get("segment_id") in validi
            ]
            # Una task senza uno straccio di riferimento verificabile non è
            # stata ricavata dalla trascrizione: è stata inventata.
            if not evidence:
                continue

            task_id = self.store.add_task(
                session_id,
                t["titolo"],
                descrizione=t.get("descrizione"),
                assignee_text=t.get("assignee"),
                due_date=t.get("due_date"),
                due_raw=t.get("due_raw"),
                priorita=t.get("priorita"),
                confidence=t.get("confidence"),
                needs_review=bool(t.get("needs_review", True)),
                review_reason=t.get("review_reason"),
                ai_output_id=output_id,
                evidence=evidence,
            )
            salvate.append({**t, "id": task_id})
        return salvate
