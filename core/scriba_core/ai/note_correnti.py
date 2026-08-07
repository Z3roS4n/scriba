"""Nota di lavoro aggiornata mentre la call è ancora in corso.

`note_incrementali` era finora solo una chiave nelle impostazioni: qui diventa
davvero qualcosa. L'idea non è avere un riassunto a metà per il gusto di
averlo — è lo stesso motivo per cui `analyze.py` esiste in due passaggi: in una
riunione vera il lavoro si nomina al minuto 5, la scadenza si concorda al 32 e
il responsabile si decide al 48. Aspettare la fine della call per estrarre
tutto in un colpo solo costringe il modello a tenere insieme un'ora di
contesto. Una nota ogni dieci minuti, mentre quel contesto è ancora denso e
recente, può invece provare a estrarre i "candidati" di un impegno appena
accennato — esattamente la stessa forma prodotta dal primo passaggio
dell'analisi finale (`Analizzatore.candidati`) — cosicché un passaggio finale
possa, un giorno, ricomporli invece di dover rileggere tutta la trascrizione
da capo.

Due vincoli tengono insieme il resto:

- Il modello di analisi e quello di trascrizione girano sulla stessa macchina,
  e la trascrizione dal vivo ha la precedenza. Se una nota è ancora in corso
  quando scatta il giro successivo, si salta: mai due generazioni in corallo
  sulla stessa GPU/CPU mentre si sta ancora parlando.
- Un errore del modello qui non è un errore della call: si pubblica l'evento
  di errore e si continua, perché la registrazione sta ancora andando ed è
  quella la cosa da non perdere.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

from ..db.store import Segment, Store
from ..llm.providers import costruisci
from . import lingue, prompts
from .analyze import Analizzatore, formatta_segmenti

log = logging.getLogger(__name__)

# Il valore mostrato all'utente nelle impostazioni ("un riassunto parziale
# ogni dieci minuti"). Se la chiave `note_incrementali_intervallo_s` compare
# nelle impostazioni la si rispetta, ma questo resta il predefinito: non c'è
# uno schema da cambiare per aggiungerla, è letta al volo con un default.
INTERVALLO_DEFAULT_S = 600.0

# Quanti token può produrre l'aggiornamento della nota. Il prompt chiede
# "massimo 200 parole": in italiano un token vale grossomodo 0,6 parole, 500
# lascia margine senza invitare il modello a dilungarsi.
MAX_TOKENS_NOTA = 500


class GestoreNote:
    """Genera e pubblica la nota corrente, a intervalli, finché la call dura.

    La firma è quella fissata in `contratto-moduli.md`: `server.py` la
    costruisce con `(store, settings, publish)` e chiama `avvia`/`ferma`
    intorno alla registrazione, solo quando `note_incrementali` è vero.
    """

    def __init__(
        self,
        store: Store,
        settings: Any,
        publish: Callable[[dict], None],
    ) -> None:
        self.store = store
        self.settings = settings
        self.publish = publish

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # Fa da flag "una nota sta già generando": un Lock non bloccante è più
        # semplice di un booleano protetto a mano, e si libera da solo anche
        # se `_genera_nota` esce con un'eccezione, grazie al try/finally in
        # `_esegui_nota`.
        self._occupato = threading.Lock()

        self._session_id: int | None = None
        self._attivo = False

        # Stato che passa da una nota alla successiva: il testo per dare
        # continuità alla riscrittura, il cursore per sapere da dove
        # ricominciare, il contatore per rendere unici i temp_id dei
        # candidati fra un giro e l'altro (vedi `_genera_nota`).
        self._nota_testo = ""
        self._cursore_ms = 0
        self._contatore = 0

    @property
    def attivo(self) -> bool:
        return self._attivo

    # --------------------------------------------------------------- ciclo

    def avvia(self, session_id: int) -> None:
        """Comincia a generare note per questa sessione, una ogni intervallo.

        Si ferma prima qualunque cosa fosse rimasta accesa: `server.py`
        dovrebbe già garantire una `avvia` per call, ma ripartire da uno stato
        pulito costa poco ed evita che una sessione precedente rimasta a metà
        contamini quella nuova.
        """
        self.ferma()

        self._stop = threading.Event()
        self._occupato = threading.Lock()
        self._session_id = session_id
        self._nota_testo = ""
        self._cursore_ms = 0
        self._contatore = 0
        self._attivo = True

        self._thread = threading.Thread(
            target=self._loop, name="note-correnti", daemon=True
        )
        self._thread.start()

    def ferma(self) -> None:
        """Ferma la generazione. Sicura se non era mai partita, e due volte di fila.

        Aspetta che il thread che scandisce l'intervallo esca (è rapido: basta
        che si accorga che `_stop` è segnalato), ma non aspetta una nota
        eventualmente già in corso di generazione sul modello — può durare
        quanto una finestra intera, e non è compito di `ferma()` bloccare la
        fine della call per quello. Quella nota, se finisce, pubblica comunque
        il suo evento; se fallisce, pubblica l'errore. In entrambi i casi non
        lascia nulla accodato dietro di sé, perché non viene mai schedulato un
        secondo giro sopra a uno ancora aperto (vedi `_tenta_ciclo`).
        """
        thread, self._thread = self._thread, None
        self._attivo = False
        if thread is None:
            return
        self._stop.set()
        thread.join(timeout=5.0)

    def _loop(self) -> None:
        intervallo = self._intervallo_secondi()
        # `Event.wait` restituisce True solo se `_stop` viene segnalato prima
        # dello scadere: è così che si esce subito invece di aspettare fino
        # all'intervallo successivo quando arriva `ferma()`.
        while not self._stop.wait(intervallo):
            self._tenta_ciclo()

    def _intervallo_secondi(self) -> float:
        grezzo = INTERVALLO_DEFAULT_S
        try:
            grezzo = self.settings.tutto(con_segreti=True).get(
                "note_incrementali_intervallo_s", INTERVALLO_DEFAULT_S
            )
        except Exception:
            # Impostazioni non disponibili o di forma inattesa: meglio il
            # predefinito che bloccare l'intero ciclo prima ancora di partire.
            grezzo = INTERVALLO_DEFAULT_S
        try:
            valore = float(grezzo)
        except (TypeError, ValueError):
            return INTERVALLO_DEFAULT_S
        return valore if valore > 0 else INTERVALLO_DEFAULT_S

    def _tenta_ciclo(self) -> None:
        if not self._occupato.acquire(blocking=False):
            # La nota precedente sta ancora generando: si salta questo giro
            # invece di accodarne un secondo sopra al primo. La trascrizione
            # dal vivo, sulla stessa macchina, ha la precedenza — meglio una
            # nota in meno che farla arrancare.
            log.info("nota incrementale saltata: la precedente è ancora in corso")
            return
        threading.Thread(
            target=self._esegui_nota, name="nota-correnti-worker", daemon=True
        ).start()

    def _esegui_nota(self) -> None:
        try:
            self._genera_nota()
        finally:
            self._occupato.release()

    # ------------------------------------------------------------- una nota

    def _genera_nota(self) -> None:
        session_id = self._session_id
        if session_id is None:
            return

        nuovi: list[Segment] = [
            s
            for s in self.store.segments(session_id, only_final=True)
            if s.t_end_ms > self._cursore_ms
        ]
        if not nuovi:
            # Nessun segmento definitivo nuovo da quando è partita l'ultima
            # nota: non c'è nulla da aggiornare, e disturbare il modello per
            # ripetere la nota precedente identica non serve a nessuno.
            return

        self.publish({"type": "nota", "stato": "in_corso", "session_id": session_id})

        try:
            provider = costruisci(self.settings.llm())
            schermate = self.store.screenshots(session_id)
            inizio, fine = nuovi[0].t_start_ms, nuovi[-1].t_end_ms
            dentro_finestra = [s for s in schermate if inizio <= s["t_ms"] <= fine]

            # La nota si scrive nella lingua della call, come il riassunto
            # (#61): e' lo stesso testo, solo scritto mentre la riunione va.
            riga = self.store.conn.execute(
                "SELECT lingua FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            completamento = provider.complete(
                system=prompts.SYSTEM_REDAZIONE.format(
                    lingua=lingue.nome(riga["lingua"] if riga else None)
                ),
                user=prompts.RUNNING_NOTE_PROMPT.format(
                    nota_precedente=self._nota_testo
                    or "(nessuna nota precedente: è l'inizio della call)",
                    finestra=formatta_segmenti(nuovi, dentro_finestra),
                ),
                max_tokens=MAX_TOKENS_NOTA,
            )
        except Exception as exc:
            # Qui sta il vincolo centrale: un errore del modello non ferma la
            # call. Si segnala e basta, il cursore non avanza, così il giro
            # successivo riprova sulla stessa finestra invece di perderla.
            log.warning(
                "nota incrementale fallita per la sessione %s", session_id, exc_info=True
            )
            self.publish(
                {"type": "nota", "stato": "errore", "session_id": session_id, "dettaglio": str(exc)}
            )
            return

        nuova_nota = completamento.text.strip()

        # L'estrazione dei candidati è valore aggiunto, non il cuore della
        # nota: se fallisce non si butta via un riassunto già buono. Si tiene
        # la nota, i candidati di questo giro restano vuoti e si riprova al
        # prossimo — la finestra "persa" resta comunque coperta dal riassunto
        # finale a fine call.
        candidati: list[dict] = []
        try:
            self._contatore += 1
            # Stessa finestratura, stesso prompt, stesso schema del primo
            # passaggio dell'analisi finale: è quello che rende questi
            # candidati "della stessa forma" e quindi riutilizzabili da lì,
            # invece di essere un formato parallelo da tradurre.
            grezzi, _ = Analizzatore(provider, self.store).candidati(nuovi, schermate)
            # Il prefisso di Analizzatore.candidati riparte da "f0_" a ogni
            # chiamata: senza un prefisso per-nota, i candidati del minuto 10
            # e quelli del minuto 20 potrebbero condividere lo stesso temp_id
            # e un passaggio di unione li confonderebbe per lo stesso impegno.
            candidati = [
                {**c, "temp_id": f"nota{self._contatore}_{c['temp_id']}"} for c in grezzi
            ]
        except Exception:
            log.warning(
                "estrazione dei candidati parziali fallita per la sessione %s",
                session_id,
                exc_info=True,
            )

        # Un'unica riga in ai_outputs: il testo va in content_md, i candidati
        # (se ce ne sono) in content_json. Niente tabella nuova — ai_outputs è
        # già versionato per kind e per finestra (scope_start_ms/scope_end_ms),
        # ed è esattamente a cosa serve: ogni nota occupa la propria finestra
        # ed è "corrente" insieme a tutte le altre già prese in questa call.
        self.store.add_ai_output(
            session_id,
            "running_note",
            nuova_nota,
            model=completamento.model,
            provider=completamento.provider,
            prompt_id=prompts.RUNNING_NOTE[0],
            prompt_version=prompts.RUNNING_NOTE[1],
            scope_start_ms=self._cursore_ms,
            scope_end_ms=fine,
            content_json=json.dumps(candidati, ensure_ascii=False) if candidati else None,
            tokens_in=completamento.tokens_in,
            tokens_out=completamento.tokens_out,
            cost_usd=completamento.cost_usd,
        )

        self._nota_testo = nuova_nota
        self._cursore_ms = fine
        self.publish(
            {
                "type": "nota",
                "stato": "fatta",
                "session_id": session_id,
                "t_ms": fine,
                "testo": nuova_nota,
            }
        )
