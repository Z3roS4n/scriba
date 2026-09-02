"""Fare una domanda all'archivio, invece di dargli delle parole.

Il modello di linguaggio c'era già e analizzava ogni call appena finita. Su
tutto l'archivio — dove servirebbe di più, perché è lì che uno non ricorda —
non lo usava nessuno: si potevano dare parole e leggere i risultati uno per uno
(#105).

Come sta in piedi: la ricerca semantica sceglie il materiale, il modello lo
legge e risponde citando da dove viene. Non gli si dà l'archivio intero — non
ci starebbe nel contesto di nessun modello, e nemmeno servirebbe — ma nemmeno
un solo passaggio: i quaranta più vicini, raggruppati per call e per catena.

Due cose che questo file non fa, e sono deliberate:

**Non risponde senza indice.** Senza i vettori si dovrebbe scegliere il
materiale con la ricerca per parole, e una domanda intera («cosa abbiamo
promesso sulle consegne?») per FTS5 è quasi sempre nessun risultato: il modello
riceverebbe niente e risponderebbe lo stesso, che è il modo peggiore di
fallire. Meglio dire che l'indice manca.

**Non si fida dei numeri che il modello scrive.** Le call che riporta si
incrociano con quelle che gli sono state date, e il testo dei passaggi si
rilegge dall'archivio invece di prenderlo dalla risposta — la stessa regola che
vale per l'estrazione delle task (vedi `prompts.py`), e per lo stesso motivo:
un modello parafrasa le citazioni credendo di aiutare.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..db.store import Store
from ..llm.base import Completion, LLMProvider
from ..semantica.catene import Catena, catene
from ..semantica.indice import Indice, IndiceVuoto, Trovato
from . import lingue, prompts

# Quanti passaggi arrivano al modello. Quaranta passaggi da 700 caratteri fanno
# circa 28.000 caratteri, cioè intorno agli 8.000 token: ci stanno in tutti i
# modelli che l'applicazione sa usare, locale compreso, e restano lontani dal
# punto in cui un modello piccolo comincia a perdere di vista l'inizio.
PASSAGGI = 40

# Quanti passaggi al massimo per una singola call. Senza questo limite, una
# call in cui si è parlato a lungo dell'argomento riempie da sola i quaranta
# posti e le altre non arrivano nemmeno sotto gli occhi del modello — che è
# esattamente il difetto che la ricerca contestuale dovrebbe risolvere.
PER_CALL = 6


class IndiceMancante(RuntimeError):
    """La ricerca contestuale ha bisogno dell'indice semantico, e non c'è."""


@dataclass(frozen=True)
class CallCitata:
    """Una call che risponde, con il perché e i passaggi che lo reggono."""

    session_id: int
    titolo: str | None
    quando: int | None
    cliente: str | None
    perche: str
    passaggi: list[Trovato] = field(default_factory=list)


@dataclass(frozen=True)
class Risposta:
    domanda: str
    testo: str
    call: list[CallCitata]
    # Le catene consegnate al modello: servono a mostrare quali call sono state
    # lette insieme. Senza, unire resterebbe un gesto invisibile — e attribuire
    # in silenzio a una call qualcosa detto in un'altra è il difetto che #106
    # descrive, non il rimedio.
    catene: list[Catena]
    passaggi_letti: int
    modello: str = ""
    provider: str = ""
    tokens_in: int | None = None
    tokens_out: int | None = None
    costo_usd: float | None = None


class RicercaContestuale:
    def __init__(self, store: Store, indice: Indice, provider: LLMProvider) -> None:
        self.store = store
        self.indice = indice
        self.provider = provider

    def rispondi(
        self,
        domanda: str,
        *,
        session_ids: list[int] | None = None,
        unisci_catene: bool = True,
        lingua: str = "it",
    ) -> Risposta:
        trovati = self._materiale(domanda, session_ids)
        if not trovati:
            return Risposta(
                domanda=domanda, testo="", call=[], catene=[], passaggi_letti=0
            )

        anagrafica = self._anagrafica(sorted({t.session_id for t in trovati}))
        gruppi = (
            catene([(sid, r["client_id"], r["started_at"]) for sid, r in anagrafica.items()])
            if unisci_catene
            else [Catena(client_id=-1, session_ids=[sid]) for sid in anagrafica]
        )
        # Solo le catene che uniscono davvero qualcosa vanno mostrate: dire
        # «questa call è una catena di una call» non è un'informazione.
        unite = [c for c in gruppi if c.unita]

        testo, numerati = self._componi(trovati, anagrafica, gruppi, unisci_catene)
        completamento = self.provider.complete(
            system=prompts.SYSTEM_ARCHIVIO.format(lingua=lingue.nome(lingua)),
            user=prompts.ARCHIVIO_PROMPT.format(
                domanda=domanda.strip(),
                lingua=lingue.nome(lingua),
                catene_spiegazione=prompts.CATENE_SPIEGAZIONE if unite else "",
                passaggi=testo,
            ),
            schema=prompts.SCHEMA_ARCHIVIO,
            max_tokens=1200,
        )
        return self._risposta(domanda, completamento, numerati, anagrafica, unite, len(trovati))

    # ------------------------------------------------------------ materiale

    def _materiale(self, domanda: str, session_ids: list[int] | None) -> list[Trovato]:
        """I passaggi da leggere, con la rete larga e un tetto per call."""

        try:
            trovati = self.indice.cerca(
                domanda,
                session_ids=session_ids,
                limite=PASSAGGI * 3,
                # Niente soglia: qui a scartare è il modello, che legge.
                margine=None,
            )
        except IndiceVuoto as exc:
            raise IndiceMancante(str(exc)) from exc

        quanti: dict[int, int] = {}
        tenuti: list[Trovato] = []
        for t in trovati:
            n = quanti.get(t.session_id, 0)
            if n >= PER_CALL:
                continue
            quanti[t.session_id] = n + 1
            tenuti.append(t)
            if len(tenuti) >= PASSAGGI:
                break
        return tenuti

    def _anagrafica(self, session_ids: list[int]) -> dict[int, dict]:
        """Titolo, data e cliente delle call toccate, in una query sola."""
        if not session_ids:
            return {}
        segnaposto = ", ".join("?" * len(session_ids))
        righe = self.store.conn.execute(
            f"""
            SELECT s.id, s.titolo, s.started_at, s.client_id, c.nome AS cliente
              FROM sessions s
              LEFT JOIN clients c ON c.id = s.client_id
             WHERE s.id IN ({segnaposto})
            """,
            session_ids,
        )
        return {r["id"]: dict(r) for r in righe}

    # ---------------------------------------------------------- il prompt

    @staticmethod
    def _componi(
        trovati: list[Trovato],
        anagrafica: dict[int, dict],
        gruppi: list[Catena],
        unisci: bool,
    ) -> tuple[str, dict[int, Trovato]]:
        """Il materiale come lo legge il modello, e la mappa per rileggerlo.

        Gli id dei passaggi sono progressivi e locali a questa domanda, non
        quelli del database: il modello deve poterli citare senza che un numero
        inventato somigli per caso a una riga vera dell'archivio.
        """
        numerati = {i + 1: t for i, t in enumerate(trovati)}
        per_call: dict[int, list[tuple[int, Trovato]]] = {}
        for numero, t in numerati.items():
            per_call.setdefault(t.session_id, []).append((numero, t))

        pezzi: list[str] = []
        for i, catena in enumerate(gruppi, start=1):
            dentro = [sid for sid in catena.session_ids if sid in per_call]
            if not dentro:
                continue
            if unisci and len(dentro) > 1:
                pezzi.append(f"--- catena {i} ---")
            for sid in dentro:
                riga = anagrafica.get(sid, {})
                pezzi.append(f"\n{_intestazione(sid, riga)}")
                for numero, t in sorted(per_call[sid], key=lambda x: x[1].t_start_ms):
                    pezzi.append(f"[{numero}] ({_minuti(t.t_start_ms)}) {t.testo}")
        return "\n".join(pezzi).strip(), numerati

    # ----------------------------------------------------------- la risposta

    def _risposta(
        self,
        domanda: str,
        completamento: Completion,
        numerati: dict[int, Trovato],
        anagrafica: dict[int, dict],
        catene_unite: list[Catena],
        letti: int,
    ) -> Risposta:
        dati = completamento.data or {}
        call: list[CallCitata] = []
        for voce in dati.get("call", []):
            sid = voce.get("session_id")
            # Una call che non gli è stata data non esiste: il modello l'ha
            # inventata, o ha copiato un numero da un'altra riga. In tutti e due
            # i casi mostrarla vorrebbe dire mandare qualcuno ad aprire una
            # conversazione che non c'entra.
            if sid not in anagrafica:
                continue
            passaggi = [
                numerati[n]
                for n in voce.get("passaggi", [])
                if isinstance(n, int) and n in numerati and numerati[n].session_id == sid
            ]
            riga = anagrafica[sid]
            call.append(
                CallCitata(
                    session_id=sid,
                    titolo=riga.get("titolo"),
                    quando=riga.get("started_at"),
                    cliente=riga.get("cliente"),
                    perche=str(voce.get("perche") or "").strip(),
                    passaggi=passaggi,
                )
            )

        citate = {c.session_id for c in call}
        return Risposta(
            domanda=domanda,
            testo=str(dati.get("risposta") or "").strip(),
            call=call,
            # Solo le catene di cui almeno una call è finita nella risposta:
            # dire «ho unito queste» di call che poi non compaiono confonderebbe
            # il materiale letto con il materiale usato.
            catene=[c for c in catene_unite if citate & set(c.session_ids)],
            passaggi_letti=letti,
            modello=completamento.model,
            provider=completamento.provider,
            tokens_in=completamento.tokens_in,
            tokens_out=completamento.tokens_out,
            costo_usd=completamento.cost_usd,
        )


def _minuti(ms: int) -> str:
    return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}"


def _intestazione(session_id: int, riga: dict) -> str:

    titolo = riga.get("titolo") or "senza titolo"
    quando = riga.get("started_at")
    data = time.strftime("%d/%m/%Y", time.localtime(quando / 1000)) if quando else "data ignota"
    cliente = riga.get("cliente")
    coda = f", {cliente}" if cliente else ""
    return f"call {session_id} — «{titolo}», {data}{coda}"
