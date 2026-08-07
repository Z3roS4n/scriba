"""I prompt, versionati.

Ogni prompt ha un identificativo e una versione che finiscono accanto all'output
nel database: quando se ne cambia uno si può confrontare il prima e il dopo sulla
stessa call, invece di andare a impressione.

Regola che attraversa tutti i prompt di estrazione: **il modello non scrive mai
le citazioni**. Indica quale segmento, e il testo lo rilegge il codice dal
database. Un modello da 12 miliardi di parametri tende a parafrasare le frasi
invece di copiarle e a inventare i timestamp; togliergli quel compito elimina
l'intera categoria di errore invece di sperare che non capiti.

I due prompt di sistema sono **modelli da riempire**, non costanti: la lingua
dentro cambia con quella della call. Prima erano fissi all'italiano, e una
riunione in inglese usciva riassunta in italiano da un modello a cui era stato
detto che la trascrizione era italiana — cioè una cosa falsa su ciò che aveva
sotto gli occhi (#61). Vedi `ai/lingue.py` per il perché le istruzioni restino
in italiano mentre l'uscita no.
"""

from __future__ import annotations

SYSTEM_ESTRAZIONE = """Sei un analista che ricava impegni operativi da trascrizioni di riunioni di lavoro in {lingua}.
Lavori solo su ciò che è scritto nella trascrizione. Non aggiungi conoscenza tua, non deduci ciò che non è stato detto.
I campi di testo che compili vanno scritti in {lingua}, la lingua della riunione.
Rispondi esclusivamente con JSON conforme allo schema richiesto."""

SYSTEM_REDAZIONE = """Scrivi in {lingua}, per una persona che alla riunione non c'era.
La riunione si è svolta in {lingua} e in {lingua} va scritto tutto quello che produci, anche se questa istruzione è in un'altra lingua.
Tono asciutto e professionale. Nessuna formula di apertura o chiusura, nessun commento tuo.
Ogni affermazione deve derivare dalla trascrizione."""


EXTRACT_CANDIDATES = ("extract_candidates", "v3")
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
- Per ogni campo che valorizzi, metti nel corrispondente elenco "righe_..." gli ID delle righe che
  lo giustificano. NON riportare il testo: quello viene riletto dalla trascrizione.
  Esempio: se scrivi assignee "Marco" perché la riga [140] dice "se ne occupa Marco", allora
  "righe_assignee" deve contenere 140.
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
            # Il limite non è un dettaglio di comodo. Con la generazione
            # vincolata da grammatica un array senza tetto permette al modello di
            # continuare ad aggiungere elementi senza mai chiudere la parentesi:
            # visto succedere, la risposta veniva troncata anche con 6000 token
            # di spazio. Una finestra da 5k token di riunione non contiene più di
            # una decina di impegni veri.
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                # Un elenco di righe per ciascun campo, invece di un unico
                # elenco in cui il modello deve etichettare ogni voce. Provato:
                # dovendo scegliere un'etichetta da un enum, un 12B mette tutto
                # sotto "descrizione". Il nome del campo, invece, gli dice da
                # solo cosa ci va dentro.
                # Tutti obbligatori, anche quelli che possono valere null.
                # Lasciati opzionali il modello li ometteva e basta: nella prova
                # su una riunione vera "assignee" e "righe_assignee" non
                # comparivano nella risposta, pur essendoci nella trascrizione la
                # riga che diceva chi se ne occupava. Obbligandolo a scrivere
                # almeno `null` lo si costringe a porsi la domanda.
                "required": [
                    "temp_id",
                    "titolo",
                    "descrizione",
                    "assignee",
                    "due_raw",
                    "priorita",
                    "confidence",
                    "righe_titolo",
                    "righe_assignee",
                    "righe_scadenza",
                    "righe_priorita",
                ],
                "properties": {
                    # Anche le stringhe hanno un tetto: senza, il modello
                    # riscrive mezza riunione dentro la descrizione.
                    "temp_id": {"type": "string", "maxLength": 24},
                    "titolo": {"type": "string", "maxLength": 120},
                    "descrizione": {"type": ["string", "null"], "maxLength": 300},
                    "assignee": {"type": ["string", "null"], "maxLength": 60},
                    "due_raw": {"type": ["string", "null"], "maxLength": 60},
                    "priorita": {"type": ["string", "null"], "enum": ["bassa", "media", "alta", "critica", None]},
                    "confidence": {"type": "number"},
                    "righe_titolo": {"type": "array", "maxItems": 6, "items": {"type": "integer"}},
                    "righe_assignee": {"type": "array", "maxItems": 4, "items": {"type": "integer"}},
                    "righe_scadenza": {"type": "array", "maxItems": 4, "items": {"type": "integer"}},
                    "righe_priorita": {"type": "array", "maxItems": 4, "items": {"type": "integer"}},
                },
            },
        }
    },
}


MERGE_TASKS = ("merge_tasks", "v3")
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
            "maxItems": 15,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["titolo", "confidence", "needs_review", "evidence"],
                "properties": {
                    "titolo": {"type": "string", "maxLength": 120},
                    "descrizione": {"type": ["string", "null"], "maxLength": 400},
                    "assignee": {"type": ["string", "null"], "maxLength": 60},
                    "due_date": {"type": ["string", "null"], "maxLength": 12},
                    "due_raw": {"type": ["string", "null"], "maxLength": 60},
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


SUMMARY = ("summary", "v2")
# I titoli arrivano da `lingue.py` invece di stare scritti qui: sono le uniche
# parole di questo prompt che finiscono davvero sotto gli occhi dell'utente, e
# una call in inglese non deve produrre un riassunto con le sezioni in italiano.
SUMMARY_PROMPT = """Scrivi il riassunto di questa riunione.

Struttura in Markdown, con queste intestazioni esatte:

## {t_breve}
Da tre a cinque punti con l'esito della riunione. Se è stata presa una decisione, va qui.

## {t_contesto}
Un paragrafo: di cosa si è parlato e perché.

## {t_decisioni}
Elenco. Per ognuna indica chi ha deciso e il minuto fra parentesi quadre.

## {t_aperti}
Questioni non risolte, con chi deve scioglierle.

## {t_passi}
Solo ciò che è stato esplicitamente concordato.

Vincoli:
- Massimo 450 parole. Se la riunione è breve, scrivi meno.
- Cita i minuti [mm:ss] per decisioni e punti controversi.
- Se un passaggio rilevante è incomprensibile, scrivi "[audio non chiaro a mm:ss]" invece di indovinare.
- Se una sezione non ha contenuto, ometti l'intestazione.

Trascrizione:
{trascrizione}"""


HIGHLIGHTS = ("highlights", "v2")
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


RUNNING_NOTE = ("running_note", "v2")
RUNNING_NOTE_PROMPT = """La riunione è ancora in corso. Aggiorna la nota di lavoro.

Nota precedente:
{nota_precedente}

Nuova parte della trascrizione:
{finestra}

Produci una nota aggiornata di massimo 200 parole che tenga insieme quanto già annotato e
quanto è emerso adesso. Punti sintetici, non prosa. Se qualcosa di annotato prima è stato
smentito, correggilo."""
