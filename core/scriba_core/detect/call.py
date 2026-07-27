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

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

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

ATTIVA = 1  # AudioSessionStateActive


@dataclass(frozen=True)
class Call:
    pid: int
    processo: str
    piattaforma: str
    dal_ms: int

    @property
    def nome(self) -> str:
        return self.piattaforma if self.piattaforma != "browser" else "una riunione nel browser"


def _sessioni(dispositivo) -> list[tuple[int, int]]:
    """Coppie (pid, stato) delle sessioni audio su un dispositivo."""
    from comtypes import CLSCTX_ALL, POINTER, cast
    from pycaw.pycaw import IAudioSessionControl2, IAudioSessionManager2

    raw = dispositivo.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None)
    manager = cast(raw, POINTER(IAudioSessionManager2))
    enumeratore = manager.GetSessionEnumerator()

    fuori = []
    for i in range(enumeratore.GetCount()):
        sessione = enumeratore.GetSession(i)
        try:
            pid = sessione.QueryInterface(IAudioSessionControl2).GetProcessId()
        except Exception:
            continue
        if pid:
            fuori.append((pid, sessione.GetState()))
    return fuori


def _risali_albero(pid: int) -> tuple[int, str]:
    """Trova l'applicazione vera a cui appartiene un processo.

    Teams è una finestra web: il microfono lo tiene `msedgewebview2.exe`, che da
    solo non dice niente. Il nome che interessa sta più in alto nell'albero.
    """
    import psutil

    try:
        processo = psutil.Process(pid)
    except Exception:
        return pid, ""

    nome = processo.name().lower()
    if nome not in ("msedgewebview2.exe", "cpthost.exe"):
        return pid, nome

    for antenato in processo.parents():
        try:
            nome_antenato = antenato.name().lower()
        except Exception:
            continue
        if nome_antenato in PIATTAFORME:
            return antenato.pid, nome_antenato
    return pid, nome


def in_ascolto() -> list[tuple[int, str]]:
    """Applicazioni che hanno una sessione aperta sul microfono.

    Si guarda la presenza, non lo stato: sul microfono lo stato resta
    "inattivo" anche mentre si registra davvero, quindi filtrarci sopra non
    troverebbe mai niente. La presenza da sola non significa "sta registrando
    adesso" — la sessione sopravvive alla chiusura — ed è il motivo per cui da
    sola non basta a far scattare nulla.
    """
    try:
        from pycaw.pycaw import AudioUtilities

        sessioni = _sessioni(AudioUtilities.GetMicrophone())
    except Exception as exc:
        log.debug("Enumerazione del microfono non riuscita: %s", exc)
        return []

    fuori = []
    for pid, _stato in sessioni:
        vero_pid, nome = _risali_albero(pid)
        if nome and nome not in IGNORATE:
            fuori.append((vero_pid, nome))
    return fuori


def sta_riproducendo(pid: int) -> bool:
    """Vero se l'applicazione sta facendo uscire audio in questo momento.

    È il segnale che dice *quando*: distingue una riunione in corso da
    un'applicazione che ha usato il microfono un'ora fa e ha lasciato lì la
    sessione. Sul lato riproduzione lo stato è affidabile.
    """
    try:
        import psutil
        from pycaw.pycaw import AudioUtilities

        attivi = {
            s.Process.pid
            for s in AudioUtilities.GetAllSessions()
            if s.State == ATTIVA and s.Process
        }
        if pid in attivi:
            return True
        # L'audio può uscire da un processo figlio diverso da quello che tiene
        # il microfono — di nuovo il caso delle applicazioni a finestra web.
        try:
            figli = {c.pid for c in psutil.Process(pid).children(recursive=True)}
        except Exception:
            return False
        return bool(attivi & figli)
    except Exception:
        return False


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
        while not self._stop.is_set():
            try:
                self._giro()
            except Exception as exc:  # pragma: no cover
                log.warning("Rilevamento non riuscito: %s", exc)
            self._stop.wait(self.intervallo_s)

    def _giro(self) -> None:
        adesso = time.monotonic()
        candidati = {pid: nome for pid, nome in in_ascolto() if sta_riproducendo(pid)}

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
