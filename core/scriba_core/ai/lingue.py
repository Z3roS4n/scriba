"""In che lingua deve rispondere il modello.

`sessions.lingua` esiste dall'inizio — la sceglie chi registra, e la trascrizione
la rispetta già. All'analisi però non arrivava, e i due prompt di sistema
imponevano l'italiano: una call in inglese usciva riassunta in italiano, e al
modello veniva detto che la trascrizione era italiana mentre ne leggeva una
inglese (#61).

## Si traduce l'uscita, non le istruzioni

I prompt restano scritti in italiano. Non è pigrizia: un prompt è una specifica
per il modello, non un testo che qualcuno legge, e `prompts.py` versiona ogni
prompt apposta per poter confrontare il prima e il dopo sulla stessa call.
Tenerne sei traduzioni vorrebbe dire sei versioni da far avanzare insieme, e sei
occasioni perché una diverga dalle altre senza che nessuno se ne accorga.

Quello che cambia è **la lingua in cui il modello deve scrivere**, dichiarata
esplicitamente, più i titoli del riassunto — quelli sì che finiscono sotto gli
occhi di chi legge.

Istruzioni in una lingua e contenuto in un'altra funzionano con i modelli in uso
qui, ma è una cosa che si misura, non che si dà per scontata: se un modello
locale piccolo dovesse rispondere nella lingua del prompt invece che in quella
richiesta, si vedrebbe subito e la strada sarebbe tradurre `SYSTEM_REDAZIONE`,
che è corto, prima di tutto il resto.

## Perché i titoli sono scritti qui e non chiesti al modello

Si potrebbe dire «traduci tu queste intestazioni». Con un modello da 12 miliardi
di parametri che gira in locale, ogni cosa lasciata alla sua discrezione è una
cosa che cambia fra una call e l'altra. Scritte qui, sono uguali sempre.
"""

from __future__ import annotations

PREDEFINITA = "it"

# Il nome in italiano, perché è la lingua in cui è scritta l'istruzione che lo
# contiene ("Scrivi in inglese"). Non il nome nella lingua stessa: mescolare le
# due cose dentro la stessa frase confonde i modelli piccoli.
NOMI: dict[str, str] = {
    "it": "italiano",
    "en": "inglese",
    "fr": "francese",
    "de": "tedesco",
    "es": "spagnolo",
    "pt": "portoghese",
}

# Le sezioni del riassunto, nell'ordine in cui il prompt le chiede. Queste sono
# testo che l'utente legge, quindi vanno nella sua lingua per davvero.
TITOLI_RIASSUNTO: dict[str, tuple[str, ...]] = {
    "it": ("In breve", "Contesto", "Decisioni prese", "Punti aperti", "Prossimi passi"),
    "en": ("In short", "Context", "Decisions made", "Open questions", "Next steps"),
    "fr": ("En bref", "Contexte", "Décisions prises", "Questions ouvertes", "Prochaines étapes"),
    "de": ("Kurz gefasst", "Kontext", "Getroffene Entscheidungen", "Offene Punkte", "Nächste Schritte"),
    "es": ("En resumen", "Contexto", "Decisiones tomadas", "Puntos abiertos", "Próximos pasos"),
    "pt": ("Em resumo", "Contexto", "Decisões tomadas", "Pontos em aberto", "Próximos passos"),
}


def normalizza(codice: str | None) -> str:
    """Il codice a due lettere, o la lingua predefinita se non lo riconosciamo.

    Accetta anche le forme regionali (`en-GB`, `pt_BR`): la regione non cambia
    la lingua in cui si scrive un riassunto, e rifiutarle vorrebbe dire far
    uscire in italiano una call che aveva dichiarato la sua lingua.
    """
    if not codice:
        return PREDEFINITA
    base = codice.strip().lower().replace("_", "-").split("-")[0]
    return base if base in NOMI else PREDEFINITA


def nome(codice: str | None) -> str:
    """Come chiamare questa lingua parlando al modello."""
    return NOMI[normalizza(codice)]


def titoli_riassunto(codice: str | None) -> tuple[str, ...]:
    return TITOLI_RIASSUNTO[normalizza(codice)]


def sezioni_riassunto(codice: str | None) -> dict[str, str]:
    """I titoli pronti da infilare nel prompt del riassunto, uno per segnaposto."""
    breve, contesto, decisioni, aperti, passi = titoli_riassunto(codice)
    return {
        "t_breve": breve,
        "t_contesto": contesto,
        "t_decisioni": decisioni,
        "t_aperti": aperti,
        "t_passi": passi,
    }
