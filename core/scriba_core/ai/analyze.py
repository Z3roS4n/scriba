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
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..db.store import Segment, Store
from ..llm.base import Completion, LLMProvider
from . import date_italiane, lingue, prompts


class AnalisiInterrotta(Exception):
    """Sollevata dal callback di avanzamento quando l'utente ha chiesto di fermarsi.

    Non viene sollevata da qui dentro: la decisione di interrompere non spetta
    all'analizzatore, che non sa nemmeno che esiste una richiesta HTTP dietro.
    Il callback la solleva quando gliela si passa già "armata".
    """

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


def formatta_segmenti(segmenti: list[Segment], schermate: list | None = None) -> str:
    """Prepara la trascrizione per il modello.

    Ogni riga porta l'id del segmento: è l'aggancio con cui il modello indica le
    proprie fonti senza dover copiare il testo.

    Le schermate catturate durante la call vengono inserite **nel punto in cui
    sono state prese**, non in fondo. È tutto il senso di averle: quando qualcuno
    dice "questo qui non torna" indicando una slide, la parola "questo" acquista
    un significato solo se la slide sta lì accanto.
    """
    voci: list[tuple[int, int, str]] = []

    for s in segmenti:
        minuti, secondi = divmod(s.t_start_ms // 1000, 60)
        chi = "io" if s.source == "mic" else "altri"
        voci.append((s.t_start_ms, 0, f"[{s.id}] ({minuti:02d}:{secondi:02d}) {chi}: {s.testo}"))

    # Le slide identiche si annotano una volta sola: chi condivide uno schermo
    # fermo produce dieci scatti dello stesso contenuto, e ripeterlo dieci volte
    # sposta il peso dell'analisi su qualcosa che è stato detto una volta.
    gia_viste: set[str] = set()
    for shot in schermate or []:
        testo = (shot["ocr_text"] or "").strip() if "ocr_text" in shot.keys() else ""
        nota = (shot["nota_utente"] or "").strip() if "nota_utente" in shot.keys() else ""
        if not testo and not nota:
            continue
        impronta = testo[:400]
        if impronta and impronta in gia_viste:
            continue
        gia_viste.add(impronta)

        minuti, secondi = divmod(shot["t_ms"] // 1000, 60)
        corpo = f"schermata condivisa: {testo}" if testo else "schermata condivisa"
        if nota:
            corpo += f" — annotazione di chi ha catturato: {nota}"
        voci.append((shot["t_ms"], 1, f"({minuti:02d}:{secondi:02d}) [{corpo}]"))

    voci.sort(key=lambda v: (v[0], v[1]))
    return "\n".join(testo for _, _, testo in voci)


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


# A quale campo corrisponde ciascun elenco di righe prodotto in estrazione.
CAMPI_PROVE = {
    "righe_titolo": "titolo",
    "righe_assignee": "assignee",
    "righe_scadenza": "due_date",
    "righe_priorita": "priorita",
}


def _prove_dai_candidati(candidati: list[dict]) -> list[dict]:
    """Trasforma gli elenchi per campo nelle prove da salvare.

    L'estrazione elenca le righe separatamente per titolo, responsabile,
    scadenza e priorità: è il nome del campo a dire cosa giustificano, non
    un'etichetta che il modello deve scegliere ogni volta. Provato altrimenti,
    finiva tutto sotto "descrizione".
    """
    viste: set[tuple[int, str]] = set()
    prove: list[dict] = []
    for candidato in candidati:
        for elenco, campo in CAMPI_PROVE.items():
            for segment_id in candidato.get(elenco) or []:
                chiave = (segment_id, campo)
                if chiave not in viste:
                    viste.add(chiave)
                    prove.append({"segment_id": segment_id, "supports": campo})
        # Formato precedente, ancora presente nelle analisi già salvate.
        for prova in candidato.get("evidence") or []:
            chiave = (prova.get("segment_id"), prova.get("supports"))
            if chiave[0] is not None and chiave not in viste:
                viste.add(chiave)
                prove.append(prova)
    return prove


class Analizzatore:
    def __init__(
        self,
        provider: LLMProvider,
        store: Store,
        *,
        on_fase: Callable[[str, str, str | None, str | None, dict[str, Any] | None], None]
        | None = None,
    ) -> None:
        self.provider = provider
        self.store = store
        # Chi chiama scopre a che punto è l'analisi da qui, non frugando nello
        # stato interno: un callback invece di un getter perché il lavoro dura
        # minuti e nessuno vuole interrogare a intervalli per saperlo.
        # Passato dal server, che non è cosa sa dell'analizzatore: qui non si
        # conosce il broadcaster né il websocket, solo "fase X, stato Y".
        self.on_fase = on_fase

    # ------------------------------------------------------------------ utili

    def _chiedi(self, sistema: str, testo: str, schema=None, max_tokens: int = 2048) -> Completion:
        return self.provider.complete(
            system=sistema, user=testo, schema=schema, max_tokens=max_tokens
        )

    def _avvisa(
        self,
        chiave: str,
        stato: str,
        nota: str | None = None,
        *,
        nota_chiave: str | None = None,
        nota_valori: dict[str, Any] | None = None,
    ) -> None:
        """Avvisa che una fase è cambiata.

        `nota` è per quello che si legge uguale in tutte le lingue — «67 s»
        è un numero e un'unità. Quando invece è una frase si manda
        `nota_chiave` con i suoi valori, e a scriverla è l'interfaccia: qui
        siamo dentro il thread dell'analisi, lontani da qualunque richiesta,
        e la lingua di chi guarda non la sappiamo.
        """
        if self.on_fase is not None:
            self.on_fase(chiave, stato, nota, nota_chiave, nota_valori)

    # I due prompt di sistema portano dentro la lingua della call: senza,
    # dicevano al modello che la trascrizione era italiana anche quando non lo
    # era, e il riassunto usciva in italiano comunque (#61).
    @staticmethod
    def _redazione(lingua: str | None) -> str:
        return prompts.SYSTEM_REDAZIONE.format(lingua=lingue.nome(lingua))

    @staticmethod
    def _estrazione(lingua: str | None) -> str:
        return prompts.SYSTEM_ESTRAZIONE.format(lingua=lingue.nome(lingua))

    @staticmethod
    def _somma(analisi: Analisi, c: Completion) -> None:
        analisi.tokens_in += c.tokens_in or 0
        analisi.tokens_out += c.tokens_out or 0
        analisi.costo_usd += c.cost_usd or 0.0
        analisi.modello = c.model
        analisi.provider = c.provider

    # ------------------------------------------------------------- redazione

    def riassumi(
        self, segmenti: list[Segment], schermate: list | None = None, *, lingua: str | None = None
    ) -> Completion:
        return self._chiedi(
            self._redazione(lingua),
            prompts.SUMMARY_PROMPT.format(
                trascrizione=formatta_segmenti(segmenti, schermate),
                **lingue.sezioni_riassunto(lingua),
            ),
            max_tokens=1200,
        )

    def punti_salienti(
        self, segmenti: list[Segment], schermate: list | None = None, *, lingua: str | None = None
    ) -> Completion:
        return self._chiedi(
            self._redazione(lingua),
            prompts.HIGHLIGHTS_PROMPT.format(
                trascrizione=formatta_segmenti(segmenti, schermate)
            ),
            max_tokens=1200,
        )

    # ------------------------------------------------------------------ task

    def candidati(
        self,
        segmenti: list[Segment],
        schermate: list | None = None,
        *,
        lingua: str | None = None,
    ) -> tuple[list[dict], list[Completion]]:
        """Primo passaggio: raccoglie tutto, finestra per finestra."""
        tutti: list[dict] = []
        completions: list[Completion] = []

        tutte_le_finestre = finestre(segmenti)
        n_finestre = len(tutte_le_finestre)

        for i, finestra in enumerate(tutte_le_finestre):
            # Il numero del blocco è l'unico modo per chi guarda di capire che
            # un'estrazione lunga sta avanzando e non è ferma: una finestra di
            # 5000 token su CPU può richiedere più di un minuto da sola.
            self._avvisa(
                "task",
                "in_corso",
                f"{i + 1} di {n_finestre} blocchi",
                nota_chiave="blocchi",
                nota_valori={"i": i + 1, "n": n_finestre},
            )

            # A ogni finestra vanno solo le schermate catturate nel suo arco di
            # tempo: una slide mostrata al minuto 40 non aiuta a capire cosa si
            # diceva al minuto 5, e occupa spazio che serve altrove.
            inizio, fine = finestra[0].t_start_ms, finestra[-1].t_end_ms
            dentro = [s for s in (schermate or []) if inizio <= s["t_ms"] <= fine]

            c = self._chiedi(
                self._estrazione(lingua),
                prompts.EXTRACT_CANDIDATES_PROMPT.format(
                    finestra=formatta_segmenti(finestra, dentro)
                ),
                schema=prompts.SCHEMA_CANDIDATES,
                # Provato a 1500 per risparmiare tempo su CPU: il JSON usciva
                # troncato a metà. Lo spazio deve bastare al caso peggiore —
                # una finestra fitta di impegni — perché una risposta tagliata
                # non è parzialmente utile, è persa.
                max_tokens=2600,
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

    @staticmethod
    def completa_da_candidati(tasks: list[dict], candidati: list[dict]) -> list[dict]:
        """Riempie i campi dell'impegno unito pescandoli dai candidati che lo compongono.

        Divisione del lavoro emersa provando il modello su una riunione vera: il
        raggruppamento gli riesce — la task dei mockup si portava dietro la riga
        del minuto 48, quella in cui si dice che se ne occupa Marco — ma il
        travaso dei valori nei campi no: responsabile vuoto, scadenza vuota,
        tutte le prove etichettate "descrizione".

        Sono due lavori diversi. Capire che due frasi lontane parlano della
        stessa cosa è giudizio semantico, e lì il modello serve. Copiare un
        valore da un candidato al gruppo è contabilità, e la fa il codice.

        Vale anche per le prove: si ricostruiscono dai candidati originali, dove
        ogni campo era già etichettato correttamente, invece di fidarsi
        dell'elenco riscritto dal modello.
        """
        per_id = {c["temp_id"]: c for c in candidati}
        completate = []

        for task in tasks:
            origini = [per_id[t] for t in task.get("merged_from", []) if t in per_id]
            unita = dict(task)

            for campo in ("assignee", "due_raw", "priorita", "descrizione"):
                if unita.get(campo):
                    continue
                # A parità, vince quanto detto più tardi nella riunione: le
                # decisioni successive sovrascrivono quelle precedenti.
                for candidato in reversed(origini):
                    if candidato.get(campo):
                        unita[campo] = candidato[campo]
                        break

            prove = _prove_dai_candidati(origini)
            if prove:
                unita["evidence"] = prove

            completate.append(unita)
        return completate

    def unisci(
        self, candidati: list[dict], quando: datetime, *, lingua: str | None = None
    ) -> Completion:
        """Secondo passaggio: ricompone gli impegni sparsi.

        Riceve solo i candidati, non la trascrizione: sono poche migliaia di
        token invece di venticinquemila, e il modello può concentrarsi sul
        confronto invece di rileggere tutto.
        """
        return self._chiedi(
            self._estrazione(lingua),
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
            "SELECT started_at, lingua FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        quando = datetime.fromtimestamp((sessione["started_at"] if sessione else 0) / 1000)
        # La lingua della call decide quella dell'analisi. Sta gia' in questa
        # riga: prima la si leggeva solo per l'orario, e il riassunto usciva in
        # italiano anche per una riunione tenuta in un'altra lingua (#61).
        lingua = sessione["lingua"] if sessione else None

        # Le schermate catturate durante la call entrano nel contesto insieme a
        # quello che si diceva mentre erano sullo schermo.
        schermate = self.store.screenshots(session_id)

        self._avvisa("riassunto", "in_corso")
        t0 = time.monotonic()
        riassunto = self.riassumi(segmenti, schermate, lingua=lingua)
        analisi.riassunto = riassunto.text.strip()
        self._somma(analisi, riassunto)
        self._salva_output(session_id, "summary", analisi.riassunto, riassunto, prompts.SUMMARY)
        self._avvisa("riassunto", "fatta", f"{round(time.monotonic() - t0)} s")

        self._avvisa("salienti", "in_corso")
        t0 = time.monotonic()
        salienti = self.punti_salienti(segmenti, schermate, lingua=lingua)
        analisi.punti_salienti = salienti.text.strip()
        self._somma(analisi, salienti)
        self._salva_output(
            session_id, "highlights", analisi.punti_salienti, salienti, prompts.HIGHLIGHTS
        )
        self._avvisa("salienti", "fatta", f"{round(time.monotonic() - t0)} s")

        # candidati() avvisa "task" finestra per finestra: qui si segna solo
        # l'inizio, per il caso raro di zero finestre (nessun segmento finale).
        self._avvisa("task", "in_corso", None)
        candidati, completions = self.candidati(segmenti, schermate, lingua=lingua)
        for c in completions:
            self._somma(analisi, c)
        self._avvisa(
            "task",
            "fatta",
            f"{len(candidati)} candidati",
            nota_chiave="candidati",
            nota_valori={"n": len(candidati)},
        )

        if candidati:
            self._avvisa("unione", "in_corso")
            unione = self.unisci(candidati, quando, lingua=lingua)
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
            tasks = self.completa_da_candidati(dati.get("tasks", []), candidati)
            analisi.tasks = self._salva_tasks(session_id, tasks, output_id)
            self._avvisa(
                "unione",
                "fatta",
                f"{len(analisi.tasks)} task",
                nota_chiave="task_n",
                nota_valori={"n": len(analisi.tasks)},
            )
        else:
            self._avvisa(
                "unione", "fatta", "nessun candidato", nota_chiave="nessun_candidato"
            )

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
        sessione = self.store.conn.execute(
            "SELECT started_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        giorno = datetime.fromtimestamp((sessione["started_at"] if sessione else 0) / 1000).date()

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

            # La data la calcola il codice, non il modello: tradurre "entro il
            # quattordici" nella data giusta è aritmetica sul calendario, e un
            # 12B la sbaglia lasciando il campo vuoto pur avendo capito la
            # frase. Se il modello ha comunque prodotto una data, si tiene
            # quella; altrimenti si prova a ricavarla dalle parole originali.
            scadenza = t.get("due_date")
            if not scadenza and t.get("due_raw"):
                risolta = date_italiane.risolvi(t["due_raw"], giorno)
                scadenza = risolta.isoformat() if risolta else None

            task_id = self.store.add_task(
                session_id,
                t["titolo"],
                descrizione=t.get("descrizione"),
                assignee_text=t.get("assignee"),
                due_date=scadenza,
                due_raw=t.get("due_raw"),
                priorita=t.get("priorita"),
                confidence=t.get("confidence"),
                needs_review=bool(t.get("needs_review", True)),
                review_reason=t.get("review_reason"),
                ai_output_id=output_id,
                evidence=evidence,
            )
            # Si riporta la data risolta, non quella grezza del modello:
            # altrimenti quello che si mostra non e' quello che si e' salvato.
            salvate.append({**t, "id": task_id, "due_date": scadenza})
        return salvate
