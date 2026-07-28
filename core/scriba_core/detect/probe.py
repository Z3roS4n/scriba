"""Sonda che osserva l'audio di sistema, in un processo tutto suo.

Perché un processo separato e non un thread: le API COM di Windows usate qui
fanno **terminare bruscamente il processo** quando vengono interrogate a
ripetizione da un thread secondario. Non sollevano un'eccezione che si possa
intercettare: il processo muore e basta, in un punto lontano da dove è stato
causato il guasto — dentro `comtypes`, mentre distrugge un riferimento.

Un processo che registra una riunione non può morire perché una funzione di
comodità ha interrogato il mixer audio. Qui la sonda sta da sola: se cade, cade
lei, e chi la sorveglia la riavvia.

Stampa una riga JSON per giro:

    {"microfono": [{"pid": 123, "nome": "zoom.exe"}], "riproducono": [123, 456]}
"""

from __future__ import annotations

import json
import sys
import time


def _sessioni_microfono() -> list[dict]:
    from comtypes import CLSCTX_ALL, POINTER, cast
    from pycaw.pycaw import (
        AudioUtilities,
        IAudioSessionControl2,
        IAudioSessionManager2,
    )

    dispositivo = AudioUtilities.GetMicrophone()
    raw = dispositivo.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None)
    manager = cast(raw, POINTER(IAudioSessionManager2))
    enumeratore = manager.GetSessionEnumerator()

    fuori = []
    for i in range(enumeratore.GetCount()):
        try:
            pid = enumeratore.GetSession(i).QueryInterface(IAudioSessionControl2).GetProcessId()
        except Exception:
            continue
        if pid:
            fuori.append(pid)
    return fuori


def _pid_che_riproducono() -> list[int]:
    from pycaw.pycaw import AudioUtilities

    fuori = []
    for sessione in AudioUtilities.GetAllSessions():
        try:
            if sessione.State == 1 and sessione.Process:
                fuori.append(sessione.Process.pid)
        except Exception:
            continue
    return fuori


def _nome(pid: int) -> str:
    import psutil

    try:
        return psutil.Process(pid).name().lower()
    except Exception:
        return ""


def _risali(pid: int) -> tuple[int, str]:
    """Trova l'applicazione vera dietro un processo figlio.

    Teams è una finestra web: il microfono lo tiene `msedgewebview2.exe`, che da
    solo non dice niente. Il nome che interessa sta più in alto nell'albero.
    """
    import psutil

    from .call import PIATTAFORME

    nome = _nome(pid)
    if nome not in ("msedgewebview2.exe", "cpthost.exe"):
        return pid, nome
    try:
        for antenato in psutil.Process(pid).parents():
            nome_antenato = antenato.name().lower()
            if nome_antenato in PIATTAFORME:
                return antenato.pid, nome_antenato
    except Exception:
        pass
    return pid, nome


def main() -> int:
    import comtypes

    # Il processo intero è dedicato a questo, quindi COM si inizializza una
    # volta sul thread principale e non si tocca più.
    comtypes.CoInitialize()

    intervallo = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0

    while True:
        try:
            microfono = [{"pid": p, "nome": n} for p, n in map(_risali, _sessioni_microfono()) if n]
            riproducono = _pid_che_riproducono()
            print(
                json.dumps({"microfono": microfono, "riproducono": riproducono}),
                flush=True,
            )
        except Exception as exc:
            print(json.dumps({"errore": str(exc)}), flush=True)
        time.sleep(intervallo)


if __name__ == "__main__":
    raise SystemExit(main())
