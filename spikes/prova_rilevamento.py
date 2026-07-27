"""Verifica il rilevamento delle call entrando in una riunione vera.

I test automatici coprono le regole con l'audio simulato. Se funzionino contro
Zoom, Teams e Meet veri si può sapere solo entrando in una riunione: questo
script mostra secondo per secondo cosa vede il rilevatore, così si capisce se ha
riconosciuto la situazione e quanto ci ha messo.

Uso:
    python spikes/prova_rilevamento.py

Lascialo aperto, entra in una call, guarda cosa stampa. Ctrl+C per uscire.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from scriba_core.detect.call import Call, RilevatoreCall, in_ascolto, sta_riproducendo  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("Sorveglianza in corso. Entra in una call e guarda cosa succede.")
    print("Ctrl+C per uscire.")
    print("=" * 70)
    print()

    rilevate: list[Call] = []

    def segnala(call: Call) -> None:
        rilevate.append(call)
        print()
        print(f"  >>> RILEVATA: {call.nome}  (processo {call.processo}, pid {call.pid})")
        print()

    rilevatore = RilevatoreCall(segnala, intervallo_s=1.0, conferma_s=5.0)
    rilevatore.start()

    try:
        while True:
            microfono = in_ascolto()
            righe = []
            for pid, nome in microfono:
                suona = "riproduce" if sta_riproducendo(pid) else "muto"
                righe.append(f"{nome}[{pid}]:{suona}")
            stato = ", ".join(righe) if righe else "nessuna applicazione sul microfono"
            print(f"\r  {time.strftime('%H:%M:%S')}  {stato[:90]:<90}", end="", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n")
    finally:
        rilevatore.stop()

    print(f"Call rilevate in questa sessione: {len(rilevate)}")
    for c in rilevate:
        print(f"  - {c.nome} ({c.processo})")
    if not rilevate:
        print()
        print("Se sei entrato davvero in una call e non è stata rilevata, dimmi cosa")
        print("mostrava la riga di stato: serve a capire quale dei due segnali manca.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
