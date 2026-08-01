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

    # Quanto deve reggere una sonda perché la si consideri sana. Sotto questa
    # soglia le ripartenze si contano come consecutive.
    RIPRESA_RIUSCITA_S = 60.0
    # Quante ripartenze ravvicinate prima di rinunciare. Alto di proposito: la
    # libreria COM sottostante ha un difetto noto che chiude l'output ogni
    # tanto, e ripartire costa una frazione di secondo. Rinunciare al primo
    # inciampo significherebbe spegnere la funzione durante una giornata
    # normale.
    CADUTE_CONSECUTIVE_MAX = 20

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
        # Chi ha dato almeno un segnale sul microfono da quando lo si osserva.
        self._con_segnale: set[int] = set()
        self._cadute = 0
        # L'ultima lettura, per chi voglia mostrare cosa si sta vedendo senza
        # avviare una seconda sonda: due processi che interrogano le stesse API
        # COM insieme si disturbano, e uno dei due muore.
        self.ultima_lettura: dict | None = None
        self._sonda = None

        # --- diagnostica
        #
        # Il rilevamento decide in silenzio, e quando non propone una riunione
        # non c'e' modo di sapere quale delle sue condizioni non e' stata
        # soddisfatta: e' un processo escluso, un microfono senza segnale, un
        # audio che non risulta in riproduzione, o l'attesa di conferma non
        # ancora scaduta. Da fuori sono indistinguibili, e senza distinguerle
        # un difetto si puo' solo indovinare.
        #
        # Qui si tiene l'esito dell'ultimo giro, processo per processo, con il
        # perche'. Costa una lista di poche voci riscritta ogni due secondi.
        self.ultima_diagnosi: list[dict] = []
        # Chi riproduceva audio all'ultimo giro. Tenuto qui e non letto da
        # `ultima_lettura`: quello lo riempie il ciclo che parla con la sonda,
        # e la diagnosi deve dire cosa ha visto *chi decide*, altrimenti i due
        # possono raccontare due momenti diversi.
        self._ultimi_riproducono: list[int] = []
        self._ultima_lettura_at: float | None = None
        self._ripartenze = 0
        self._ultimo_motivo: str | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._ciclo, name="rilevatore", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # Si chiude la sonda per prima. Il ciclo è fermo in lettura sul suo
        # standard output, che è un'attesa bloccante: senza chiuderla, non si
        # accorge dello stop finché non arriva la lettura successiva, e chiudere
        # l'applicazione costa secondi di attesa a vuoto.
        # Si riprova qualche volta: fra la richiesta di avvio della sonda e il
        # momento in cui il suo processo è noto passa un istante, e uno stop che
        # capiti proprio lì troverebbe ancora niente da chiudere.
        for _ in range(10):
            processo = self._sonda
            if processo is not None:
                with contextlib.suppress(Exception):
                    processo.kill()
            if self._thread is None or not self._thread.is_alive():
                break
            self._thread.join(timeout=0.2)

        if self._thread is not None:
            self._thread.join(timeout=2)
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
            avvio = time.monotonic()
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
                    self.ultima_lettura = lettura
                    try:
                        self._giro(lettura)
                    except Exception as exc:  # pragma: no cover
                        log.warning("Rilevamento non riuscito: %s", exc)
            finally:
                motivo = self._perche_e_finita(processo)

            if self._stop.is_set():
                return

            # La sonda si è fermata. Succede: la libreria COM sottostante ha un
            # difetto noto — solleva "COM method call without VTable" mentre
            # libera un oggetto — e quando capita l'output si chiude anche se il
            # processo è ancora vivo. Non è una causa che si possa togliere da
            # qui, quindi si riparte e basta.
            #
            # Il conto si azzera se la sonda ha retto abbastanza: quello che si
            # vuole evitare è il caso in cui non riesce proprio a partire, non
            # una ripartenza ogni tanto durante una giornata di lavoro.
            durata = time.monotonic() - avvio
            if durata >= self.RIPRESA_RIUSCITA_S:
                self._cadute = 0
            self._cadute += 1
            # `_cadute` si azzera quando la sonda ha retto: conta le ripartenze
            # *ravvicinate*, che è quello su cui si decide di rinunciare. Per
            # capire se una giornata è andata male serve invece il totale, che
            # non si azzera mai.
            self._ripartenze += 1
            self._ultimo_motivo = motivo

            log.info("Sonda audio ripartita dopo %.0fs (%s).", durata, motivo)
            if self._cadute >= self.CADUTE_CONSECUTIVE_MAX:
                log.warning(
                    "La sonda audio non riesce a restare in piedi (%d tentativi ravvicinati): "
                    "rilevamento sospeso. Ultimo motivo: %s",
                    self._cadute,
                    motivo,
                )
                return
            self._stop.wait(2)

    @staticmethod
    def _perche_e_finita(processo) -> str:
        """Raccoglie il motivo per cui la sonda ha smesso di riferire.

        Prima lo stderr della sonda veniva scartato, e quando cadeva restava
        solo "è caduta" — cioè l'unica informazione che non serve a niente.
        """
        codice = processo.poll()
        dettagli = [
            "output chiuso pur essendo viva" if codice is None else f"uscita con codice {codice}"
        ]

        # Si chiude prima di leggere: `read()` aspetta la fine del flusso, e su
        # un processo ancora vivo aspetterebbe per sempre.
        with contextlib.suppress(Exception):
            processo.kill()
        with contextlib.suppress(Exception):
            if processo.stderr is not None:
                resto = processo.stderr.read()
                if resto and resto.strip():
                    ultima = [r for r in resto.strip().splitlines() if r.strip()][-1]
                    dettagli.append(ultima.strip()[:200])
        return "; ".join(dettagli)

    def _avvia_sonda(self):
        try:
            self._sonda = subprocess.Popen(
                [sys.executable, "-m", "scriba_core.detect.probe", str(self.intervallo_s)],
                stdout=subprocess.PIPE,
                # Non si butta: quando la sonda cade, quello che ha scritto qui
                # è l'unica cosa che spiega perché.
                stderr=subprocess.PIPE,
                cwd=str(Path(__file__).resolve().parents[2]),
                text=True,
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            # Assegnato subito, prima di restituirlo: chi ferma il rilevatore
            # deve trovare qualcosa da chiudere anche se lo fa in questo istante.
            return self._sonda
        except Exception as exc:
            log.warning("Sonda audio non avviata: %s", exc)
            self._sonda = None
            return None

    def _giro(self, lettura: dict) -> None:
        adesso = time.monotonic()
        self._ultima_lettura_at = adesso
        riproducono = set(lettura.get("riproducono", []))
        self._ultimi_riproducono = sorted(riproducono)

        diagnosi: list[dict] = []
        candidati: dict[int, str] = {}
        for voce in lettura.get("microfono", []):
            pid, nome = voce["pid"], voce.get("nome")
            picco = voce.get("picco", -1.0)
            riga: dict = {
                "pid": pid,
                "processo": nome,
                "picco": picco,
                "riproduce": pid in riproducono,
            }
            diagnosi.append(riga)

            if nome in IGNORATE:
                riga["esito"] = "escluso"
                riga["perche"] = "è nell'elenco dei processi da ignorare"
                continue

            # Il microfono sta davvero registrando? Le sessioni di cattura non
            # si chiudono quando l'applicazione smette: senza questo controllo,
            # un programma che ha usato il microfono un'ora fa e adesso fa
            # uscire audio viene scambiato per una riunione. È successo davvero,
            # con un browser che riproduceva un video.
            if picco > 0.0:
                self._con_segnale.add(pid)
            elif picco == 0.0 and pid not in self._con_segnale:
                # Un istante di silenzio assoluto capita anche registrando: si
                # esclude solo chi non ha mai dato segnale da quando lo si
                # osserva.
                riga["esito"] = "escluso"
                riga["perche"] = (
                    "ha una sessione microfono aperta ma non ha mai dato segnale: "
                    "sembra una sessione vecchia, non una registrazione in corso"
                )
                continue

            if pid in riproducono:
                candidati[pid] = nome
            elif self._figlio_riproduce(pid, riproducono):
                riga["riproduce_un_figlio"] = True
                candidati[pid] = nome
            else:
                riga["esito"] = "in attesa"
                riga["perche"] = (
                    "usa il microfono ma non risulta riprodurre audio, né lui né un suo "
                    "processo figlio: in una riunione qualcuno parla"
                )

        # Chi ha smesso torna disponibile per la volta successiva: finita una
        # riunione, la prossima con la stessa applicazione va segnalata.
        presenti = {voce["pid"] for voce in lettura.get("microfono", [])}
        self._con_segnale &= presenti  # chi è sparito riparte da capo

        for pid in list(self._visto_da):
            if pid not in candidati:
                del self._visto_da[pid]
                self._gia_segnalati.discard(pid)

        per_pid = {r["pid"]: r for r in diagnosi}
        for pid, nome in candidati.items():
            self._visto_da.setdefault(pid, adesso)
            riga = per_pid[pid]
            if pid in self._gia_segnalati:
                riga["esito"] = "già proposta"
                riga["perche"] = "la proposta è già stata fatta per questa riunione"
                continue
            atteso = adesso - self._visto_da[pid]
            if atteso < self.conferma_s:
                riga["esito"] = "in conferma"
                riga["perche"] = "sembra una riunione: si aspetta che la situazione regga"
                riga["mancano_s"] = round(self.conferma_s - atteso, 1)
                continue

            riga["esito"] = "riunione"
            riga["perche"] = "microfono in uso e audio in riproduzione da abbastanza tempo"
            self._gia_segnalati.add(pid)
            self.on_call(
                Call(
                    pid=pid,
                    processo=nome,
                    piattaforma=PIATTAFORME.get(nome, nome.removesuffix(".exe")),
                    dal_ms=int(self._visto_da[pid] * 1000),
                )
            )

        self.ultima_diagnosi = diagnosi

    def diagnostica(self) -> dict:
        """Cosa sta vedendo il rilevamento, adesso.

        Serve a rispondere alla domanda «perché non mi ha proposto di
        registrare» guardando, invece che indovinando fra cinque ipotesi tutte
        plausibili. Legge lo stato dell'ultimo giro: non interroga le API audio
        e non avvia una seconda sonda, che è la cosa da non fare — due processi
        che leggono insieme quelle interfacce COM si disturbano, e uno dei due
        muore.
        """
        viva = self._sonda is not None and self._sonda.poll() is None
        eta = None
        if self._ultima_lettura_at is not None:
            eta = round(time.monotonic() - self._ultima_lettura_at, 1)

        return {
            "in_ascolto": self._thread is not None and self._thread.is_alive(),
            "conferma_s": self.conferma_s,
            "intervallo_s": self.intervallo_s,
            "sonda": {
                "viva": viva,
                "ripartenze": self._ripartenze,
                "rinunciato": self._cadute >= self.CADUTE_CONSECUTIVE_MAX,
                "ultimo_motivo": self._ultimo_motivo,
                "ultima_lettura_fa_s": eta,
            },
            # Chi stava riproducendo audio: non è candidato a niente di per sé,
            # ma è quello che spiega un "riproduce un figlio" — l'audio esce da
            # un pid diverso da quello che tiene il microfono.
            "riproducono": list(self._ultimi_riproducono),
            "processi": self.ultima_diagnosi,
        }

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
