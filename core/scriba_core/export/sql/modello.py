"""Cosa Scriba sa mandare a un database remoto, e come si chiama.

Questo file è l'unica descrizione di *quali dati esistono*. Il dialetto sa
tradurre i tipi in colonne, il connettore sa collegarsi e scrivere: nessuno dei
due sa cosa sia una call. Aggiungere un campo si fa qui e basta.

**Le chiavi naturali.** Ogni tabella dice su cosa si riconosce una riga già
scritta. Non è un dettaglio da rimandare: senza, risincronizzare una call
duplicherebbe tutto quello che contiene, e duplicare le task di una riunione
dentro il sistema di lavoro di qualcuno è un danno vero, non un fastidio. Sono
uuid dove esiste un'identità (la call, la task) e coppie dove l'identità è la
posizione (un segmento è il segmento *n* di quella call).

**Perché non ci sono le immagini degli screenshot.** Solo il percorso locale e
il testo letto dall'OCR. Mandare i file vorrebbe dire caricarli da qualche
parte, e non è quello che si è chiesto a un database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...db.store import Store
from ...i18n import colonna_sql, tabella_sql

# I tipi che il modello conosce. Il dialetto li traduce nei tipi veri del
# motore: qui restano astratti perché lo stesso campo deve poter finire in un
# `timestamptz` di Postgres e in un `DATETIME` di MySQL senza riscrivere niente.
TIPI = ("testo", "testo_lungo", "intero", "decimale", "booleano", "istante", "data")


@dataclass(frozen=True)
class Campo:
    chiave: str
    etichetta: str
    tipo: str
    descrizione: str = ""
    #: Fa parte della chiave naturale della tabella.
    chiave_naturale: bool = False


@dataclass(frozen=True)
class Tabella:
    chiave: str
    etichetta: str
    descrizione: str
    campi: tuple[Campo, ...]
    #: Spuntata di default nella scelta iniziale.
    predefinita: bool = True
    #: Può essere molto grande: si dice all'utente prima che la scelga.
    voluminosa: bool = False

    @property
    def chiave_naturale(self) -> tuple[str, ...]:
        return tuple(c.chiave for c in self.campi if c.chiave_naturale)

    def campo(self, chiave: str) -> Campo | None:
        return next((c for c in self.campi if c.chiave == chiave), None)


CALL = Tabella(
    chiave="call",
    etichetta="Call",
    descrizione="Una riga per riunione: quando, quanto è durata, di chi era.",
    campi=(
        Campo("uuid", "Identificativo", "testo", "Stabile: non cambia mai", chiave_naturale=True),
        Campo("titolo", "Titolo", "testo"),
        Campo("cliente", "Cliente", "testo", "Vuoto se la call non è attribuita"),
        Campo("piattaforma", "Piattaforma", "testo", "Zoom, Teams, browser…"),
        Campo("inizio", "Inizio", "istante"),
        Campo("fine", "Fine", "istante"),
        Campo("durata_ms", "Durata (ms)", "intero"),
        Campo("stato", "Stato", "testo"),
        Campo("lingua", "Lingua", "testo"),
        Campo("note", "Note", "testo_lungo", "Quelle scritte a mano nella scheda"),
    ),
)

TASK = Tabella(
    chiave="task",
    etichetta="Task",
    descrizione="Gli impegni estratti dalla riunione, con la citazione da cui vengono.",
    campi=(
        Campo("uuid", "Identificativo", "testo", chiave_naturale=True),
        Campo("call_uuid", "Call", "testo", "A quale riunione appartiene"),
        Campo("titolo", "Titolo", "testo"),
        Campo("descrizione", "Descrizione", "testo_lungo"),
        Campo("assegnatario", "Assegnatario", "testo"),
        Campo("scadenza", "Scadenza", "data", "Risolta in una data vera"),
        Campo("scadenza_detta", "Scadenza a voce", "testo", "«entro fine mese»: l'ambiguità com'era"),
        Campo("priorita", "Priorità", "testo"),
        Campo("stato", "Stato", "testo"),
        Campo("confidenza", "Confidenza", "decimale", "Quanto ci crede il modello, da 0 a 1"),
        Campo("citazione", "Citazione", "testo_lungo", "La frase da cui viene la task"),
        Campo("citazione_ms", "Minuto della citazione", "intero"),
    ),
)

ANALISI = Tabella(
    chiave="analisi",
    etichetta="Riassunto e punti salienti",
    descrizione="Quello che il modello ha prodotto, e con quale modello.",
    campi=(
        Campo("call_uuid", "Call", "testo", chiave_naturale=True),
        Campo("tipo", "Tipo", "testo", "riassunto, punti salienti…", chiave_naturale=True),
        Campo("contenuto", "Contenuto", "testo_lungo"),
        Campo("modello", "Modello", "testo"),
        Campo("provider", "Motore", "testo", "local, anthropic, openai…"),
        Campo("prodotta_at", "Prodotta il", "istante"),
    ),
)

TRASCRIZIONE = Tabella(
    chiave="trascrizione",
    etichetta="Trascrizione",
    descrizione="Ogni frase detta, con il minuto e da quale traccia arriva.",
    voluminosa=True,
    campi=(
        Campo("call_uuid", "Call", "testo", chiave_naturale=True),
        Campo("indice", "Posizione", "intero", "Il numero d'ordine dentro la call", chiave_naturale=True),
        Campo("t_start_ms", "Da (ms)", "intero"),
        Campo("t_end_ms", "A (ms)", "intero"),
        Campo("sorgente", "Traccia", "testo", "mic = io, loopback = gli altri"),
        Campo("parlante", "Parlante", "testo", "Solo se la call è stata diarizzata"),
        Campo("testo", "Testo", "testo_lungo"),
    ),
)

PARTECIPANTE = Tabella(
    chiave="partecipante",
    etichetta="Partecipanti",
    descrizione="Le voci riconosciute nella call, con il nome se è stato dato.",
    predefinita=False,
    campi=(
        Campo("call_uuid", "Call", "testo", chiave_naturale=True),
        Campo("etichetta", "Etichetta", "testo", "«io», «Voce 2»…", chiave_naturale=True),
        Campo("ruolo", "Ruolo", "testo", "me | them"),
        Campo("nome", "Nome", "testo"),
    ),
)

SCREENSHOT = Tabella(
    chiave="screenshot",
    etichetta="Screenshot",
    descrizione=(
        "Solo i dati, non le immagini: percorso sul computer e testo letto dall'OCR. "
        "Il percorso da remoto non apre niente."
    ),
    predefinita=False,
    campi=(
        Campo("call_uuid", "Call", "testo", chiave_naturale=True),
        Campo("t_ms", "Minuto (ms)", "intero", chiave_naturale=True),
        Campo("percorso", "Percorso locale", "testo"),
        Campo("ocr", "Testo letto", "testo_lungo"),
        Campo("nota", "Nota", "testo_lungo"),
    ),
)

TABELLE: tuple[Tabella, ...] = (CALL, TASK, ANALISI, TRASCRIZIONE, PARTECIPANTE, SCREENSHOT)


def tabella(chiave: str) -> Tabella | None:
    return next((t for t in TABELLE if t.chiave == chiave), None)


def descrivi(lingua: str = "it") -> list[dict[str, Any]]:
    """Il modello in forma serializzabile, per l'interfaccia."""
    return [
        {
            "chiave": t.chiave,
            "etichetta": tabella_sql(t.chiave, t.etichetta, t.descrizione, lingua)[0],
            "descrizione": tabella_sql(t.chiave, t.etichetta, t.descrizione, lingua)[1],
            "predefinita": t.predefinita,
            "voluminosa": t.voluminosa,
            "chiave_naturale": list(t.chiave_naturale),
            "campi": [
                {
                    "chiave": c.chiave,
                    "etichetta": colonna_sql(t.chiave, c.chiave, c.etichetta, c.descrizione, lingua)[0],
                    "tipo": c.tipo,
                    "descrizione": colonna_sql(t.chiave, c.chiave, c.etichetta, c.descrizione, lingua)[1],
                    "chiave_naturale": c.chiave_naturale,
                }
                for c in t.campi
            ],
        }
        for t in TABELLE
    ]


# ---------------------------------------------------------------- estrazione


def _istante(ms: int | None) -> int | None:
    """Gli istanti restano epoch in millisecondi fino al dialetto.

    Convertirli in `datetime` qui significherebbe decidere un fuso, e il
    momento giusto per farlo è quando si sa in che colonna vanno a finire.
    """
    return ms


def righe(store: Store, session_id: int, chiave: str) -> list[dict[str, Any]]:
    """Le righe di una tabella per una call, già nella forma del modello.

    Solleva `ValueError` se la sessione non esiste, come fanno gli altri export.
    """
    sessione = store.conn.execute(
        """
        SELECT s.*, c.nome AS cliente
          FROM sessions s
          LEFT JOIN clients c ON c.id = s.client_id
         WHERE s.id = ?
        """,
        (session_id,),
    ).fetchone()
    if sessione is None:
        raise ValueError(f"Sessione {session_id} inesistente.")
    call_uuid = sessione["uuid"]

    if chiave == "call":
        return [
            {
                "uuid": call_uuid,
                "titolo": sessione["titolo"],
                "cliente": sessione["cliente"],
                "piattaforma": sessione["piattaforma"],
                "inizio": _istante(sessione["started_at"]),
                "fine": _istante(sessione["ended_at"]),
                "durata_ms": sessione["durata_ms"],
                "stato": sessione["stato"],
                "lingua": sessione["lingua"],
                "note": sessione["note_utente"],
            }
        ]

    if chiave == "task":
        fuori = []
        for t in store.conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? AND stato <> 'rejected' ORDER BY id",
            (session_id,),
        ):
            # La citazione che sostiene l'esistenza della task: è quella che si
            # mostra nell'interfaccia, quindi è quella che ha senso mandare.
            prova = store.conn.execute(
                """
                SELECT quote, t_ms FROM task_evidence
                 WHERE task_id = ?
                 ORDER BY CASE supports WHEN 'esistenza' THEN 0 ELSE 1 END, t_ms
                 LIMIT 1
                """,
                (t["id"],),
            ).fetchone()
            fuori.append(
                {
                    "uuid": t["uuid"],
                    "call_uuid": call_uuid,
                    "titolo": t["titolo"],
                    "descrizione": t["descrizione"],
                    "assegnatario": t["assignee_text"],
                    "scadenza": t["due_date"],
                    "scadenza_detta": t["due_raw"],
                    "priorita": t["priorita"],
                    "stato": t["stato"],
                    "confidenza": t["confidence"],
                    "citazione": prova["quote"] if prova else None,
                    "citazione_ms": prova["t_ms"] if prova else None,
                }
            )
        return fuori

    if chiave == "analisi":
        return [
            {
                "call_uuid": call_uuid,
                "tipo": r["kind"],
                "contenuto": r["content_md"],
                "modello": r["model"],
                "provider": r["provider"],
                "prodotta_at": _istante(r["created_at"]),
            }
            for r in store.conn.execute(
                """
                SELECT kind, content_md, model, provider, created_at
                  FROM ai_outputs
                 WHERE session_id = ? AND is_current = 1 AND scope_start_ms IS NULL
                 ORDER BY kind
                """,
                (session_id,),
            )
        ]

    if chiave == "trascrizione":
        return [
            {
                "call_uuid": call_uuid,
                # La posizione, non `transcript_segments.id`: quello è un
                # contatore del database locale, e ricostruirlo (è successo)
                # cambierebbe la chiave di ogni riga già sincronizzata.
                "indice": i,
                "t_start_ms": s.t_start_ms,
                "t_end_ms": s.t_end_ms,
                "sorgente": s.source,
                "parlante": s.speaker_nome_reale or s.speaker_label,
                "testo": s.testo,
            }
            for i, s in enumerate(store.segments(session_id, only_final=True))
        ]

    if chiave == "partecipante":
        return [
            {
                "call_uuid": call_uuid,
                "etichetta": r["label"],
                "ruolo": r["ruolo"],
                "nome": r["nome_reale"],
            }
            for r in store.speakers(session_id)
        ]

    if chiave == "screenshot":
        return [
            {
                "call_uuid": call_uuid,
                "t_ms": r["t_ms"],
                "percorso": r["path"],
                "ocr": r["ocr_text"],
                "nota": r["nota_utente"],
            }
            for r in store.screenshots(session_id)
        ]

    raise ValueError(f"Tabella sconosciuta: {chiave}")
