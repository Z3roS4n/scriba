"""Punto di ingresso per l'eseguibile pacchettizzato del core (PyInstaller).

Sta fuori da `core/scriba_core/` di proposito, per due motivi:

1. `server.py` usa import relativi (`from .db.store import Store`), validi solo
   se il modulo viene importato come parte del pacchetto. PyInstaller analizza
   a partire da uno script "esterno", non da un modulo lanciato con `-m`: senza
   questo involucro l'analisi fallirebbe sugli import relativi.
2. Il perimetro di questo task non include `core/scriba_core/`: aggiungere un
   entry point qui, sotto `scripts/`, tocca solo file di packaging.

Replica l'unico comando che `sidecar.ts` invoca oggi in sviluppo
(`python -m scriba_core.server <db> --watch-parent`): stessi argomenti,
stesso comportamento, cambia solo come l'interprete viene raggiunto.
"""

from __future__ import annotations

import argparse
import sys


def _dispatch_modulo() -> int:
    """Emula `python -m <modulo> [argomenti]` dentro l'eseguibile pacchettizzato.

    `detect/call.py` isola la sonda di rilevamento chiamate in un processo
    separato lanciandola con `[sys.executable, "-m", "scriba_core.detect.probe", ...]`
    — un'invocazione che ha senso solo se `sys.executable` e' un vero
    interprete Python. Una volta pacchettizzato, `sys.executable` e' invece
    questo stesso eseguibile: senza questo ramo, l'argparse del server
    riceverebbe `-m` come argomento sconosciuto e uscirebbe con un errore,
    disabilitando il rilevamento delle chiamate dopo un pugno di tentativi
    falliti. Generico apposta (non hardcoded sul solo probe): qualunque altro
    modulo invocato allo stesso modo in futuro continua a funzionare senza
    dover toccare di nuovo questo file.
    """
    import runpy

    modulo = sys.argv[2]
    # Il modulo bersaglio si aspetta il proprio nome in argv[0], come farebbe
    # il vero `python -m`: senza questo, `sys.argv[1:]` dentro il modulo
    # includerebbe ancora "-m" e il nome del modulo stesso.
    sys.argv = sys.argv[2:]
    runpy.run_module(modulo, run_name="__main__")
    return 0


def _avvia_server() -> int:
    from scriba_core.server import run

    parser = argparse.ArgumentParser(description="Core di Scriba")
    parser.add_argument("db", nargs="?", default="data/scriba.sqlite")
    parser.add_argument(
        "--watch-parent",
        action="store_true",
        help="spegniti quando chi ti ha avviato chiude lo standard input (lo usa l'interfaccia).",
    )
    args = parser.parse_args()
    run(args.db, watch_parent=args.watch_parent)
    return 0


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "-m":
        return _dispatch_modulo()
    return _avvia_server()


if __name__ == "__main__":
    raise SystemExit(main())
