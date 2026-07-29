# Contratto fra core e interfaccia

> Il nuovo design chiede all'interfaccia cose che il core oggi non sa dire: lo stato di
> ogni call nell'elenco, a che punto è un'analisi, quali modelli sono installati, quanto
> spazio resta. Qui c'è l'elenco di ciò che il core deve esporre e con quale forma.
>
> **Le forme sono quelle di [`ui/renderer/tipi.ts`](../../../ui/renderer/tipi.ts)**: quel
> file è la definizione, questo documento dice solo dove va ogni cosa. Se una differenza
> emerge, vince `tipi.ts` e il core si adegua — l'interfaccia è già scritta contro quello.

Tutte le rotte richiedono il token, come le esistenti.

## Già esistenti, da estendere

| Rotta | Cosa cambia |
|---|---|
| `GET /sessions` | Ogni voce diventa un `Sessione`: `stato` non è più quello grezzo del database ma uno fra `recording`, `recorded`, `analyzing`, `analyzed`, `failed`, e si aggiungono `n_task` e `n_da_confermare`. Sono i tre dati che l'elenco a sinistra mostra su ogni riga. |
| `GET /sessions/{id}/analysis` | Restituisce un `Analisi` completo: oltre a `riassunto` e `punti_salienti` in Markdown, le versioni già divise in pezzi (`riassunto_gruppi`, `salienti`) e `meta` con motore, costo e durata. Il pannello mostra «API Anthropic · 0,04 € · 3m 12s»: quei tre valori vengono da qui. |
| `GET /analisi/stato` | Diventa uno `StatoAnalisi`: oltre a `in_corso`, quale sessione e le **quattro fasi** con il loro stato. Le fasi vanno aggiornate davvero mentre il lavoro procede: sono l'unica cosa che dice a chi guarda che non è tutto fermo. |
| `POST /settings` | Accetta le chiavi nuove elencate in `Impostazioni`: `stt.microfono_id`, `stt.loopback_id`, `stt.filtro_eco`, `note_incrementali`, `interfaccia.overlay_ridotto`, `export.cartella`, `export.formato`. |
| `GET /providers` | Ogni voce diventa un `Provider`: si aggiungono `esce_dal_computer`, `costo_ora_eur`, `minuti_per_ora` e `rimedio`. Oggi la conseguenza («la trascrizione viene inviata ad Anthropic») è scritta a mano nell'interfaccia: deve venire dal core, perché è la stessa informazione che serve anche all'export e ai log. |

## Nuove

| Rotta | Restituisce |
|---|---|
| `GET /sessions/{id}/screenshots` | `Scatto[]` — la trascrizione li mostra al loro minuto. |
| `POST /sessions/{id}/analyze/stop` | Interrompe l'analisi in corso. |
| `POST /sessions/{id}/elimina` | Cancella tutto di una call: audio, trascrizione, screenshot, task. |
| `GET /dispositivi` | `Dispositivi` — microfoni e sorgenti di loopback disponibili. |
| `GET /dati` | `VoceDati[]` — dove stanno audio, database e screenshot, e quanto occupano. |
| `POST /dati/elimina-audio` | Cancella i soli file audio, tenendo trascrizioni e task. |
| `GET /disco` | `Disco` — spazio sulla cartella dei modelli. |
| `GET /modelli` | `Modello[]` |
| `POST /modelli/{id}/scarica` | Avvia o riprende. Deve funzionare anche dopo un riavvio dell'applicazione. |
| `POST /modelli/{id}/sospendi` | Sospende, tenendo il parziale. |
| `POST /modelli/{id}/elimina` | |
| `POST /modelli/{id}/avvia` | Accende il modello di analisi (`llama-server`). |
| `POST /modelli/{id}/ferma` | |

## Eventi sul websocket

Si aggiungono a quelli esistenti; la forma è in `EventoCore`.

- `analisi` porta anche `fasi` quando cambiano, così il pannello non deve interrogare.
- `modello_locale` porta il `Modello` aggiornato a ogni passo del download: avanzamento,
  verifica, esito. Senza, l'interfaccia dovrebbe chiedere ogni secondo per un'ora.

## Due cose che non sono dettagli

**Il download si riprende.** Sono file da 5 a 17 GB su una connessione domestica. Va usato
`Range`, il parziale va tenuto su disco con un nome riconoscibile, e riaprendo
l'applicazione il modello deve risultare `in_pausa` con i byte già presi, non
`non_installato`. Chi ha scaricato 14 GB e chiude per sbaglio non deve ricominciare.

**Lo spazio si controlla prima.** Se non basta, lo stato è `spazio_insufficiente` e il
download non parte. Accorgersene a metà significa aver riempito il disco per niente.
