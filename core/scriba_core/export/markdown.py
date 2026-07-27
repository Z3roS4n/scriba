"""Esporta una call in un file Markdown.

È l'export senza perdite: tutto quello che l'applicazione sa su una riunione
finisce in un file di testo leggibile, versionabile e che sopravvive
all'applicazione stessa. Se un domani Scriba non esistesse più, il lavoro fatto
resterebbe consultabile con qualunque editor.

Per questo la trascrizione integrale c'è sempre, anche se lunga: è il documento
originale, e un riassunto non lo sostituisce.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ..db.store import Store

PRIORITA_SIMBOLO = {"critica": "!!!", "alta": "!!", "media": "!", "bassa": ""}


def _mmss(ms: int) -> str:
    minuti, secondi = divmod(max(0, ms) // 1000, 60)
    return f"{minuti:02d}:{secondi:02d}"


def _nome_file(titolo: str | None, quando: datetime, session_id: int) -> str:
    base = titolo or f"call-{session_id}"
    # Si tiene solo ciò che è sicuro in un nome di file su qualunque sistema.
    pulito = re.sub(r"[^\w\s-]", "", base, flags=re.UNICODE).strip()
    pulito = re.sub(r"[\s_]+", "-", pulito).lower()[:60] or f"call-{session_id}"
    return f"{quando:%Y-%m-%d}.{pulito}.md"


def esporta(store: Store, session_id: int, destinazione: Path | str) -> Path:
    """Scrive il file e restituisce il percorso."""
    sessione = store.conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if sessione is None:
        raise ValueError(f"Sessione {session_id} inesistente.")

    quando = datetime.fromtimestamp(sessione["started_at"] / 1000)
    destinazione = Path(destinazione)
    if destinazione.suffix.lower() != ".md":
        destinazione.mkdir(parents=True, exist_ok=True)
        destinazione = destinazione / _nome_file(sessione["titolo"], quando, session_id)
    destinazione.parent.mkdir(parents=True, exist_ok=True)

    righe: list[str] = []
    a = righe.append

    a(f"# {sessione['titolo'] or f'Call #{session_id}'}")
    a("")
    durata = f" · {_mmss(sessione['durata_ms'])}" if sessione["durata_ms"] else ""
    piattaforma = f" · {sessione['piattaforma']}" if sessione["piattaforma"] else ""
    a(f"*{quando:%d/%m/%Y %H:%M}{durata}{piattaforma}*")
    a("")
    if not sessione["consenso_confermato_at"]:
        # Se ne prende atto nel documento invece di lasciarlo implicito: chi lo
        # rilegge fra sei mesi deve poterlo sapere.
        a("> Non risulta confermato l'avviso ai partecipanti sulla registrazione.")
        a("")

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

    if riassunto := correnti.get("summary"):
        a(riassunto.strip())
        a("")

    if salienti := correnti.get("highlights"):
        a("## Punti salienti")
        a("")
        a(salienti.strip())
        a("")

    # ------------------------------------------------------------------- task

    tasks = list(
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
    if tasks:
        a("## Da fare")
        a("")
        for t in tasks:
            spunta = "x" if t["stato"] == "done" else " "
            pezzi = []
            if t["assignee_text"]:
                pezzi.append(t["assignee_text"])
            if t["due_date"]:
                pezzi.append(t["due_date"])
            elif t["due_raw"]:
                pezzi.append(t["due_raw"])
            if simbolo := PRIORITA_SIMBOLO.get(t["priorita"] or ""):
                pezzi.append(simbolo)
            coda = f" — {' · '.join(pezzi)}" if pezzi else ""
            da_rivedere = " *(da confermare)*" if t["needs_review"] else ""
            a(f"- [{spunta}] **{t['titolo']}**{coda}{da_rivedere}")

            if t["descrizione"]:
                a(f"  {t['descrizione']}")

            # Da dove viene ogni campo: è la parte che rende una task
            # verificabile invece che solo plausibile.
            for e in store.task_evidence(t["id"]):
                if e["quote"]:
                    a(f"  - `{_mmss(e['t_ms'])}` {e['supports']}: «{e['quote']}»")
        a("")

    # ------------------------------------------------------------ screenshot

    schermate = store.screenshots(session_id)
    if schermate:
        a("## Schermate")
        a("")
        for s in schermate:
            a(f"### {_mmss(s['t_ms'])}")
            a("")
            a(f"![schermata {_mmss(s['t_ms'])}]({Path(s['path']).as_posix()})")
            a("")
            if s["nota_utente"]:
                a(f"*{s['nota_utente']}*")
                a("")
            if s["ocr_text"]:
                a("```")
                a(s["ocr_text"])
                a("```")
                a("")

    # ----------------------------------------------------------- trascrizione

    segmenti = store.segments(session_id, only_final=True)
    if segmenti:
        a("## Trascrizione")
        a("")
        per_tempo = {s["t_ms"]: s for s in schermate}
        prossime = sorted(per_tempo)
        i = 0
        for seg in segmenti:
            # Le schermate si intercalano dove sono state prese, così rileggendo
            # si ritrova quello che si aveva davanti in quel momento.
            while i < len(prossime) and prossime[i] <= seg.t_start_ms:
                shot = per_tempo[prossime[i]]
                a(f"`{_mmss(shot['t_ms'])}` → *schermata: {Path(shot['path']).name}*")
                a("")
                i += 1
            chi = "**Io**" if seg.source == "mic" else "**Altri**"
            a(f"`{_mmss(seg.t_start_ms)}` {chi} — {seg.testo}")
            a("")

    destinazione.write_text("\n".join(righe), encoding="utf-8")
    return destinazione
