"""Verifica il rilevamento delle call entrando in una riunione vera.

I test automatici coprono le regole con letture finte. Se funzionino contro
Zoom, Teams e Meet veri si può sapere solo entrando in una riunione: questo
script mostra cosa vede il rilevatore e cosa decide, così se non scatta si
capisce quale dei segnali manca.

Uso:
    python spikes/prova_rilevamento.py

Lascialo aperto, entra in una call, guarda cosa stampa. Ctrl+C per uscire.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from scriba_core.detect.call import Call, RilevatoreCall  # noqa: E402


def main() -> int:
    print("=" * 74)
    print("Sorveglianza in corso. Entra in una call e guarda cosa succede.")
    print()
    print("  picco = quanto segnale arriva dal microfono di quel programma.")
    print("          0.000 significa sessione vecchia, non sta registrando.")
    print("  esce  = quel programma sta facendo uscire audio.")
    print()
    print("Serve che entrambi siano veri, per qualche secondo di fila.")
    print("Ctrl+C per uscire.")
    print("=" * 74)
    print()

    rilevate: list[Call] = []

    def segnala(call: Call) -> None:
        rilevate.append(call)
        print(f"\n  >>> RILEVATA: {call.nome}  ({call.processo}, pid {call.pid})\n")

    # Una sola sonda, quella del rilevatore: se ne partisse una seconda per la
    # sola visualizzazione, i due processi si disturberebbero interrogando
    # insieme le stesse API COM, e uno dei due morirebbe.
    rilevatore = RilevatoreCall(segnala, intervallo_s=1.0, conferma_s=5.0)
    rilevatore.start()

    try:
        while True:
            lettura = rilevatore.ultima_lettura
            if lettura is None:
                stato = "in attesa della prima lettura..."
            else:
                riproducono = set(lettura.get("riproducono", []))
                voci = [
                    f"{v['nome']} picco={v.get('picco', -1):.3f}"
                    f" {'esce' if v['pid'] in riproducono else '----'}"
                    for v in lettura.get("microfono", [])
                ]
                stato = " | ".join(voci) if voci else "nessun programma sul microfono"
            print(f"\r  {time.strftime('%H:%M:%S')}  {stato[:96]:<96}", end="", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n")
    finally:
        rilevatore.stop()

    print(f"Call rilevate: {len(rilevate)}")
    for c in rilevate:
        print(f"  - {c.nome} ({c.processo})")
    if not rilevate:
        print()
        print("Se sei entrato davvero in una call e non e' stata rilevata, dimmi cosa")
        print("mostrava la riga: serve a capire quale dei due segnali mancava.")
    if rilevatore._cadute:
        print(f"\nLa sonda e' caduta {rilevatore._cadute} volte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
