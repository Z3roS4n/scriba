"""Prototipo end-to-end: registra una call e la trascrive mentre parli.

Stessa strada che percorre l'applicazione, ma senza finestra: serve a provare la
registrazione dal terminale quando si sta lavorando sul core.

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

from scriba_core.db.store import Store  # noqa: E402
from scriba_core.recorder import Recorder  # noqa: E402
from scriba_core.stt.base import TranscriptEvent  # noqa: E402
from scriba_core.stt.parakeet import ParakeetEngine  # noqa: E402

GRIGIO, RESET, GRASSETTO = "\033[90m", "\033[0m", "\033[1m"
ETICHETTA = {"mic": "IO   ", "loopback": "ALTRI"}


class Console:
    """Stampa i parziali in modo che non si accumulino a schermo."""

    def __init__(self) -> None:
        self._riga_provvisoria = False

    def evento(self, ev: TranscriptEvent) -> None:
        etichetta = ETICHETTA.get(ev.source, ev.source)
        minuti, secondi = divmod(ev.t_start_ms // 1000, 60)
        if self._riga_provvisoria:
            print("\r\033[K", end="")
            self._riga_provvisoria = False

        if ev.is_final:
            print(f"[{minuti:02d}:{secondi:02d}] {GRASSETTO}{etichetta}{RESET}  {ev.text}")
        else:
            testo = ev.text if len(ev.text) < 110 else "..." + ev.text[-107:]
            print(
                f"{GRIGIO}[{minuti:02d}:{secondi:02d}] {etichetta}  {testo}{RESET}",
                end="",
                flush=True,
            )
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
        if input("Hai avvisato i partecipanti? [s/N] ").strip().lower() not in (
            "s", "si", "sì", "y",
        ):
            print("Registrazione annullata.")
            return 1
        consenso_ms = int(time.time() * 1000)

    print("\nCarico il modello di trascrizione...")
    engine = ParakeetEngine(quantization="int8")
    store = Store(args.db)
    console = Console()

    # Si passa dal Recorder invece di rimettere insieme i pezzi a mano: è lui
    # che sa in che ordine si spegne tutto, che salva l'audio su disco e che
    # scarta le frasi in cui il microfono ha ripreso l'altoparlante. Rifarlo qui
    # significherebbe avere due versioni della stessa cosa, e una delle due
    # sarebbe sbagliata.
    recorder = Recorder(engine, store, on_event=console.evento)
    info = recorder.start(titolo=args.titolo, consenso_confermato_at=consenso_ms)
    session_id = info.session_id

    print(f"\nmic      : {info.devices['mic'].name}")
    print(f"loopback : {info.devices['loopback'].name}")
    print(f"sessione : #{session_id} in {args.db}")
    print(f"\nREGISTRO — Ctrl+C per fermare (max {args.minutes:.0f} min)\n")

    durata_s = 0.0
    try:
        deadline = time.perf_counter() + args.minutes * 60
        while time.perf_counter() < deadline:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n\nChiudo...")
    finally:
        durata_s = recorder.now_ms() / 1000
        recorder.stop()

    segmenti = store.segments(session_id)
    parlato = sum(s.t_end_ms - s.t_start_ms for s in segmenti) / 1000
    print(f"\n{'=' * 72}")
    print(f"Sessione #{session_id} — {durata_s:.0f}s registrati")
    print(f"Segmenti: {len(segmenti)}  ({parlato:.0f}s di parlato)")
    for source in ("mic", "loopback"):
        n = sum(1 for s in segmenti if s.source == source)
        print(f"  {ETICHETTA[source].strip():<6}: {n}")
    if recorder._echi_scartati:
        print(f"  scartate {recorder._echi_scartati} frasi rientrate dall'altoparlante")

    sessione = store.conn.execute(
        "SELECT audio_mic_path, audio_loop_path FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    for etichetta, campo in (("mic", "audio_mic_path"), ("loopback", "audio_loop_path")):
        percorso = sessione[campo]
        if percorso and Path(percorso).exists():
            mb = Path(percorso).stat().st_size / 1e6
            print(f"  audio {etichetta}: {percorso} ({mb:.1f} MB)")

    print(f"\nTrascrizione completa in {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
