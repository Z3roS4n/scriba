"""Esporta analisi e task in una forma pensata per essere data a un modello.

Gli altri formati hanno destinatari diversi. Il Markdown è il documento umano:
prosa, trascrizione integrale, fatto per essere letto. Il JSON è per un
programma, e lega ogni prova al suo `segment_id` — un modello dovrebbe
incrociare gli id prima di poter ragionare, spendendo contesto per un lavoro
che possiamo fare noi una volta sola.

Qui la regola è una: **ogni affermazione porta accanto la citazione da cui
viene**, con il minuto, scritta per esteso. Niente riferimenti da risolvere.

E il suo complemento, che conta uguale: **quello che una fonte non ce l'ha
viene detto**. Una task senza prove non diventa una task con prove implicite —
si scrive che non ne ha. Un modello che legge questo documento deve poter
distinguere ciò che è ancorato alla trascrizione da ciò che il modello
precedente ha aggiunto di suo, altrimenti l'errore del primo diventa la
premessa del secondo.

**Più call insieme.** L'archivio filtra per cliente e per periodo, e la domanda
vera è «dammi tutto quello che ci siamo detti con questo cliente». Il documento
tiene quindi N riunioni, ognuna con la sua intestazione.

**La trascrizione integrale è facoltativa.** Il contesto di un modello è finito
e una call di due ore sono circa ottocento segmenti: si può includere, ma è una
scelta, e `stima_token` dice quanto pesa prima di scoprirlo quando viene
troncato.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..db.store import Store
from ._util import mmss, nome_file

#: Quante lettere per token, all'ingrosso. Serve a dare un ordine di grandezza
#: prima di incollare il documento da qualche parte, non a fare un conto esatto:
#: quello dipende dal tokenizzatore, che qui non c'è e non vale la dipendenza.
LETTERE_PER_TOKEN = 4

#: Come si legge un `supports` di `task_evidence`.
CAMPO_SOSTENUTO = {
    "esistenza": "che esista",
    "titolo": "il titolo",
    "descrizione": "la descrizione",
    "assignee": "il responsabile",
    "due_date": "la scadenza",
    "priorita": "la priorità",
}

CHI = {"mic": "io", "loopback": "gli altri"}

#: `strftime("%B")` segue la locale del processo, che non è impostata: dentro un
#: documento italiano uscirebbe «July». I mesi si scrivono, non si chiedono.
MESI = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)

#: Gli stati di `tasks.stato` detti in italiano. Il documento è in italiano e lo
#: legge un modello: mescolarci i valori grezzi del database gli fa credere che
#: siano termini tecnici da preservare.
STATO_TASK = {
    "proposed": "proposta dal modello",
    "confirmed": "confermata",
    "done": "fatta",
    "merged": "unita a un altro impegno",
}


def stima_token(testo: str) -> int:
    return max(1, len(testo) // LETTERE_PER_TOKEN)


def _data(ms: int | None) -> str:
    if not ms:
        return "data sconosciuta"
    d = datetime.fromtimestamp(ms / 1000)
    return f"{d.day} {MESI[d.month - 1]} {d.year}, {d:%H:%M}"


def _durata(ms: int | None) -> str:
    if not ms:
        return "durata sconosciuta"
    minuti = ms // 60000
    return f"{minuti // 60}h{minuti % 60:02d}" if minuti >= 60 else f"{minuti} min"


def _intestazione(quante: int, con_trascrizione: bool) -> list[str]:
    """Dice al modello cosa sta leggendo e come sono fatte le fonti.

    Non è cortesia verso la macchina: senza questa spiegazione un modello non
    ha modo di sapere che «nessuna citazione» è un'informazione e non una
    dimenticanza, e tratterà le due cose allo stesso modo.
    """
    return [
        "# Verbali di riunione, con le fonti",
        "",
        f"{quante} riunione, trascritta e analizzata da Scriba."
        if quante == 1
        else f"{quante} riunioni, trascritte e analizzate da Scriba.",
        "",
        "Come leggere questo documento:",
        "",
        "- Le citazioni fra virgolette basse sono **trascrizione letterale**, con il minuto",
        "  a cui sono state dette. Sono l'unica cosa qui dentro che non è stata interpretata.",
        "- Riassunto e punti salienti li ha scritti un modello leggendo la trascrizione:",
        "  sono interpretazione, non verbale.",
        "- Ogni task dice **da dove viene ogni suo campo**. Dove è scritto «nessuna",
        "  citazione», quel campo è stato dedotto e non è ancorato a niente: trattalo",
        "  come un'ipotesi, non come un fatto.",
        "- I minuti sono relativi all'inizio di ciascuna riunione.",
        "- Sotto ogni riunione c'è la trascrizione integrale."
        if con_trascrizione
        else "- La trascrizione integrale non è inclusa: ci sono solo le parti citate.",
        "",
        "---",
        "",
    ]


def _sezione_call(store: Store, session_id: int, *, con_trascrizione: bool) -> list[str]:
    s = store.conn.execute(
        """
        SELECT s.*, c.nome AS cliente
          FROM sessions s
          LEFT JOIN clients c ON c.id = s.client_id
         WHERE s.id = ?
        """,
        (session_id,),
    ).fetchone()
    if s is None:
        raise ValueError(f"Sessione {session_id} inesistente.")

    righe: list[str] = [f"## {s['titolo'] or f'Call #{session_id}'}", ""]

    meta = [_data(s["started_at"]), _durata(s["durata_ms"])]
    if s["cliente"]:
        meta.append(f"cliente: {s['cliente']}")
    if s["piattaforma"]:
        meta.append(s["piattaforma"])
    righe += [" · ".join(meta), ""]

    # Con quale modello è stata prodotta l'analisi: chi legge deve poter pesare
    # quanto fidarsi di quello che segue.
    analisi = store.get_analysis_meta(session_id)
    if analisi is not None and analisi["finita_at"]:
        pezzi = [p for p in (analisi["etichetta_provider"], analisi["modello"]) if p]
        if pezzi:
            righe += [f"Analizzata con {' · '.join(pezzi)}.", ""]

    correnti = {
        r["kind"]: r["content_md"]
        for r in store.conn.execute(
            """
            SELECT kind, content_md FROM ai_outputs
             WHERE session_id = ? AND is_current = 1 AND scope_start_ms IS NULL
            """,
            (session_id,),
        )
    }

    if correnti.get("summary"):
        righe += ["### Riassunto", "", correnti["summary"].strip(), ""]
    if correnti.get("highlights"):
        righe += ["### Punti salienti", "", correnti["highlights"].strip(), ""]

    righe += _sezione_task(store, session_id)

    scatti = [r for r in store.screenshots(session_id) if (r["ocr_text"] or "").strip()]
    if scatti:
        righe += ["### Testo letto dagli screenshot", ""]
        for r in scatti:
            testo = " ".join((r["ocr_text"] or "").split())
            righe.append(f"- [{mmss(r['t_ms'])}] {testo}")
            if r["nota_utente"]:
                righe.append(f"  - nota di chi l'ha preso: {r['nota_utente']}")
        righe.append("")

    if con_trascrizione:
        righe += ["### Trascrizione integrale", ""]
        for seg in store.segments(session_id, only_final=True):
            chi = seg.speaker_nome_reale or seg.speaker_label or CHI.get(seg.source, seg.source)
            righe.append(f"[{mmss(seg.t_start_ms)}] {chi}: {seg.testo.strip()}")
        righe.append("")

    righe += ["---", ""]
    return righe


def _sezione_task(store: Store, session_id: int) -> list[str]:
    task = list(
        store.conn.execute(
            """
            SELECT * FROM tasks
             WHERE session_id = ? AND stato <> 'rejected'
             ORDER BY CASE stato WHEN 'confirmed' THEN 0 WHEN 'done' THEN 1 ELSE 2 END,
                      IFNULL(due_date, '9999'), id
            """,
            (session_id,),
        )
    )
    if not task:
        return ["### Impegni", "", "Nessun impegno estratto da questa riunione.", ""]

    righe = ["### Impegni", ""]
    for i, t in enumerate(task, start=1):
        righe.append(f"#### {i}. {t['titolo']}")
        if t["descrizione"]:
            righe.append(f"{t['descrizione']}")
        righe.append("")

        attributi = []
        if t["assignee_text"]:
            attributi.append(f"responsabile: {t['assignee_text']}")
        if t["due_date"]:
            detto = f" (a voce: «{t['due_raw']}»)" if t["due_raw"] else ""
            attributi.append(f"scadenza: {t['due_date']}{detto}")
        elif t["due_raw"]:
            # Detta ma non risolta: l'ambiguità si conserva invece di sceglierne
            # una lettura al posto di chi legge.
            attributi.append(f"scadenza detta solo a voce, non risolta: «{t['due_raw']}»")
        if t["priorita"]:
            attributi.append(f"priorità: {t['priorita']}")
        attributi.append(f"stato: {STATO_TASK.get(t['stato'], t['stato'])}")
        if t["confidence"] is not None:
            attributi.append(f"confidenza del modello: {t['confidence']:.2f}")
        if t["needs_review"]:
            motivo = f" — {t['review_reason']}" if t["review_reason"] else ""
            attributi.append(f"**non ancora confermata da una persona**{motivo}")
        righe += [f"- {a}" for a in attributi]

        prove = store.task_evidence(t["id"])
        if prove:
            righe += ["", "Da dove viene:"]
            for e in prove:
                cosa = CAMPO_SOSTENUTO.get(e["supports"], e["supports"])
                citazione = " ".join((e["quote"] or "").split())
                if citazione:
                    righe.append(f'- {cosa} — [{mmss(e["t_ms"])}] «{citazione}»')
                else:
                    # Una prova che punta a un istante ma non porta il testo:
                    # si dice, invece di far sembrare che una citazione ci sia.
                    righe.append(f"- {cosa} — [{mmss(e['t_ms'])}] (nessuna citazione salvata)")
        else:
            righe += [
                "",
                "Da dove viene: **nessuna citazione**. Questo impegno non è ancorato a "
                "nessun punto della trascrizione — trattalo come un'ipotesi.",
            ]
        righe.append("")
    return righe


def costruisci(
    store: Store, session_ids: list[int], *, con_trascrizione: bool = False
) -> str:
    """Il documento, come stringa. Solleva `ValueError` se una call non esiste."""
    if not session_ids:
        raise ValueError("Nessuna call da esportare.")

    righe = _intestazione(len(session_ids), con_trascrizione)
    for sid in session_ids:
        righe += _sezione_call(store, sid, con_trascrizione=con_trascrizione)
    return "\n".join(righe).rstrip() + "\n"


def anteprima(store: Store, session_ids: list[int], *, con_trascrizione: bool = False) -> dict[str, Any]:
    """Quanto pesa, senza scrivere niente su disco.

    Serve a decidere se includere la trascrizione: il contesto di un modello è
    finito, e scoprirlo quando il documento viene troncato è tardi.
    """
    testo = costruisci(store, session_ids, con_trascrizione=con_trascrizione)
    return {
        "caratteri": len(testo),
        "token_stimati": stima_token(testo),
        "call": len(session_ids),
    }


def esporta(
    store: Store,
    session_ids: list[int],
    destinazione: Path | str,
    *,
    con_trascrizione: bool = False,
) -> Path:
    testo = costruisci(store, session_ids, con_trascrizione=con_trascrizione)

    cartella = Path(destinazione)
    cartella.mkdir(parents=True, exist_ok=True)

    if len(session_ids) == 1:
        s = store.get_session(session_ids[0])
        quando = datetime.fromtimestamp((s["started_at"] if s else 0) / 1000)
        nome = nome_file(s["titolo"] if s else None, quando, session_ids[0], "contesto.md")
    else:
        nome = f"{datetime.now():%Y-%m-%d}.contesto-{len(session_ids)}-call.md"

    percorso = cartella / nome
    percorso.write_text(testo, encoding="utf-8")
    return percorso


def esporta_sessione(store: Store, session_id: int, destinazione: Path | str) -> Path:
    """Firma compatibile con gli altri formati, per il registro in `export/__init__`."""
    return esporta(store, [session_id], destinazione)
