"""Prova l'analisi AI su una riunione finta ma realistica.

La trascrizione è costruita apposta perché sia difficile nel modo in cui lo sono
le riunioni vere: i dettagli di uno stesso impegno sono lontani fra loro. Il
lavoro si nomina al minuto 5, la scadenza si concorda al 32, il responsabile si
decide al 48. C'è anche un'idea proposta e poi scartata, che non deve diventare
una task.

Uso:
    python spikes/prova_analisi.py [--provider local|anthropic|openai]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from scriba_core.ai.analyze import Analizzatore  # noqa: E402
from scriba_core.db.store import Store  # noqa: E402
from scriba_core.llm.providers import costruisci  # noqa: E402

# (minuti, chi, cosa)
RIUNIONE = [
    (0.2, "them", "allora, ci siamo tutti? bene, direi di partire"),
    (0.5, "me", "sì, ci sono. volevo ripartire dal punto rimasto aperto la settimana scorsa"),
    (1.0, "them", "il portale clienti, giusto? l'abbiamo lasciato a metà"),
    (1.4, "me", "esatto. la parte di login funziona, manca tutta l'area documenti"),
    (2.1, "them", "quanto manca secondo te?"),
    (2.6, "me", "come sviluppo una decina di giorni, ma dipende da come vogliamo l'interfaccia"),
    (3.2, "them", "sull'interfaccia siamo un po' indietro, non abbiamo ancora niente di deciso"),
    (4.0, "them", "e infatti volevo dire una cosa"),
    # Il lavoro viene nominato qui, senza scadenza e senza responsabile.
    (5.0, "them", "dovremmo preparare i mockup della dashboard prima di continuare a sviluppare"),
    (5.4, "them", "altrimenti rischiamo di rifare il lavoro due volte"),
    (5.9, "me", "sono d'accordo. serve almeno la vista desktop e quella mobile"),
    (6.5, "them", "sì, e vanno mostrati al cliente prima di andare avanti"),
    (7.2, "me", "ok. poi c'è la questione della fatturazione elettronica"),
    (8.0, "them", "quella la vedrei dopo, non è bloccante"),
    (9.1, "me", "va bene. un'altra cosa: pensavo di integrare anche il pagamento con carta"),
    (9.8, "them", "aspetta, quello non era previsto nel preventivo"),
    # Idea proposta e poi scartata: non deve diventare una task.
    (10.3, "me", "hai ragione, lasciamo perdere, lo mettiamo in un secondo momento"),
    (11.0, "them", "meglio. concentriamoci su quello che c'è"),
    (14.2, "them", "senti, il budget complessivo com'è messo?"),
    (14.9, "me", "siamo a quarantamila sui cinquantamila previsti"),
    (15.5, "them", "ok, c'è margine ma non tantissimo"),
    (18.0, "me", "l'altra cosa da chiarire è chi ci dà i contenuti per le pagine"),
    (18.7, "them", "quello lo chiedo io al marketing, ci penso io"),
    (22.0, "them", "torniamo un attimo ai mockup"),
    (23.1, "me", "dimmi"),
    (24.0, "them", "il cliente ha la riunione di revisione il quindici"),
    (25.2, "me", "quindi ci servono prima"),
    # La scadenza si concorda qui, molto dopo.
    (32.0, "them", "diciamo entro il quattordici, così abbiamo un giorno di margine"),
    (32.6, "me", "il quattordici mi sembra fattibile"),
    (33.4, "them", "perfetto, mettiamo quella data"),
    (36.0, "me", "sulla parte tecnica invece dobbiamo decidere il database"),
    (37.2, "them", "restiamo su postgres, non complichiamoci"),
    (40.0, "me", "va bene. e per il deploy?"),
    (41.1, "them", "quello lo vediamo più avanti, prima facciamo funzionare le cose"),
    (44.0, "them", "ah, la migrazione dei dati vecchi non l'abbiamo ancora pianificata"),
    (45.0, "me", "vero. quella è delicata, sono tanti record"),
    (46.2, "them", "diciamo che è urgente, se sbagliamo lì perdiamo dati veri"),
    # Il responsabile dei mockup si decide qui, alla fine.
    (48.0, "them", "per i mockup se ne occupa Marco, gli ho già parlato"),
    (48.8, "me", "ottimo, Marco è quello giusto"),
    (50.0, "them", "invece la migrazione la seguo io personalmente"),
    (52.0, "me", "ok, direi che abbiamo coperto tutto"),
    (53.1, "them", "sì, ci risentiamo la settimana prossima"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="local")
    parser.add_argument("--model", default="gemma-4-12b-it")
    parser.add_argument("--db", default="data/prova_analisi.sqlite")
    args = parser.parse_args()

    db = Path(args.db)
    if db.exists():
        for suffisso in ("", "-wal", "-shm"):
            Path(str(db) + suffisso).unlink(missing_ok=True)

    store = Store(db)
    session_id = store.create_session(
        int(datetime(2026, 7, 27, 10, 0).timestamp() * 1000),
        titolo="Revisione portale clienti",
    )
    for minuti, chi, testo in RIUNIONE:
        t = int(minuti * 60_000)
        store.add_segment(
            session_id,
            "mic" if chi == "me" else "loopback",
            t,
            t + len(testo) * 60,
            testo,
            is_final=True,
        )

    provider = costruisci({"provider": args.provider, "model": args.model})
    if not provider.available():
        print(f"Il provider '{args.provider}' non risponde.")
        if args.provider == "local":
            print("Avvia llama-server:")
            print("  python -m scriba_core.models_manager avvia --model gemma-4-12b")
        return 1

    parole = sum(len(t.split()) for _, _, t in RIUNIONE)
    print(f"Riunione finta: {len(RIUNIONE)} battute, {parole} parole, 53 minuti simulati")
    print(f"Provider: {args.provider} ({provider.model})\n")

    inizio = time.perf_counter()
    analisi = Analizzatore(provider, store).analizza(session_id)
    durata = time.perf_counter() - inizio

    print("=" * 74)
    print("RIASSUNTO")
    print("=" * 74)
    print(analisi.riassunto or "(vuoto)")

    print("\n" + "=" * 74)
    print("PUNTI SALIENTI")
    print("=" * 74)
    print(analisi.punti_salienti or "(vuoto)")

    print("\n" + "=" * 74)
    print(f"TASK ({len(analisi.tasks)})")
    print("=" * 74)
    for t in analisi.tasks:
        print(f"\n• {t['titolo']}")
        if t.get("descrizione"):
            print(f"  {t['descrizione']}")
        print(f"  responsabile : {t.get('assignee') or '—'}")
        print(f"  scadenza     : {t.get('due_date') or '—'}  (detta: {t.get('due_raw') or '—'})")
        print(f"  priorità     : {t.get('priorita') or '—'}")
        print(f"  confidenza   : {t.get('confidence')}  da rivedere: {t.get('needs_review')}")
        for e in store.task_evidence(t["id"]):
            m, s = divmod(e["t_ms"] // 1000, 60)
            print(f"    [{m:02d}:{s:02d}] {e['supports']:<12} «{e['quote']}»")

    if analisi.scartati:
        print(f"\nScartati: {len(analisi.scartati)}")
        for s in analisi.scartati:
            print(f"  - {s.get('motivo')}")

    print("\n" + "=" * 74)
    print(f"tempo   : {durata:.0f}s")
    print(f"token   : {analisi.tokens_in} in / {analisi.tokens_out} out")
    print(f"costo   : ${analisi.costo_usd:.4f}")

    # Il caso per cui il progetto esiste: titolo dal minuto 5, scadenza dal 32,
    # responsabile dal 48, tutti nella stessa task.
    print("\n" + "=" * 74)
    print("VERIFICA — l'impegno con i dettagli sparsi")
    print("=" * 74)
    mockup = next((t for t in analisi.tasks if "mockup" in t["titolo"].lower()), None)
    if mockup is None:
        print("[X] La task dei mockup non è stata individuata.")
        return 1

    momenti = {e["supports"]: e["t_ms"] // 60_000 for e in store.task_evidence(mockup["id"])}
    esiti = [
        ("titolo ricavato dal minuto ~5", momenti.get("titolo") in range(4, 8)),
        ("scadenza ricavata dal minuto ~32", momenti.get("due_date") in range(30, 35)),
        ("responsabile ricavato dal minuto ~48", momenti.get("assignee") in range(46, 52)),
        ("scadenza risolta al 14 agosto", (mockup.get("due_date") or "").endswith("-14")),
        ("responsabile è Marco", "marco" in (mockup.get("assignee") or "").lower()),
    ]
    for descrizione, ok in esiti:
        print(f"  [{'OK' if ok else 'X '}] {descrizione}")

    carta = [t for t in analisi.tasks if "carta" in t["titolo"].lower() or "pagament" in t["titolo"].lower()]
    print(f"  [{'OK' if not carta else 'X '}] l'idea scartata non è diventata una task")

    return 0 if all(ok for _, ok in esiti) and not carta else 1


if __name__ == "__main__":
    sys.exit(main())
