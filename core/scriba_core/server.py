"""Server locale del core.

L'interfaccia grafica è un processo separato e parla con il core da qui. Due
scelte per non esporre le call di lavoro a qualunque programma in esecuzione
sulla macchina:

- si ascolta **solo** su 127.0.0.1 e su una **porta effimera**, decisa dal
  sistema all'avvio, quindi non indovinabile;
- ogni richiesta porta un **token** generato all'avvio e comunicato al processo
  padre sullo standard output.

Un server su porta fissa senza token sarebbe raggiungibile da qualsiasi pagina
web aperta nel browser.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .api import traduci_stato_sessione as _traduci_stato_sessione
from .db import manutenzione
from .db.store import Store
from .recorder import Recorder
from .settings import Settings
from .stt.base import TranscriptEvent

from .ai.note_correnti import GestoreNote

log = logging.getLogger(__name__)

# Quanto aspetta l'analisi automatica prima di cominciare i suoi controlli,
# dopo che la registrazione è finita. Non è un rallentamento accettato per
# pigrizia: se nel frattempo arriva una richiesta esplicita — l'utente ha
# premuto "Analizza" mentre la call stava ancora fermandosi — è quella a dover
# vincere. Un processo partito da solo non deve mai scavalcare, né tanto meno
# far fallire con "già in corso", una richiesta che qualcuno ha fatto apposta.
# Impercettibile rispetto ai minuti che l'analisi vera richiede comunque.
RITARDO_ANALISI_AUTOMATICA_S = 2.0

# Le quattro fasi mostrate mentre un'analisi gira, nell'ordine in cui accadono
# davvero. La chiave è quella che ai/analyze.py usa nel suo callback di
# avanzamento; il titolo è quello che l'interfaccia mostra.
FASI_ANALISI: tuple[tuple[str, str], ...] = (
    ("riassunto", "Riassunto"),
    ("salienti", "Punti salienti"),
    ("task", "Estrazione task"),
    ("unione", "Unione dei riferimenti"),
)

# Cosa dire di ogni motore di analisi: non solo se è disponibile, ma cosa
# comporta usarlo. È la stessa informazione che serve all'export e ai log, per
# questo vive qui in un solo posto invece che scritta a mano nell'interfaccia.
PROVIDERS_INFO: dict[str, dict[str, Any]] = {
    "local": {
        "etichetta": "Modello locale",
        "descrizione": "Non esce nulla dal computer. Più lento: "
        "una call di un'ora richiede una decina di minuti.",
        "model": "gemma-4-12b-it",
        "esce_dal_computer": False,
        "costo_ora_eur": None,
        "minuti_per_ora": 10,
        "rimedio": "Scarica e avvia il modello locale dalle Impostazioni.",
    },
    "claude-cli": {
        "etichetta": "Abbonamento Claude",
        "descrizione": "Usa l'abbonamento già attivo, nessun costo a consumo. "
        "Circa tre minuti per una call di un'ora. La trascrizione viene inviata ad Anthropic.",
        "model": "sonnet",
        "esce_dal_computer": True,
        "costo_ora_eur": None,
        "minuti_per_ora": 3,
        "rimedio": "Installa Claude Code (l'eseguibile `claude`) e accedi al tuo abbonamento "
        "con `claude auth login`. Se prima funzionava, la sessione è scaduta: rifai l'accesso.",
    },
    "anthropic": {
        "etichetta": "API Anthropic",
        "descrizione": "Richiede una chiave. Si paga a consumo.",
        "model": "claude-sonnet-5",
        "esce_dal_computer": True,
        "costo_ora_eur": 0.15,
        "minuti_per_ora": 3,
        "rimedio": "Aggiungi una chiave API Anthropic nelle Impostazioni.",
    },
    "openai": {
        "etichetta": "API OpenAI",
        "descrizione": "Richiede una chiave. Si paga a consumo.",
        "model": "gpt-5-mini",
        "esce_dal_computer": True,
        "costo_ora_eur": 0.05,
        "minuti_per_ora": 3,
        "rimedio": "Aggiungi una chiave API OpenAI nelle Impostazioni.",
    },
}

# La traduzione dello stato grezzo in quello che l'interfaccia mostra vive in
# `api/__init__.py` (importata in cima): la usano in due — qui per l'elenco
# delle call, in `api/clienti.py` per l'archivio — e la stessa call non deve
# risultare in due stati diversi a seconda della schermata da cui la si guarda.


# ------------------------------------------------------ Markdown dell'analisi
#
# Il modello scrive Markdown libero, non JSON: la divisione in pezzi va fatta
# per pattern, tollerando che una riga non torni. Meglio lasciarla fuori dai
# pezzi che far fallire l'intera risposta — il Markdown grezzo resta comunque
# disponibile a parte.

_RIGA_SALIENTE = re.compile(
    r"^\[(?P<t>\d{1,2}:\d{2}(?::\d{2})?)\]\s*\*\*(?P<etichetta>.+?)\*\*\s*[—–-]\s*(?P<corpo>.+)$"
)
_MINUTI_IN_RIGA = re.compile(r"\[(?P<t>\d{1,2}:\d{2}(?::\d{2})?)\]")


def _tempo_a_ms(testo: str) -> int | None:
    """'mm:ss' oppure 'h:mm:ss' -> millisecondi. None se non è nel formato atteso."""
    pezzi = testo.split(":")
    try:
        numeri = [int(p) for p in pezzi]
    except ValueError:
        return None
    if len(numeri) == 2:
        h, m, s = 0, *numeri
    elif len(numeri) == 3:
        h, m, s = numeri
    else:
        return None
    return ((h * 60 + m) * 60 + s) * 1000


def _senza_marcatore_tempo(testo: str, marcatore: re.Match[str]) -> str:
    """Toglie da `testo` il marcatore `[mm:ss]` già estratto altrove come `t_ms`.

    L'interfaccia mostra quel minuto a parte, come chip cliccabile: lasciarlo
    anche nel testo lo fa comparire due volte nella stessa riga. Si ripulisce
    anche lo spazio doppio e la punteggiatura rimasta orfana al suo posto,
    altrimenti il buco lasciato dal marcatore si vede lo stesso.
    """
    pulito = testo[: marcatore.start()] + testo[marcatore.end() :]
    pulito = re.sub(r"\s{2,}", " ", pulito)
    pulito = re.sub(r"\s+([.,;:!?])", r"\1", pulito)
    return pulito.strip()


def _salienti_da_markdown(testo: str | None) -> list[dict[str, Any]]:
    """Ogni riga nel formato '[mm:ss] **Etichetta** — corpo' diventa un PuntoSaliente."""
    if not testo:
        return []
    punti = []
    for riga in testo.splitlines():
        m = _RIGA_SALIENTE.match(riga.strip())
        if not m:
            continue
        t_ms = _tempo_a_ms(m.group("t"))
        if t_ms is None:
            continue
        corpo = m.group("corpo").strip()
        # Il marcatore d'apertura resta fuori da `corpo` per come è fatta la
        # regex, ma se il modello lo ripete anche in testa al corpo (capita)
        # si toglie con la stessa cura: è lo stesso minuto già estratto sopra.
        ripetuto = _MINUTI_IN_RIGA.match(corpo)
        if ripetuto is not None and _tempo_a_ms(ripetuto.group("t")) == t_ms:
            corpo = _senza_marcatore_tempo(corpo, ripetuto)
        punti.append({"t_ms": t_ms, "etichetta": m.group("etichetta").strip(), "corpo": corpo})
    return punti


def _riassunto_a_gruppi(testo: str | None) -> list[dict[str, Any]]:
    """Ogni sezione '## Titolo' diventa un GruppoRiassunto con le sue voci.

    Le voci sono le righe della sezione (puntate o no); i minuti citati fra
    parentesi quadre in una voce ne diventano il riferimento, quando ci sono.
    Una sezione senza voci utilizzabili non compare: mostrarla vuota non
    aiuterebbe chi legge.
    """
    if not testo:
        return []
    gruppi: list[dict[str, Any]] = []
    corrente: dict[str, Any] | None = None

    for grezza in testo.splitlines():
        riga = grezza.strip()
        if riga.startswith("## "):
            if corrente and corrente["voci"]:
                gruppi.append(corrente)
            corrente = {"titolo": riga[3:].strip(), "voci": []}
            continue
        if not riga or corrente is None:
            continue
        contenuto = riga[1:].strip() if riga[:1] in ("-", "*") else riga
        if not contenuto:
            continue
        m = _MINUTI_IN_RIGA.search(contenuto)
        t_ms = _tempo_a_ms(m.group("t")) if m else None
        if m is not None and t_ms is not None:
            # Il minuto va nel chip a parte (t_ms): lasciarlo anche qui lo
            # duplica nella stessa riga, una volta nel testo e una nel chip.
            contenuto = _senza_marcatore_tempo(contenuto, m)
        if not contenuto:
            continue  # restava solo il marcatore: una voce vuota non aiuta
        corrente["voci"].append({"testo": contenuto, "t_ms": t_ms})

    if corrente and corrente["voci"]:
        gruppi.append(corrente)
    return gruppi


class StartRequest(BaseModel):
    titolo: str | None = None
    piattaforma: str | None = None
    # None, non "it": la lingua predefinita e' quella scelta in Impostazioni, e
    # metterla qui vorrebbe dire che chi non la manda registra sempre in
    # italiano. E' quello che succedeva — l'interfaccia non la manda mai, e
    # `sessions.lingua` valeva "it" su ogni call, anche su quelle tenute in
    # un'altra lingua (#61).
    lingua: str | None = None
    # L'utente ha confermato di aver avvisato i partecipanti. Non è un
    # tecnicismo: senza, la sessione resta marcata come non confermata.
    consenso_confermato: bool = False


class ExportRequest(BaseModel):
    # Una cartella, oppure il percorso preciso di un .md. Se manca, si scrive
    # accanto al database.
    destinazione: str | None = None


class ScreenshotRequest(BaseModel):
    path: str
    nota_utente: str | None = None
    width: int | None = None
    height: int | None = None


class Broadcaster:
    """Recapita gli eventi ai client collegati.

    Gli eventi nascono nei thread di trascrizione, che non sono asincroni: il
    passaggio al loop asyncio va fatto in modo esplicito, altrimenti si
    corrompe lo stato interno del loop in modi che si manifestano molto dopo.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        with self._lock:
            self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        with self._lock:
            self._clients.discard(ws)

    def publish(self, message: dict[str, Any]) -> None:
        """Chiamabile da qualunque thread."""
        if self._loop is None:
            return
        with suppress(RuntimeError):  # loop già chiuso durante lo spegnimento
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._fanout(message))
            )

    async def _fanout(self, message: dict[str, Any]) -> None:
        with self._lock:
            clients = list(self._clients)
        payload = json.dumps(message, ensure_ascii=False)
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                # Un client che se n'è andato non deve impedire agli altri di
                # ricevere: si rimuove e si prosegue.
                self.disconnect(ws)


# Ogni quanto mettere al sicuro quello che una call ha scritto finora.
# È il tetto alla perdita in caso di morte violenta del processo: verificato che
# quando l'applicazione Electron muore di colpo il sistema operativo porta con sé
# anche il core — il Job Object di Electron non gli lascia il tempo di
# consolidare, per quanta grazia gli si conceda. Due minuti di trascrizione
# persi sono un fastidio; un'ora di riunione è un danno.
INTERVALLO_CONSOLIDAMENTO_S = 120.0


async def _consolida_mentre_registra(state: dict[str, Any], store) -> None:
    """Travasa il WAL a intervalli, ma solo mentre si registra.

    Fuori da una registrazione non c'è niente di nuovo da mettere al sicuro, e
    un checkpoint a vuoto ogni due minuti sarebbe solo rumore su disco.
    """
    if store is None:
        return
    while True:
        await asyncio.sleep(INTERVALLO_CONSOLIDAMENTO_S)
        recorder = state.get("recorder")
        if recorder is None or not recorder.is_recording:
            continue
        try:
            await asyncio.to_thread(store.consolida)
        except Exception:  # pragma: no cover - non deve mai fermare una call
            log.exception("Consolidamento periodico non riuscito")


def _lifespan(broadcaster: Broadcaster, state: dict[str, Any], preload, avvia_rilevatore=None, store=None):
    """Aggancia il broadcaster al loop e chiude ciò che resta aperto."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        broadcaster.bind_loop(asyncio.get_running_loop())
        if avvia_rilevatore is not None:
            avvia_rilevatore()
        # Il modello si carica subito e in disparte: sono quasi quattro secondi,
        # e farli pagare a chi preme "Registra" fa sembrare l'app bloccata.
        # Girano in un thread perché il caricamento è codice sincrono che
        # altrimenti terrebbe fermo l'intero event loop, websocket compreso.
        asyncio.create_task(preload())
        guardia = asyncio.create_task(_consolida_mentre_registra(state, store))
        try:
            yield
        finally:
            guardia.cancel()
            rilevatore = state.get("rilevatore")
            if rilevatore is not None:
                rilevatore.stop()

            recorder = state.get("recorder")
            if recorder is not None and recorder.is_recording:
                # Meglio una sessione chiusa male che una registrazione orfana
                # che tiene occupato il microfono finché non si riavvia il PC.
                recorder.stop()

            if store is not None:
                # L'ultima cosa, dopo che il registratore ha finito di scrivere:
                # è lo spegnimento il momento in cui SQLite consoliderebbe da sé
                # il WAL, e prima di questa riga non arrivava mai perché il core
                # veniva ucciso invece di essere fermato.
                store.consolida()
                store.close()

    return lifespan


async def _sincronizza_se_richiesto(session_id: int, store: Store, broadcaster) -> None:
    """Manda la call al database remoto, se ce n'è uno e se è stato chiesto.

    Non solleva mai: l'analisi è finita e i suoi risultati sono già al sicuro
    nel database locale. Un server remoto irraggiungibile è un contrattempo da
    riferire, non un motivo per far risultare fallita un'analisi riuscita — e
    la call resta comunque nell'elenco di quelle da rimandare.
    """
    from .export import sql as db_remoto

    try:
        config = await asyncio.to_thread(db_remoto.leggi_config, store)
        if not (config.get("automatico") and config.get("schema") and config.get("tabelle")):
            return
        esito = await asyncio.to_thread(db_remoto.invia, session_id, store)
    except Exception as exc:
        log.warning("Sincronizzazione remota della sessione %s non riuscita: %s", session_id, exc)
        broadcaster.publish(
            {"type": "database_remoto", "stato": "errore",
             "session_id": session_id, "dettaglio": str(exc)}
        )
        return

    broadcaster.publish(
        {"type": "database_remoto", "stato": "fatto",
         "session_id": session_id, "righe": esito["righe"]}
    )


def create_app(
    *,
    db_path: Path,
    token: str,
    engine_factory=None,
    recorder_factory=None,
) -> FastAPI:
    """Costruisce l'applicazione.

    Le due factory sono iniettabili perché caricare il modello vero costa
    secondi e aprire i device audio veri legherebbe i test all'hardware.
    """
    app = FastAPI(title="Scriba core", docs_url=None, redoc_url=None)
    broadcaster = Broadcaster()

    # Prima di aprirlo per scriverci: un database che non si legge non si usa.
    # Continuare a scriverci dentro non lo aggiusta e rende irrecuperabile
    # quello che ancora si poteva salvare (manutenzione.py).
    danno = manutenzione.controlla(db_path)

    store = Store(db_path)
    settings = Settings(Path(db_path).with_name("settings.json"))

    # Lo stato lasciato dalla volta precedente, prima di toccare qualsiasi cosa:
    # è il backup che serve se questo avvio va storto.
    manutenzione.backup(store)

    # Il core è appena partito, quindi nessuno sta registrando: è l'unico
    # momento in cui si può dirlo con certezza, ed è qui che si rimettono in
    # ordine le sessioni lasciate a metà da un avvio precedente morto male.
    appese = store.chiudi_sessioni_appese()
    if appese:
        log.warning(
            "Sessioni rimaste aperte da un avvio precedente, richiuse: %s",
            ", ".join(str(i) for i in appese),
        )

    state: dict[str, Any] = {
        "engine": None,
        "recorder": None,
        "modello": "in_attesa",
        "analisi_in_corso": False,
        # Quale sessione sta analizzando adesso, le sue quattro fasi e
        # l'interruttore per fermarla. Tutti None/vuoti quando non c'è
        # un'analisi in corso.
        "analisi_session_id": None,
        "analisi_fasi": [],
        "analisi_annulla": None,
        # Non None se all'avvio il database era illeggibile ed è stato messo da
        # parte: è una cosa che l'utente deve sapere, non solo i log.
        "db_danneggiato": danno,
    }

    # Un'unica istanza per processo, come il resto dello stato: le note
    # incrementali seguono una sola registrazione alla volta.
    gestore_note = GestoreNote(store, settings, broadcaster.publish)

    def load_engine():
        """Carica il modello. Sincrono e lento: non va mai chiamato sul loop."""
        if state["engine"] is None:
            if engine_factory is not None:
                state["engine"] = engine_factory()
            else:
                from .stt.parakeet import ParakeetEngine

                state["engine"] = ParakeetEngine(quantization="int8")
        return state["engine"]

    async def preload() -> None:
        state["modello"] = "caricamento"
        broadcaster.publish({"type": "modello", "stato": "caricamento"})
        try:
            await asyncio.to_thread(load_engine)
        except Exception as exc:  # il core resta vivo: senza modello si può
            state["modello"] = "errore"  # ancora consultare le call passate
            broadcaster.publish({"type": "modello", "stato": "errore", "dettaglio": str(exc)})
            return
        state["modello"] = "pronto"
        broadcaster.publish({"type": "modello", "stato": "pronto"})

    async def get_engine_async():
        # Se qualcuno preme "Registra" prima che il precaricamento finisca, si
        # aspetta qui — in un thread, non sul loop.
        return await asyncio.to_thread(load_engine)

    async def get_recorder() -> Recorder:
        if state["recorder"] is None:
            engine = await get_engine_async()
            if recorder_factory is not None:
                # Iniettabile dai test con una firma fissa a tre posizionali:
                # non le si forza `settings`, che il doppio potrebbe non
                # accettare. È il percorso di produzione qui sotto che deve
                # leggere `stt.microfono_id`/`loopback_id`/`filtro_eco` per
                # davvero.
                state["recorder"] = recorder_factory(engine, store, _publish_event)
            else:
                state["recorder"] = Recorder(
                    engine, store, on_event=_publish_event, settings=settings
                )
        return state["recorder"]

    def _publish_event(ev: TranscriptEvent) -> None:
        broadcaster.publish(
            {
                "type": "transcript",
                "source": ev.source,
                "t_start_ms": ev.t_start_ms,
                "t_end_ms": ev.t_end_ms,
                "text": ev.text,
                "is_final": ev.is_final,
            }
        )

    def check_token(token_param: str = Query(..., alias="token")) -> None:
        # `compare_digest` invece di `==`: il confronto normale esce al primo
        # byte diverso e i tempi di risposta rivelano il token un carattere
        # alla volta.
        if not secrets.compare_digest(token_param, token):
            raise HTTPException(status_code=401, detail="token non valido")

    def _annuncia_call(call) -> None:
        """Una call è cominciata: si propone, non si avvia.

        Registrare coinvolge altre persone. Che il rilevamento sia sicuro non
        rende la decisione meno di chi usa l'applicazione: anche con
        `rilevamento.avvio_automatico` a vero, qui non si chiama mai
        `recorder.start`. Cambia solo l'insistenza con cui si chiede — la
        chiave dice all'interfaccia di aprire subito la finestra col consenso
        già davanti, invece di lasciare una proposta che si può ignorare —
        e quella lettura la decide questa funzione, non l'interfaccia da sola.
        """
        recorder = state.get("recorder")
        if recorder is not None and recorder.is_recording:
            return  # si sta già registrando: non c'è niente da proporre
        conf = settings.tutto().get("rilevamento", {})
        broadcaster.publish(
            {
                "type": "call_rilevata",
                "pid": call.pid,
                "processo": call.processo,
                "piattaforma": call.piattaforma,
                "nome": call.nome,
                # Letta ora e non quando il rilevatore è partito, così chi
                # cambia l'impostazione a metà giornata la vede applicata
                # dalla prossima call rilevata, senza dover riavviare nulla.
                "avvio_automatico": bool(conf.get("avvio_automatico", False)),
            }
        )

    def _avvia_rilevatore() -> None:
        conf = settings.tutto().get("rilevamento", {})
        if not conf.get("attivo", True):
            return
        try:
            from .detect.call import RilevatoreCall

            rilevatore = RilevatoreCall(
                _annuncia_call, conferma_s=float(conf.get("conferma_s", 5.0))
            )
            rilevatore.start()
            state["rilevatore"] = rilevatore
        except Exception as exc:
            # Il rilevamento è una comodità: se non parte, l'applicazione
            # funziona lo stesso avviando a mano.
            log.warning("Rilevamento delle call non avviato: %s", exc)

    app.router.lifespan_context = _lifespan(broadcaster, state, preload, _avvia_rilevatore, store)

    # ------------------------------------------------------------------- stato

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Senza token: serve al processo padre per sapere quando il core è su."""
        recorder = state.get("recorder")
        return {
            "ok": True,
            "modello": state["modello"],
            "in_registrazione": bool(recorder and recorder.is_recording),
            # Presente solo se all'avvio il database era illeggibile: dice dove
            # sono finiti i file messi da parte e da quale backup si è ripartiti.
            "db_danneggiato": state.get("db_danneggiato"),
            # Da che build viene questo processo. Non la legge da un file suo:
            # gliela passa chi lo avvia (`SCRIBA_VERSIONE`/`SCRIBA_COMMIT` in
            # ui/main/sidecar.ts), perché interfaccia e core escono sempre dalla
            # stessa compilazione e due numeri letti da due posti diversi prima
            # o poi non coincidono. Avviato a mano, restano None — che è la
            # verità: quel core non appartiene a nessuna build.
            "versione": os.environ.get("SCRIBA_VERSIONE"),
            "commit": os.environ.get("SCRIBA_COMMIT"),
        }

    @app.get("/session/state", dependencies=[Depends(check_token)])
    async def session_state() -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None or not recorder.is_recording:
            return {"in_registrazione": False}
        return {
            "in_registrazione": True,
            "session_id": recorder.session_id,
            "now_ms": recorder.now_ms(),
            "stato": recorder.clock.state.value if recorder.clock else None,
        }

    # ------------------------------------------------------------ registrazione

    @app.post("/session/start", dependencies=[Depends(check_token)])
    async def session_start(req: StartRequest) -> dict[str, Any]:
        recorder = await get_recorder()
        if recorder.is_recording:
            raise HTTPException(status_code=409, detail="registrazione già in corso")

        import time

        try:
            info = await asyncio.to_thread(
                recorder.start,
                titolo=req.titolo,
                piattaforma=req.piattaforma,
                lingua=req.lingua or str(settings.tutto().get("stt", {}).get("lingua") or "it"),
                consenso_confermato_at=int(time.time() * 1000) if req.consenso_confermato else None,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if settings.tutto().get("note_incrementali", False):
            try:
                gestore_note.avvia(info.session_id)
            except Exception:
                # Le note di lavoro sono un aiuto durante la call, non la
                # ragione per cui esiste: un guasto qui non deve impedire la
                # registrazione, che è la cosa che nessuno può recuperare dopo.
                log.exception("Note incrementali non avviate per la sessione %s", info.session_id)

        payload = {
            "session_id": info.session_id,
            "started_at_ms": info.started_at_ms,
            "devices": {s: d.name for s, d in info.devices.items()},
            # Quali sorgenti sono ripiegate sul predefinito perché il device
            # scelto nelle impostazioni non c'è più (cuffie staccate, scheda
            # cambiata): senza dirlo subito, chi ha registrato con l'audio
            # sbagliato lo scopre solo a call finita, quando non si rifà.
            "fallback": info.fallback,
        }
        broadcaster.publish({"type": "session_started", **payload})
        return payload

    @app.post("/session/stop", dependencies=[Depends(check_token)])
    async def session_stop() -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None or not recorder.is_recording:
            raise HTTPException(status_code=409, detail="nessuna registrazione in corso")
        session_id = await asyncio.to_thread(recorder.stop)

        try:
            # Sempre, anche se non era mai partita: deve essere sicura a
            # prescindere, per contratto.
            gestore_note.ferma()
        except Exception:
            log.exception("Chiusura delle note incrementali non riuscita per la sessione %s", session_id)

        # La registrazione è finita: è il momento in cui la call va messa in
        # sicurezza. Finché resta solo nel WAL, l'unica copia di quello che è
        # stato detto è un file che nessuno consolida (vedi Store.consolida).
        await asyncio.to_thread(store.consolida)
        await asyncio.to_thread(manutenzione.backup, store)

        broadcaster.publish({"type": "session_stopped", "session_id": session_id})
        if session_id is not None:
            # Nessuno l'ha chiesta esplicitamente: parte in disparte e non deve
            # allungare l'attesa di chi ha appena premuto "stop".
            asyncio.create_task(_prova_analisi_automatica(session_id))
        return {"session_id": session_id}

    @app.post("/session/pause", dependencies=[Depends(check_token)])
    async def session_pause() -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None or not recorder.is_recording:
            raise HTTPException(status_code=409, detail="nessuna registrazione in corso")
        recorder.pause()
        return {"stato": "paused"}

    @app.post("/session/resume", dependencies=[Depends(check_token)])
    async def session_resume() -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None:
            raise HTTPException(status_code=409, detail="nessuna registrazione in corso")
        recorder.resume()
        return {"stato": "recording"}

    @app.post("/session/screenshot", dependencies=[Depends(check_token)])
    async def session_screenshot(req: ScreenshotRequest) -> dict[str, Any]:
        recorder = state.get("recorder")
        if recorder is None or not recorder.is_recording:
            raise HTTPException(status_code=409, detail="nessuna registrazione in corso")
        shot_id, t_ms = recorder.add_screenshot(
            req.path, nota_utente=req.nota_utente, width=req.width, height=req.height
        )
        payload = {"type": "screenshot", "id": shot_id, "t_ms": t_ms, "path": req.path}
        broadcaster.publish(payload)
        return {"id": shot_id, "t_ms": t_ms}

    # ---------------------------------------------------------------- analisi

    def _avvia_analisi_task(session_id: int, provider, provider_conf: dict[str, Any]) -> None:
        """Fa davvero partire un'analisi: fasi, thread di lavoro, eventi.

        Condivisa fra la rotta esplicita e l'avvio automatico a fine
        registrazione (`_prova_analisi_automatica`): la call non deve poter
        finire in due analisi che girano insieme sullo stesso stato
        condiviso. Chi chiama si è già assicurato che non ce ne sia una in
        corso e che il motore risponda.
        """
        from .ai.analyze import AnalisiInterrotta, Analizzatore
        from .llm.base import LLMError

        provider_id = provider_conf.get("provider", "local")
        etichetta_provider = PROVIDERS_INFO.get(provider_id, {}).get("etichetta", provider_id)

        fasi = [
            {"chiave": chiave, "titolo": titolo, "stato": "attesa", "nota": "in attesa"}
            for chiave, titolo in FASI_ANALISI
        ]
        annulla = threading.Event()
        state["analisi_in_corso"] = True
        state["analisi_fasi"] = fasi
        state["analisi_session_id"] = session_id
        state["analisi_annulla"] = annulla

        def _fase_aggiornata(chiave: str, stato: str, nota: str | None) -> None:
            # Gira nel thread dell'analisi. È anche l'unico punto in cui si
            # controlla se è stato chiesto di interrompere: è il momento in cui
            # il lavoro passa da una fase all'altra, l'unico in cui fermarsi non
            # butta via un risultato a metà.
            if annulla.is_set():
                raise AnalisiInterrotta("interrotta dall'utente")
            for f in fasi:
                if f["chiave"] == chiave:
                    f["stato"], f["nota"] = stato, nota
                    break
            broadcaster.publish(
                {"type": "analisi", "stato": "in_corso", "session_id": session_id, "fasi": fasi}
            )

        async def lavora() -> None:
            inizio = time.time()
            try:
                # In un thread: l'analisi dura minuti e sul loop bloccherebbe
                # tutto, compresa la trascrizione di un'eventuale call successiva.
                analisi = await asyncio.to_thread(
                    Analizzatore(provider, store, on_fase=_fase_aggiornata).analizza, session_id
                )
            except AnalisiInterrotta:
                store.set_session_state(session_id, "error")
                store.set_analysis_errore(session_id, "Interrotta dall'utente.")
                broadcaster.publish(
                    {"type": "analisi", "stato": "errore", "session_id": session_id,
                     "dettaglio": "Interrotta dall'utente."}
                )
                return
            except LLMError as exc:
                store.set_session_state(session_id, "error")
                store.set_analysis_errore(session_id, str(exc))
                broadcaster.publish(
                    {"type": "analisi", "stato": "errore", "session_id": session_id,
                     "dettaglio": str(exc)}
                )
                return
            except Exception as exc:  # pragma: no cover
                log.exception("Analisi della sessione %s non riuscita", session_id)
                store.set_session_state(session_id, "error")
                store.set_analysis_errore(session_id, str(exc))
                broadcaster.publish(
                    {"type": "analisi", "stato": "errore", "session_id": session_id,
                     "dettaglio": str(exc)}
                )
                return
            finally:
                state["analisi_in_corso"] = False
                state["analisi_session_id"] = None
                state["analisi_fasi"] = []
                state["analisi_annulla"] = None

            store.set_analysis_meta(
                session_id,
                provider=analisi.provider or provider_id,
                etichetta_provider=etichetta_provider,
                modello=analisi.modello or None,
                costo_usd=round(analisi.costo_usd, 4),
                durata_ms=int((time.time() - inizio) * 1000),
                finita_at=int(time.time() * 1000),
            )
            # Un'analisi sono minuti di lavoro e, con un'API, anche dei soldi:
            # non resta appesa a un WAL che nessuno consolida.
            await asyncio.to_thread(store.consolida)

            broadcaster.publish(
                {
                    "type": "analisi",
                    "stato": "fatto",
                    "session_id": session_id,
                    "tasks": len(analisi.tasks),
                    "costo_usd": round(analisi.costo_usd, 4),
                    "tokens_in": analisi.tokens_in,
                    "tokens_out": analisi.tokens_out,
                    "modello": analisi.modello,
                }
            )

            await _sincronizza_se_richiesto(session_id, store, broadcaster)

        # Si risponde subito e si lavora dopo. Tenere aperta una richiesta HTTP
        # per mezz'ora non funziona: il client la chiude molto prima, e chi
        # aspettava quella risposta per sapere che il lavoro era finito resta ad
        # aspettare per sempre, anche se il lavoro nel frattempo è riuscito.
        broadcaster.publish(
            {"type": "analisi", "stato": "in_corso", "session_id": session_id, "fasi": fasi}
        )
        asyncio.create_task(lavora())

    async def _prova_rifinitura_automatica(session_id: int) -> None:
        """Ripassa la trascrizione prima dell'analisi, se è stato chiesto.

        Prima, non dopo: l'analisi legge la trascrizione, e deve leggere quella
        rifinita. Farle al contrario significherebbe estrarre le task dal testo
        che si è appena deciso di non tenere.

        Spenta di default. Ogni condizione mancante fa uscire in silenzio: è un
        di più, e non deve poter far sembrare rotta una call registrata bene.
        """
        conf = settings.tutto().get("stt", {})
        if not conf.get("rifinitura_automatica", False):
            return
        avvia = state.get("avvia_rifinitura")
        if avvia is None or (state.get("rifinitura") or {}).get("in_corso"):
            return
        if not store.segments(session_id, only_final=True):
            return
        from .models_manager import modello_gestito_installato

        if not await asyncio.to_thread(modello_gestito_installato, "canary-1b-v2"):
            log.info("Rifinitura automatica saltata: il modello non è ancora scaricato.")
            return
        try:
            avvia(session_id)
            task = state.get("rifinitura_task")
            if task is not None:
                await task
        except Exception:
            log.exception("Rifinitura automatica non riuscita per la sessione %s", session_id)

    async def _prova_analisi_automatica(session_id: int) -> None:
        """Fa partire l'analisi da sola a fine registrazione, se si può.

        Gira come task a parte dopo che `/session/stop` ha già risposto:
        nessuno ha chiesto questa analisi esplicitamente, quindi non deve
        allungare di un millisecondo l'attesa di chi ha premuto "stop", né
        rischiare di far sembrare rotta una call che è stata registrata bene.
        Ogni condizione mancante fa uscire in silenzio, non con un errore.
        """
        await asyncio.sleep(RITARDO_ANALISI_AUTOMATICA_S)
        await _prova_rifinitura_automatica(session_id)
        if not settings.tutto().get("analisi_automatica", True):
            return
        if state["analisi_in_corso"]:
            return  # non se ne avvia una seconda
        if not store.segments(session_id):
            return  # niente da leggere senza una trascrizione

        from .llm.providers import costruisci

        provider_conf = settings.llm()
        try:
            provider = costruisci(provider_conf)
            raggiungibile = await asyncio.to_thread(provider.available)
        except Exception:
            raggiungibile = False
        if not raggiungibile:
            # Il motore non risponde: non è un guasto della call, solo
            # un'analisi che oggi non può partire. Si lascia "registrata".
            return

        # Fra l'inizio di questa funzione e adesso il loop ha ceduto il passo
        # più volte (i due `await` sopra): un'analisi esplicita potrebbe essere
        # partita nel frattempo. Si ricontrolla prima di far partire la nostra.
        if state["analisi_in_corso"]:
            return

        _avvia_analisi_task(session_id, provider, provider_conf)

    @app.post("/sessions/{session_id}/analyze", dependencies=[Depends(check_token)])
    async def analyze(session_id: int) -> dict[str, Any]:
        from .llm.providers import costruisci

        if state["analisi_in_corso"]:
            # Se sta già girando proprio su questa call, la richiesta è
            # soddisfatta: si risponde di sì invece di rifiutare.
            #
            # Non è pignoleria. A fine registrazione l'analisi parte da sola;
            # chi preme "Rianalizza" un attimo dopo vuole esattamente quello
            # che sta già succedendo, e un 409 gli mostrerebbe un errore mentre
            # il lavoro è in corso — con l'interfaccia che a quel punto smette
            # pure di aspettare il risultato, restando ferma su un guasto che
            # non c'è. Il ritardo prima dell'analisi automatica riduce la
            # finestra in cui questo accade, ma non la chiude: qui la si chiude.
            if state.get("analisi_session_id") == session_id:
                return {"session_id": session_id, "stato": "già_avviata"}
            raise HTTPException(status_code=409, detail="un'analisi è già in corso")

        provider_conf = settings.llm()
        provider = costruisci(provider_conf)
        if not provider.available():
            raise HTTPException(
                status_code=412,
                detail="Il modello di analisi non è raggiungibile. Se usi quello locale, "
                "avvia llama-server; se usi l'abbonamento Claude, rifai l'accesso con "
                "`claude auth login`; se usi un'API, controlla la chiave nelle impostazioni.",
            )

        _avvia_analisi_task(session_id, provider, provider_conf)
        return {"session_id": session_id, "stato": "avviata"}

    @app.get("/analisi/stato", dependencies=[Depends(check_token)])
    async def analisi_stato() -> dict[str, Any]:
        """Permette all'interfaccia di ritrovare la verità.

        Un'interfaccia che si fida solo degli eventi resta ferma per sempre
        quando ne perde uno — ed è successo: due ore a mostrare "in corso" per
        un'analisi finita da un pezzo. Le fasi tornano per lo stesso motivo:
        chi apre la finestra a metà lavoro deve vedere a che punto è, non solo
        che qualcosa sta succedendo.
        """
        return {
            "in_corso": bool(state["analisi_in_corso"]),
            "session_id": state.get("analisi_session_id"),
            "fasi": state.get("analisi_fasi") or [],
        }

    @app.get("/sessions/{session_id}/analysis", dependencies=[Depends(check_token)])
    async def analysis(session_id: int) -> dict[str, Any]:
        output = {
            r["kind"]: r["content_md"]
            for r in store.conn.execute(
                "SELECT kind, content_md FROM ai_outputs WHERE session_id = ? AND is_current = 1",
                (session_id,),
            )
        }
        tasks = []
        for t in store.conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? AND stato <> 'rejected' ORDER BY id",
            (session_id,),
        ):
            task = dict(t)
            task["evidence"] = [
                {
                    "supports": e["supports"],
                    "t_ms": e["t_ms"],
                    "quote": e["quote"],
                    "segment_id": e["segment_id"],
                }
                for e in store.task_evidence(t["id"])
            ]
            tasks.append(task)

        riassunto = output.get("summary")
        punti_salienti = output.get("highlights")

        meta_row = store.get_analysis_meta(session_id)
        meta = None
        errore = None
        if meta_row is not None:
            errore = meta_row["errore"]
            # finita_at si valorizza solo su un'analisi riuscita (vedi
            # set_analysis_meta/set_analysis_errore): la sua presenza è come si
            # distingue "non ancora analizzata" da "analizzata, ma l'ultimo
            # tentativo di rianalisi è fallito".
            if meta_row["finita_at"] is not None:
                meta = {
                    "provider": meta_row["provider"],
                    "etichetta_provider": meta_row["etichetta_provider"],
                    "modello": meta_row["modello"],
                    "costo_usd": meta_row["costo_usd"],
                    "durata_ms": meta_row["durata_ms"],
                    "finita_at": meta_row["finita_at"],
                }

        return {
            "riassunto": riassunto,
            "punti_salienti": punti_salienti,
            "riassunto_gruppi": _riassunto_a_gruppi(riassunto),
            "salienti": _salienti_da_markdown(punti_salienti),
            "tasks": tasks,
            "meta": meta,
            "errore": errore,
        }

    @app.post("/tasks/{task_id}", dependencies=[Depends(check_token)])
    async def update_task(task_id: int, modifiche: dict[str, Any]) -> dict[str, Any]:
        campi = {
            k: v
            for k, v in modifiche.items()
            if k in {"titolo", "descrizione", "assignee_text", "due_date", "priorita", "stato"}
        }
        if not campi:
            raise HTTPException(status_code=400, detail="nessun campo modificabile")

        # Se l'utente ha messo mano a una task, l'ha guardata: non ha piu' senso
        # segnalargliela come da rivedere.
        campi["needs_review"] = 0
        assegnazioni = ", ".join(f"{k} = ?" for k in campi)
        with store.tx() as conn:
            conn.execute(
                f"UPDATE tasks SET {assegnazioni} WHERE id = ?", (*campi.values(), task_id)
            )
        row = store.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="task inesistente")
        return dict(row)

    # ------------------------------------------------------------ impostazioni

    @app.get("/settings", dependencies=[Depends(check_token)])
    async def get_settings() -> dict[str, Any]:
        return settings.tutto()

    @app.get("/providers", dependencies=[Depends(check_token)])
    async def providers() -> list[dict[str, Any]]:
        """Quali motori di analisi sono utilizzabili in questo momento.

        Non basta elencarli: un motore locale spento e un `claude` non
        installato sono voci che si possono selezionare ma non funzionano, e lo
        si scoprirebbe solo a fine call. Qui si verifica adesso.
        """
        from .llm.providers import costruisci

        attuale = settings.llm()
        elenco = [
            {
                "id": id_,
                "etichetta": info["etichetta"],
                "descrizione": info["descrizione"],
                "model": attuale.get("model") if attuale.get("provider") == id_ else info["model"],
                "esce_dal_computer": info["esce_dal_computer"],
                "costo_ora_eur": info["costo_ora_eur"],
                "minuti_per_ora": info["minuti_per_ora"],
            }
            for id_, info in PROVIDERS_INFO.items()
        ]

        for voce in elenco:
            configurazione = dict(attuale)
            configurazione["provider"] = voce["id"]
            configurazione.setdefault("model", voce["model"])
            try:
                voce["disponibile"] = await asyncio.to_thread(
                    costruisci(configurazione).available
                )
            except Exception:
                voce["disponibile"] = False
            voce["attivo"] = voce["id"] == attuale.get("provider")
            # Il modello locale può essere partito e non rispondere ancora:
            # caricare un GGUF da 7-9 GB richiede decine di secondi. Dirlo
            # «non disponibile» in quella finestra è falso, e il rimedio
            # («scarica e avvia il modello») è quello che l'utente ha appena
            # fatto.
            gestore = state.get("gestore_modelli")
            voce["in_avvio"] = bool(
                voce["id"] == "local"
                and not voce["disponibile"]
                and gestore is not None
                and gestore.server_in_avvio()
            )
            # Detto solo quando serve: una voce già utilizzabile, o che sta
            # arrivando, non ha nulla da rimediare.
            voce["rimedio"] = (
                None
                if voce["disponibile"] or voce["in_avvio"]
                else PROVIDERS_INFO[voce["id"]]["rimedio"]
            )
        return elenco

    @app.post("/settings", dependencies=[Depends(check_token)])
    async def post_settings(modifiche: dict[str, Any]) -> dict[str, Any]:
        return settings.aggiorna(modifiche)

    # ---------------------------------------------------------------- lettura

    @app.get("/sessions", dependencies=[Depends(check_token)])
    async def sessions(limit: int = 50) -> list[dict[str, Any]]:
        # n_task e n_da_confermare in una query sola con LEFT JOIN + COUNT
        # condizionale: l'elenco si ricarica a ogni fine registrazione, e una
        # query per sessione per contare le task diventerebbe lenta con lo
        # storico che cresce.
        rows = store.conn.execute(
            """
            SELECT s.id, s.titolo, s.piattaforma, s.started_at, s.ended_at,
                   s.durata_ms, s.stato, s.lingua, s.client_id,
                   c.nome AS cliente,
                   COUNT(CASE WHEN t.stato <> 'rejected' THEN 1 END) AS n_task,
                   COUNT(CASE WHEN t.stato <> 'rejected' AND t.needs_review = 1
                              THEN 1 END) AS n_da_confermare
              FROM sessions s
              LEFT JOIN clients c ON c.id = s.client_id
              LEFT JOIN tasks t ON t.session_id = s.id
             GROUP BY s.id
             ORDER BY s.started_at DESC
             LIMIT ?
            """,
            (limit,),
        )
        sessione_in_analisi = state.get("analisi_session_id") if state.get("analisi_in_corso") else None
        risultato = []
        for r in rows:
            voce = dict(r)
            voce["stato"] = _traduci_stato_sessione(
                voce["stato"], in_analisi=voce["id"] == sessione_in_analisi
            )
            risultato.append(voce)
        return risultato

    @app.get("/sessions/{session_id}/note", dependencies=[Depends(check_token)])
    async def note_correnti(session_id: int) -> dict[str, Any]:
        """Le note di lavoro scritte mentre la call andava.

        Restituisce l'ultima a parte, oltre a tutte: ogni nota riscrive la
        precedente incorporandola, quindi è quella da mostrare — le altre
        raccontano come è cambiata la comprensione della riunione, ed è
        un'altra domanda.
        """
        righe = [dict(r) for r in store.note_correnti(session_id)]
        for r in righe:
            # I candidati sono JSON in una colonna di testo: si consegnano già
            # decodificati, così l'interfaccia non deve saperlo.
            grezzo = r.pop("content_json", None)
            try:
                r["candidati"] = json.loads(grezzo) if grezzo else []
            except (TypeError, ValueError):
                r["candidati"] = []
        return {
            "session_id": session_id,
            "note": righe,
            "ultima": righe[-1] if righe else None,
            "attive": bool(settings.tutto().get("note_incrementali", False)),
        }

    @app.get("/sessions/{session_id}/segments", dependencies=[Depends(check_token)])
    async def segments(session_id: int) -> list[dict[str, Any]]:
        # `diarizzata_at` distingue «non l'ha mai fatta nessuno» da «fatta, e
        # non ha trovato altre voci». Senza, una call con un solo interlocutore
        # sembrerebbe in attesa di un lavoro che invece è già stato fatto.
        sessione = store.get_session(session_id)
        diarizzata = sessione is not None and sessione["diarizzata_at"] is not None

        return [
            {
                "id": s.id,
                # `source` viene dalla traccia da cui il suono è entrato: è
                # l'unica cosa che nessun modello può smentire, e resta anche
                # dopo la diarizzazione.
                "source": s.source,
                "t_start_ms": s.t_start_ms,
                "t_end_ms": s.t_end_ms,
                "testo": s.testo,
                "is_final": s.is_final,
                "revision": s.revision,
                # Riconosciuta come ritorno dell'altoparlante. Arrivano fin qui
                # apposta: sono già fuori da riassunto, note ed export, e
                # questa è l'unica schermata in cui si può controllare che il
                # giudizio fosse giusto. Nasconderle anche qui vorrebbe dire
                # cancellarle con un altro nome.
                "eco": s.eco,
                "speaker": (
                    {
                        "id": s.speaker_id,
                        "label": s.speaker_label,
                        "nome_reale": s.speaker_nome_reale,
                    }
                    if diarizzata and s.speaker_id is not None
                    else None
                ),
            }
            for s in store.segments(session_id, includi_eco=True)
        ]

    @app.post("/sessions/{session_id}/export/markdown", dependencies=[Depends(check_token)])
    async def export_markdown(session_id: int, req: ExportRequest) -> dict[str, Any]:
        from .export.markdown import esporta

        destinazione = Path(req.destinazione) if req.destinazione else db_path.parent / "export"
        try:
            percorso = await asyncio.to_thread(esporta, store, session_id, destinazione)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"percorso": str(percorso)}

    @app.post("/rilevamento/ignora/{pid}", dependencies=[Depends(check_token)])
    async def rilevamento_ignora(pid: int) -> dict[str, Any]:
        """L'utente ha detto di no a questa call.

        Non si smette di sorvegliare: si dimentica solo questa proposta, così
        alla riunione successiva la domanda torna. Chi rifiuta una volta non sta
        disattivando la funzione.
        """
        rilevatore = state.get("rilevatore")
        if rilevatore is not None:
            rilevatore.dimentica(pid)
        return {"ok": True}

    @app.get("/rilevamento/diagnostica", dependencies=[Depends(check_token)])
    async def rilevamento_diagnostica() -> dict[str, Any]:
        """Cosa sta vedendo il rilevamento in questo momento.

        Esiste perché «non mi ha proposto di registrare» ha almeno cinque cause
        possibili, tutte plausibili e nessuna distinguibile dall'esterno: la
        sonda non parte, il processo è nell'elenco degli esclusi, il microfono
        non dà segnale, l'audio non risulta in riproduzione, l'attesa di
        conferma non è ancora scaduta. Mostrarle è la differenza fra leggere un
        difetto e indovinarlo.
        """
        rilevatore = state.get("rilevatore")
        if rilevatore is None:
            # Spento nelle impostazioni, oppure mai avviato. Va detto: una
            # schermata vuota qui si legge come "non vedo nessuna riunione",
            # che è una risposta diversa e sbagliata.
            attivo = bool((settings.tutto().get("rilevamento") or {}).get("attivo"))
            return {
                "in_ascolto": False,
                "spento": not attivo,
                "conferma_s": None,
                "intervallo_s": None,
                "sonda": None,
                "riproducono": [],
                "processi": [],
            }
        return {"spento": False, **rilevatore.diagnostica()}

    @app.get("/search", dependencies=[Depends(check_token)])
    async def search(q: str, limit: int = 50) -> list[dict[str, Any]]:
        return [dict(r) for r in store.search(q, limit=limit)]

    # -------------------------------------------------------------- websocket

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket, token_param: str = Query(..., alias="token")) -> None:
        if not secrets.compare_digest(token_param, token):
            await ws.close(code=4401)
            return
        await broadcaster.connect(ws)
        try:
            while True:
                # Non si aspettano comandi dal client — i comandi passano dalle
                # rotte HTTP. Leggere serve solo ad accorgersi della chiusura.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.disconnect(ws)

    # -------------------------------------------------------- rotte per argomento
    #
    # Montate qui, non definite qui: modelli locali e dispositivi cambiano molto
    # più spesso del resto e non c'è motivo di farli abitare nella stessa
    # funzione della registrazione.
    from .api import Contesto
    from .api import clienti as api_clienti
    from .api import database_remoto as api_database_remoto
    from .api import export as api_export
    from .api import modelli as api_modelli
    from .api import note as api_note
    from .api import rifinitura as api_rifinitura
    from .api import sistema as api_sistema

    contesto = Contesto(
        store=store,
        settings=settings,
        db_path=Path(db_path),
        publish=broadcaster.publish,
        state=state,
    )
    fabbriche_router = [
        api_clienti.crea_router,
        api_database_remoto.crea_router,
        api_export.crea_router,
        api_modelli.crea_router,
        api_note.crea_router,
        api_rifinitura.crea_router,
        api_sistema.crea_router,
    ]
    # Un altro agente sta scrivendo questo modulo adesso (vedi
    # contratto-moduli.md): finché il file non esiste sul disco si monta solo
    # quello che c'è, invece di far fallire l'avvio dell'intero server per un
    # pezzo che qualcun altro sta ancora scrivendo.
    try:
        from .api import diarizzazione as api_diarizzazione
    except ImportError:
        pass
    else:
        fabbriche_router.append(api_diarizzazione.crea_router)

    for crea in fabbriche_router:
        app.include_router(crea(contesto), dependencies=[Depends(check_token)])

    app.state.store = store
    app.state.settings = settings
    # Lo stato condiviso fra le rotte (`modello`, `recorder`, `analisi_*`,
    # `rifinitura`). Esposto qui perché è l'unico modo di osservarlo dall'esterno
    # senza inventarsi una rotta che esista solo per i test.
    app.state.stato_server = state
    app.state.token = token
    return app


def _exit_when_orphaned(server=None, grazia_s: float = 4.0) -> None:
    """Si spegne quando il processo padre sparisce.

    Se l'interfaccia va in crash, questo processo resterebbe vivo tenendo
    occupato il microfono: alla registrazione successiva il device risulta in
    uso e non si capisce perché. Il canale è lo standard input, che il sistema
    chiude quando il padre muore — funziona anche quando il padre non ha fatto
    in tempo a terminarci.

    Prima si chiede a uvicorn di fermarsi, e solo se non lo fa entro `grazia_s`
    si esce di forza. Uscire subito era il comportamento precedente, ed è
    costato dati: `os._exit` salta lo spegnimento dell'applicazione, quindi
    salta il consolidamento del WAL — cioè l'unico momento in cui quello che una
    call ha scritto finisce davvero nel database.

    `grazia_s` sta sotto l'attesa di `Sidecar.stop()` di proposito: chi si ferma
    per primo deve essere il core, così l'uccisione dell'albero dal lato Electron
    resta l'ultima rete e non la regola.

    Va attivata esplicitamente da chi lancia il processo. Attivarla sempre
    sarebbe un disastro: avviato da riga di comando o dai test, lo stdin è
    chiuso in partenza, il primo `readline` restituisce EOF e il core si
    spegnerebbe appena avviato.
    """
    import os
    import sys

    def watch() -> None:
        try:
            while sys.stdin.readline():
                pass
        except Exception:
            pass
        if server is not None:
            # Fa uscire `serve()`, che porta con sé lo spegnimento ordinato.
            server.should_exit = True
            scadenza = time.time() + grazia_s
            while time.time() < scadenza:
                if getattr(server, "started", False) is False:
                    break
                time.sleep(0.2)
        # Rete di sicurezza: a questo punto non c'è più nessuno a cui rispondere,
        # e uno spegnimento che si è impuntato non deve lasciare un orfano.
        os._exit(0)

    threading.Thread(target=watch, name="orphan-watch", daemon=True).start()


def run(
    db_path: Path | str = "data/scriba.sqlite",
    host: str = "127.0.0.1",
    *,
    watch_parent: bool = False,
) -> None:
    """Avvia il core e annuncia al processo padre dove trovarlo.

    La porta la sceglie il sistema: si stampa su stdout una riga JSON con porta
    e token, che è il modo in cui la shell Electron scopre come collegarsi.
    """
    import socket

    import uvicorn

    token = secrets.token_urlsafe(32)

    # Si apre il socket qui, così la porta è nota prima dell'avvio e si può
    # annunciare subito. Il socket viene poi passato a uvicorn già aperto:
    # chiuderlo e ridare solo il numero lascerebbe una finestra in cui un altro
    # processo può prendersi quella porta.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, 0))
    # `listen` qui e non solo dentro uvicorn: fra l'annuncio della porta e il
    # momento in cui uvicorn e' pronto passa quasi un secondo, e in quella
    # finestra le richieste verrebbero rifiutate con "connection refused".
    # Mettendosi in ascolto subito, restano in coda finche' non c'e' chi
    # risponde.
    sock.listen(128)
    port = sock.getsockname()[1]

    print(json.dumps({"port": port, "token": token}), flush=True)

    app = create_app(db_path=Path(db_path), token=token)
    # `sockets=[...]` e non `fd=`: quest'ultimo in uvicorn passa da
    # `socket.fromfd(..., AF_UNIX)`, che su Windows non esiste.
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))

    # Dopo aver costruito il server, non prima: la sorveglianza sul padre deve
    # potergli chiedere di fermarsi in modo ordinato, che è ciò che consolida il
    # WAL. Senza il riferimento resterebbe solo l'uscita brutale.
    if watch_parent:
        _exit_when_orphaned(server)

    server.run(sockets=[sock])


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Core di Scriba")
    parser.add_argument("db", nargs="?", default="data/scriba.sqlite")
    parser.add_argument(
        "--watch-parent",
        action="store_true",
        help="spegniti quando chi ti ha avviato chiude lo standard input. "
        "Lo usa l'interfaccia; da riga di comando lascialo stare, o il core "
        "esce subito.",
    )
    args = parser.parse_args()
    run(args.db, watch_parent=args.watch_parent)
