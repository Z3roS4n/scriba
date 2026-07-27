"""Prototipo end-to-end: registra una call e la trascrive mentre parli.

Mette in fila tutti i pezzi validati finora — cattura a due tracce, trascrizione
locale in streaming, persistenza — senza interfaccia grafica. Se questo
funziona, la UI è solo una finestra sopra a qualcosa che già gira.

A schermo il testo provvisorio compare in grigio mentre si parla e viene
sostituito da quello definitivo quando la frase si chiude.

Uso:
    python spikes/live_transcribe.py [--minutes 10]

Si ferma con Ctrl+C.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from scriba_core.audio.capture import DualCapture  # noqa: E402
from scriba_core.db.store import Store  # noqa: E402
from scriba_core.session import SessionClock  # noqa: E402
from scriba_core.stt.base import TranscriptEvent  # noqa: E402
from scriba_core.stt.parakeet import ParakeetEngine  # noqa: E402
from scriba_core.stt.streaming import StreamingTranscriber  # noqa: E402

GRIGIO, RESET, GRASSETTO = "\033[90m", "\033[0m", "\033[1m"
ETICHETTA = {"mic": "IO   ", "loopback": "ALTRI"}


class Console:
    """Stampa i parziali in modo che non si accumulino a schermo."""

    def __init__(self) -> None:
        self._riga_provvisoria = False

    def _pulisci(self) -> None:
        if self._riga_provvisoria:
            print("\r\033[K", end="")
            self._riga_provvisoria = False

    def evento(self, ev: TranscriptEvent) -> None:
        etichetta = ETICHETTA.get(ev.source, ev.source)
        minuti, secondi = divmod(ev.t_start_ms // 1000, 60)
        self._pulisci()
        if ev.is_final:
            print(f"[{minuti:02d}:{secondi:02d}] {GRASSETTO}{etichetta}{RESET}  {ev.text}")
        else:
            testo = ev.text if len(ev.text) < 110 else "..." + ev.text[-107:]
            print(f"{GRIGIO}[{minuti:02d}:{secondi:02d}] {etichetta}  {testo}{RESET}", end="", flush=True)
            self._riga_provvisoria = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=10.0, help="durata massima")
    parser.add_argument("--db", type=Path, default=Path("data/scriba.sqlite"))
    parser.add_argument("--titolo", default=None)
    parser.add_argument(
        "--senza-conferma",
        action="store_true",
        help="salta la domanda sul consenso (per prove automatiche). La sessione "
        "resta marcata come non confermata: non finge un consenso che non c'è stato.",
    )
    args = parser.parse_args()

    consenso_ms: int | None = None
    if args.senza_conferma:
        print("[prova automatica: consenso non richiesto e non registrato]\n")
    else:
        print("=" * 72)
        print("Stai per registrare anche l'audio degli altri partecipanti.")
        print("Avvisarli e' una tua responsabilita', non la sostituisce questa conferma.")
        print("=" * 72)
        if input("Hai avvisato i partecipanti? [s/N] ").strip().lower() not in ("s", "si", "sì", "y"):
            print("Registrazione annullata.")
            return 1
        consenso_ms = int(time.time() * 1000)

    print("\nCarico il modello di trascrizione...")
    engine = ParakeetEngine(quantization="int8")

    store = Store(args.db)
    clock = SessionClock()
    session_id = store.create_session(
        clock.started_at_ms,
        titolo=args.titolo,
        stt_model=engine.name,
        consenso_confermato_at=consenso_ms,
    )
    console = Console()

    # Un evento provvisorio aggiorna sempre lo stesso record: quando diventa
    # definitivo si rifinisce quello, invece di crearne un altro. È ciò che
    # tiene validi i riferimenti che le task avranno su questi segmenti.
    aperti: dict[str, int] = {}

    def on_event(ev: TranscriptEvent) -> None:
        console.evento(ev)
        seg_id = aperti.get(ev.source)
        if seg_id is None:
            seg_id = store.add_segment(
                session_id, ev.source, ev.t_start_ms, ev.t_end_ms, ev.text, is_final=ev.is_final
            )
            aperti[ev.source] = seg_id
        else:
            store.refine_segment(seg_id, ev.text, t_end_ms=ev.t_end_ms, is_final=ev.is_final)
        if ev.is_final:
            aperti.pop(ev.source, None)

    trascrittori = {
        source: StreamingTranscriber(engine, source, on_event)
        for source in ("mic", "loopback")
    }
    for t in trascrittori.values():
        t.start()

    def on_audio(source: str, samples, t_ms: int) -> None:
        trascrittori[source].feed(samples, t_ms)

    capture = DualCapture(clock, on_audio)
    devices = capture.start()

    print(f"\nmic      : {devices['mic'].name}")
    print(f"loopback : {devices['loopback'].name}")
    print(f"sessione : #{session_id} in {args.db}")
    print(f"\nREGISTRO — Ctrl+C per fermare (max {args.minutes:.0f} min)\n")

    try:
        deadline = time.perf_counter() + args.minutes * 60
        while time.perf_counter() < deadline:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n\nChiudo...")
    finally:
        capture.stop()
        # I trascrittori si fermano dopo la cattura: così l'ultima frase, quella
        # che stavi ancora dicendo, viene chiusa invece di andare persa.
        for t in trascrittori.values():
            t.stop()
        store.end_session(session_id, clock.ended_at_ms)
        store.set_session_state(session_id, "ready")

    segmenti = store.segments(session_id)
    parlato = sum(s.t_end_ms - s.t_start_ms for s in segmenti) / 1000
    print(f"\n{'=' * 72}")
    print(f"Sessione #{session_id} — {clock.now_ms() / 1000:.0f}s registrati")
    print(f"Segmenti: {len(segmenti)}  ({parlato:.0f}s di parlato)")
    for source in ("mic", "loopback"):
        n = sum(1 for s in segmenti if s.source == source)
        print(f"  {ETICHETTA[source].strip():<6}: {n}")
    print(f"\nTrascrizione completa in {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
