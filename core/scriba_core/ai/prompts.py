"""I prompt, versionati.

Ogni prompt ha un identificativo e una versione che finiscono accanto all'output
nel database: quando se ne cambia uno si può confrontare il prima e il dopo sulla
stessa call, invece di andare a impressione.

Regola che attraversa tutti i prompt di estrazione: **il modello non scrive mai
le citazioni**. Indica quale segmento, e il testo lo rilegge il codice dal
database. Un modello da 12 miliardi di parametri tende a parafrasare le frasi
invece di copiarle e a inventare i timestamp; togliergli quel compito elimina
l'intera categoria di errore invece di sperare che non capiti.
"""

from __future__ import annotations

SYSTEM_ESTRAZIONE = """Sei un analista che ricava impegni operativi da trascrizioni di riunioni di lavoro in italiano.
Lavori solo su ciò che è scritto nella trascrizione. Non aggiungi conoscenza tua, non deduci ciò che non è stato detto.
Rispondi esclusivamente con JSON conforme allo schema richiesto."""

SYSTEM_REDAZIONE = """Scrivi in italiano, per una persona che alla riunione non c'era.
Tono asciutto e professionale. Nessuna formula di apertura o chiusura, nessun commento tuo.
Ogni affermazione deve derivare dalla trascrizione."""


EXTRACT_CANDIDATES = ("extract_candidates", "v1")
EXTRACT_CANDIDATES_PROMPT = """Questa è una finestra della riunione. Ogni riga ha la forma:

[id] (mm:ss) CHI: testo

dove CHI è "io" (l'utente) oppure "altri" (gli interlocutori).

Individua OGNI cosa che assomigli a un impegno, un'azione da fare o una richiesta, anche se incompleta.
Meglio un candidato in più che uno perso: un passaggio successivo unirà i duplicati.

Regole:
- Un candidato è un'azione concreta. Non estrarre opinioni, contesto o informazioni senza azione.
- Se un dettaglio (scadenza, responsabile, priorità) non compare in questa finestra, lascia null
  e aggiungilo a "campi_mancanti". Non inventarlo e non dedurlo.
- Le date relative ("entro venerdì", "fine mese") vanno in "due_raw" così come sono state dette.
  Non convertirle in date.
- In "evidence" indica gli ID delle righe che giustificano ogni campo. NON riportare il testo:
  quello viene riletto dalla trascrizione.
- confidence: 0.9 o più se l'impegno è esplicito e accettato; fra 0.6 e 0.9 se probabile;
  sotto 0.6 se è un'ipotesi o una discussione non conclusa.
- Se un'azione viene proposta e poi esplicitamente scartata, non estrarla.

Trascrizione:
{finestra}"""

SCHEMA_CANDIDATES = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidati"],
    "properties": {
        "candidati": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["temp_id", "titolo", "confidence", "evidence"],
                "properties": {
                    "temp_id": {"type": "string"},
                    "titolo": {"type": "string"},
                    "descrizione": {"type": ["string", "null"]},
                    "assignee": {"type": ["string", "null"]},
                    "due_raw": {"type": ["string", "null"]},
                    "priorita": {"type": ["string", "null"], "enum": ["bassa", "media", "alta", "critica", None]},
                    "campi_mancanti": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["segment_id", "supports"],
                            "properties": {
                                "segment_id": {"type": "integer"},
                                "supports": {
                                    "type": "string",
                                    "enum": [
                                        "titolo",
                                        "descrizione",
                                        "assignee",
                                        "due_date",
                                        "priorita",
                                        "esistenza",
                                    ],
                                },
                            },
                        },
                    },
                },
            },
        }
    },
}


MERGE_TASKS = ("merge_tasks", "v2")
MERGE_TASKS_PROMPT = """Questi sono i candidati estratti da un'unica riunione, in ordine cronologico.

I dettagli di uno stesso impegno sono spesso SPARSI: il lavoro viene nominato a un certo punto,
la scadenza si concorda molto dopo, il responsabile si decide alla fine. Il tuo compito è
ricomporre impegni completi e coerenti.

Procedi così:
1. Raggruppa i candidati che riguardano lo stesso lavoro, anche se formulati con parole diverse.
   Due candidati sono lo stesso impegno se hanno lo stesso oggetto concreto.
2. Per ogni gruppo componi UN impegno. **Compila i campi**, non limitarti a raccogliere le prove:
   se in un candidato del gruppo compare un responsabile, quel nome va nel campo "assignee"
   dell'impegno unito. Se compare una scadenza, va in "due_raw". A parità di affidabilità vince
   quanto detto più tardi nella riunione.
3. UNISCI le evidence di tutti i candidati del gruppo. Per ognuna indica **quale campo giustifica**:
   "assignee" per la riga che dice chi se ne occupa, "due_date" per quella che fissa la scadenza,
   "titolo" per quella che nomina il lavoro. Non mettere tutto sotto "descrizione".
4. In "due_raw" riporta la scadenza **con le parole usate nella riunione**. Lascia "due_date" a null:
   la conversione in data la fa un altro passaggio.
5. Scarta i candidati che, guardando l'intera riunione, non sono impegni reali (ipotesi abbandonate,
   cose già fatte, esempi). Elencali in "scartati" con il motivo.
6. needs_review è true se: confidence sotto 0.8, oppure manca il responsabile o la scadenza,
   oppure hai dovuto dedurre un campo invece di leggerlo.

Esempio di come i pezzi vanno ricomposti. Da questi tre candidati:

  {{"temp_id": "f0_c1", "titolo": "Preparare i mockup", "assignee": null, "due_raw": null,
    "evidence": [{{"segment_id": 12, "supports": "titolo"}}]}}
  {{"temp_id": "f2_c3", "titolo": "Scadenza mockup", "due_raw": "entro il quattordici",
    "evidence": [{{"segment_id": 88, "supports": "due_date"}}]}}
  {{"temp_id": "f4_c1", "titolo": "Mockup a Marco", "assignee": "Marco",
    "evidence": [{{"segment_id": 140, "supports": "assignee"}}]}}

deve uscire UN impegno solo, con i campi pieni:

  {{"titolo": "Preparare i mockup", "assignee": "Marco", "due_raw": "entro il quattordici",
    "due_date": null, "confidence": 0.85, "needs_review": false,
    "merged_from": ["f0_c1", "f2_c3", "f4_c1"],
    "evidence": [{{"segment_id": 12, "supports": "titolo"}},
                 {{"segment_id": 88, "supports": "due_date"}},
                 {{"segment_id": 140, "supports": "assignee"}}]}}

Data della riunione: {data_riunione}, {giorno_settimana}.
Non inventare impegni che non compaiono fra i candidati.

Candidati:
{candidati}"""

SCHEMA_MERGE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tasks"],
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["titolo", "confidence", "needs_review", "evidence"],
                "properties": {
                    "titolo": {"type": "string"},
                    "descrizione": {"type": ["string", "null"]},
                    "assignee": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                    "due_raw": {"type": ["string", "null"]},
                    "priorita": {"type": ["string", "null"], "enum": ["bassa", "media", "alta", "critica", None]},
                    "confidence": {"type": "number"},
                    "needs_review": {"type": "boolean"},
                    "review_reason": {"type": ["string", "null"]},
                    "merged_from": {"type": "array", "items": {"type": "string"}},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["segment_id", "supports"],
                            "properties": {
                                "segment_id": {"type": "integer"},
                                "supports": {
                                    "type": "string",
                                    "enum": [
                                        "titolo",
                                        "descrizione",
                                        "assignee",
                                        "due_date",
                                        "priorita",
                                        "esistenza",
                                    ],
                                },
                            },
                        },
                    },
                },
            },
        },
        "scartati": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["temp_id", "motivo"],
                "properties": {"temp_id": {"type": "string"}, "motivo": {"type": "string"}},
            },
        },
    },
}


SUMMARY = ("summary", "v1")
SUMMARY_PROMPT = """Scrivi il riassunto di questa riunione.

Struttura in Markdown:

## In breve
Da tre a cinque punti con l'esito della riunione. Se è stata presa una decisione, va qui.

## Contesto
Un paragrafo: di cosa si è parlato e perché.

## Decisioni prese
Elenco. Per ognuna indica chi ha deciso e il minuto fra parentesi quadre.

## Punti aperti
Questioni non risolte, con chi deve scioglierle.

## Prossimi passi
Solo ciò che è stato esplicitamente concordato.

Vincoli:
- Massimo 450 parole. Se la riunione è breve, scrivi meno.
- Cita i minuti [mm:ss] per decisioni e punti controversi.
- Se un passaggio rilevante è incomprensibile, scrivi "[audio non chiaro a mm:ss]" invece di indovinare.
- Se una sezione non ha contenuto, ometti l'intestazione.

Trascrizione:
{trascrizione}"""


HIGHLIGHTS = ("highlights", "v1")
HIGHLIGHTS_PROMPT = """Estrai i momenti salienti: i passaggi che una persona vorrebbe riascoltare.

Per ciascuno produci una riga così:
[mm:ss] **Etichetta breve** — una frase che spiega perché conta.

Includi: decisioni, cambi di direzione, obiezioni o preoccupazioni, numeri e cifre citati,
impegni presi, informazioni nuove.
Escludi: convenevoli, ripetizioni, digressioni.

Da 5 a 12 punti, in ordine cronologico. Se la riunione ne contiene meno, produci meno.
Non parafrasare al punto da perdere il dettaglio concreto: se qualcuno dice "il budget è 40k",
il numero deve comparire.

Trascrizione:
{trascrizione}"""


RUNNING_NOTE = ("running_note", "v1")
RUNNING_NOTE_PROMPT = """La riunione è ancora in corso. Aggiorna la nota di lavoro.

Nota precedente:
{nota_precedente}

Nuova parte della trascrizione:
{finestra}

Produci una nota aggiornata di massimo 200 parole che tenga insieme quanto già annotato e
quanto è emerso adesso. Punti sintetici, non prosa. Se qualcosa di annotato prima è stato
smentito, correggilo."""
