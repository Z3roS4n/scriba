"""Si accorge quando sei entrato in una call.

L'approccio ovvio — cercare `Zoom.exe` fra i processi — non funziona: Zoom resta
aperto tutto il giorno nella barra delle applicazioni, e trovarlo non dice
niente su cosa stai facendo. Teams poi è una finestra web, e il microfono lo
tiene un processo figlio che si chiama `msedgewebview2.exe`, come mille altre
cose.

Il segnale che funziona è un altro: **chi sta usando il microfono adesso**.
Windows lo sa, perché tiene una sessione audio aperta per ogni applicazione che
registra. Vale per Zoom, Teams, Meet nel browser, Slack e qualunque cosa arrivi
domani, senza scrivere una riga per ciascuna.

Il microfono da solo però non basta: lo usano anche la dettatura e un messaggio
vocale su WhatsApp. Serve che l'applicazione **stia anche riproducendo audio** —
in una riunione qualcuno parla — e che lo faccia per qualche secondo di fila.

Nota su cosa è affidabile e cosa no, misurato su questa macchina:

- Le sessioni di **riproduzione** riportano lo stato correttamente: passa ad
  "attivo" esattamente mentre esce audio e torna indietro quando finisce. È il
  segnale su cui poggia il rilevamento.
- Le sessioni di **cattura** no: aprendo il microfono la sessione compare, ma lo
  stato resta "inattivo" e la sessione sopravvive alla chiusura. Quindi del
  microfono si usa solo la *presenza* di una sessione, mai il suo stato.

Da questo viene la forma della regola: la presenza di una sessione microfono
dice *quale* applicazione può essere in riunione, la riproduzione attiva dice
*quando*.
"""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Nomi noti, solo per dire all'utente che cosa si è riconosciuto. Il rilevamento
# non ne dipende: un'applicazione non elencata viene comunque individuata.
PIATTAFORME = {
    "zoom.exe": "Zoom",
    "cpthost.exe": "Zoom",
    "ms-teams.exe": "Teams",
    "teams.exe": "Teams",
    "slack.exe": "Slack",
    "discord.exe": "Discord",
    "webexmta.exe": "Webex",
    "webex.exe": "Webex",
    "chrome.exe": "browser",
    "msedge.exe": "browser",
    "firefox.exe": "browser",
    "brave.exe": "browser",
}

# Applicazioni che usano il microfono ma non sono riunioni.
IGNORATE = {"scriba.exe", "python.exe", "audiodg.exe"}

# Queste API vanno interrogate solo dalla sonda, in `probe.py`, che gira in un
# processo suo. Interrogarle da qui — dal processo che registra — lo fa
# terminare bruscamente: non sollevano un'eccezione, muore e basta, dentro
# `comtypes` mentre distrugge un riferimento e quindi lontano dalla riga che ha
# causato il guasto. Per questo qui non c'e' nessuna funzione che le tocchi.


@dataclass(frozen=True)
class Call:
    pid: int
    processo: str
    piattaforma: str
    dal_ms: int

    @property
    def nome(self) -> str:
        return self.piattaforma if self.piattaforma != "browser" else "una riunione nel browser"


class RilevatoreCall:
    """Sorveglia il microfono e avvisa quando comincia una riunione.

    Chiama `on_call` una volta sola per riunione. Non avvia niente da solo:
    proporre è compito suo, decidere è dell'utente.
    """

    def __init__(
        self,
        on_call: Callable[[Call], None],
        *,
        intervallo_s: float = 2.0,
        conferma_s: float = 5.0,
    ) -> None:
        self.on_call = on_call
        self.intervallo_s = intervallo_s
        # Quanto deve durare la situazione prima di crederci. La schermata di
        # prova audio prima di entrare in una riunione accende il microfono per
        # un attimo: senza questa attesa si verrebbe interrotti ogni volta.
        self.conferma_s = conferma_s

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._visto_da: dict[int, float] = {}
        self._gia_segnalati: set[int] = set()
        self._cadute = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._ciclo, name="rilevatore", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def dimentica(self, pid: int) -> None:
        """Torna a segnalare questa applicazione alla prossima riunione."""
        self._gia_segnalati.discard(pid)
        self._visto_da.pop(pid, None)

    def _ciclo(self) -> None:
        """Legge quello che la sonda riferisce e applica le regole.

        Le letture arrivano da un processo separato: qui dentro non si tocca
        COM, e quindi non si puo' morire per causa sua.
        """
        while not self._stop.is_set():
            processo = self._avvia_sonda()
            if processo is None:
                self._stop.wait(30)
                continue

            try:
                for riga in processo.stdout:
                    if self._stop.is_set():
                        break
                    try:
                        lettura = json.loads(riga)
                    except json.JSONDecodeError:
                        continue
                    if "errore" in lettura:
                        log.debug("La sonda segnala: %s", lettura["errore"])
                        continue
                    try:
                        self._giro(lettura)
                    except Exception as exc:  # pragma: no cover
                        log.warning("Rilevamento non riuscito: %s", exc)
            finally:
                with contextlib.suppress(Exception):
                    processo.kill()

            if self._stop.is_set():
                return

            # La sonda e' caduta. Si riprova, ma senza accanirsi: se la causa e'
            # permanente, riavviarla all'infinito non aiuta e riempie i log.
            self._cadute += 1
            if self._cadute >= 3:
                log.warning(
                    "La sonda audio e' caduta %d volte: rilevamento sospeso.", self._cadute
                )
                return
            self._stop.wait(5)

    def _avvia_sonda(self):
        try:
            return subprocess.Popen(
                [sys.executable, "-m", "scriba_core.detect.probe", str(self.intervallo_s)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=str(Path(__file__).resolve().parents[2]),
                text=True,
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            log.warning("Sonda audio non avviata: %s", exc)
            return None

    def _giro(self, lettura: dict) -> None:
        adesso = time.monotonic()
        riproducono = set(lettura.get("riproducono", []))
        candidati = {
            voce["pid"]: voce["nome"]
            for voce in lettura.get("microfono", [])
            if voce.get("nome") not in IGNORATE
            and (voce["pid"] in riproducono or self._figlio_riproduce(voce["pid"], riproducono))
        }

        # Chi ha smesso torna disponibile per la volta successiva: finita una
        # riunione, la prossima con la stessa applicazione va segnalata.
        for pid in list(self._visto_da):
            if pid not in candidati:
                del self._visto_da[pid]
                self._gia_segnalati.discard(pid)

        for pid, nome in candidati.items():
            self._visto_da.setdefault(pid, adesso)
            if pid in self._gia_segnalati:
                continue
            if adesso - self._visto_da[pid] < self.conferma_s:
                continue

            self._gia_segnalati.add(pid)
            self.on_call(
                Call(
                    pid=pid,
                    processo=nome,
                    piattaforma=PIATTAFORME.get(nome, nome.removesuffix(".exe")),
                    dal_ms=int(self._visto_da[pid] * 1000),
                )
            )

    @staticmethod
    def _figlio_riproduce(pid: int, riproducono: set[int]) -> bool:
        """L'audio può uscire da un processo figlio di quello che ha il microfono.

        È il caso delle applicazioni a finestra web: il microfono lo tiene un
        processo, l'audio lo fa uscire un altro.
        """
        try:
            import psutil

            figli = {c.pid for c in psutil.Process(pid).children(recursive=True)}
        except Exception:
            return False
        return bool(figli & riproducono)
