"""Verifica il rilevamento delle call entrando in una riunione vera.

I test automatici coprono le regole con letture finte. Se funzionino contro
Zoom, Teams e Meet veri si può sapere solo entrando in una riunione: questo
script mostra cosa vede la sonda e cosa decide il rilevatore, così se non scatta
si capisce quale dei due segnali manca.

Uso:
    python spikes/prova_rilevamento.py

Lascialo aperto, entra in una call, guarda cosa stampa. Ctrl+C per uscire.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "core"
sys.path.insert(0, str(CORE))

from scriba_core.detect.call import Call, RilevatoreCall  # noqa: E402


def main() -> int:
    print("=" * 74)
    print("Sorveglianza in corso. Entra in una call e guarda cosa succede.")
    print("Ctrl+C per uscire.")
    print("=" * 74)
    print()

    rilevate: list[Call] = []

    def segnala(call: Call) -> None:
        rilevate.append(call)
        print(f"\n  >>> RILEVATA: {call.nome}  ({call.processo}, pid {call.pid})\n")

    rilevatore = RilevatoreCall(segnala, intervallo_s=1.0, conferma_s=5.0)
    rilevatore.start()

    # Una seconda sonda solo per mostrare a schermo cosa si vede, senza toccare
    # quella del rilevatore.
    sonda = subprocess.Popen(
        [sys.executable, "-m", "scriba_core.detect.probe", "1.0"],
        cwd=str(CORE), stdout=subprocess.PIPE, text=True, bufsize=1,
    )

    def mostra() -> None:
        for riga in sonda.stdout:
            try:
                lettura = json.loads(riga)
            except json.JSONDecodeError:
                continue
            if "errore" in lettura:
                print(f"\r  sonda in errore: {lettura['errore'][:70]}", end="", flush=True)
                continue
            riproducono = set(lettura.get("riproducono", []))
            voci = [
                f"{v['nome']}[{v['pid']}]:{'riproduce' if v['pid'] in riproducono else 'muto'}"
                for v in lettura.get("microfono", [])
            ]
            stato = ", ".join(voci) if voci else "nessuna applicazione sul microfono"
            print(f"\r  {time.strftime('%H:%M:%S')}  {stato[:92]:<92}", end="", flush=True)

    threading.Thread(target=mostra, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n")
    finally:
        sonda.kill()
        rilevatore.stop()

    print(f"Call rilevate: {len(rilevate)}")
    for c in rilevate:
        print(f"  - {c.nome} ({c.processo})")
    if not rilevate:
        print()
        print("Se sei entrato davvero in una call e non è stata rilevata, dimmi cosa")
        print("mostrava la riga di stato: serve a capire quale dei due segnali manca.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
