# Scriba — API del core

> Le rotte che il core espone all'interfaccia. Non è un'API pubblica: ascolta
> solo su 127.0.0.1, su porta effimera, e ogni richiesta porta un token.
> Ultimo aggiornamento: 2026-08-02.

## Principi

- **Rotte sottili.** La logica vive nei moduli (`export/`, `db/`, `ai/`); una
  rotta valida l'ingresso, chiama, e traduce l'errore. Se una rotta è lunga, la
  logica è nel posto sbagliato.
- **Niente lavoro sull'event loop.** Ogni chiamata sincrona che può durare —
  disco, rete, database remoto — passa da `asyncio.to_thread`. Durante una
  registrazione un server lento non deve fermare la trascrizione.
- **I segreti entrano, non escono.** Token e password si scrivono, non si
  rileggono: lo stato dice *se* un collegamento c'è, mai con quale credenziale.
  Vale per `llm.api_key`, per Notion e per il database remoto.
- **Un campo vuoto significa «non lo sto cambiando»**, non «cancellalo».
  L'interfaccia rimanda indietro l'oggetto intero anche quando tocca un campo
  solo, e non ha mai visto il segreto.
- **I moduli nuovi stanno in `api/`,** con un `Contesto` esplicito
  (`store`, `settings`, `db_path`, `publish`, `state`) invece della chiusura
  lessicale di `server.py`.

## Sicurezza del trasporto

Porta effimera decisa dal sistema all'avvio e token generato allora, comunicati
al processo padre su stdout come una riga JSON. Un server su porta fissa senza
token sarebbe raggiungibile da qualunque pagina web aperta nel browser.

## Rotte

### Sessione e registrazione
| Metodo | Path | Scopo |
|---|---|---|
| GET | `/health` | stato del modello, database messo da parte |
| GET | `/session/state` | registrazione in corso, istante corrente |
| POST | `/session/start` · `/stop` · `/pause` · `/resume` | ciclo della registrazione |
| POST | `/session/screenshot` | aggancia uno scatto all'istante della call |
| GET | `/sessions` | elenco, con cliente e conteggio task |
| GET | `/sessions/{id}/segments` | la trascrizione |
| POST | `/sessions/{id}/elimina` | |

### Analisi
| Metodo | Path | Scopo |
|---|---|---|
| POST | `/sessions/{id}/analyze` | risponde subito, lavora dopo |
| POST | `/sessions/{id}/analyze/stop` | |
| GET | `/sessions/{id}/analysis` | riassunto, salienti, task, prove |
| GET | `/analisi/stato` | fasi dell'analisi in corso |
| GET | `/sessions/{id}/note` | le note di lavoro scritte durante la call |
| POST | `/tasks/{id}` | correzione manuale di una task |

`/sessions/{id}/note` restituisce tutte le note **e** l'ultima a parte: ognuna
riscrive la precedente incorporandola, quindi è quella da mostrare. Non passa da
`/sessions/{id}/analysis` perché quella costruisce `{kind: testo}` e le note sono
`is_current` tutte insieme — hanno finestre diverse — quindi lì collasserebbero in
una sola, e quale dipenderebbe dall'ordine di scansione. `attive` dice se
l'impostazione è accesa: senza, l'interfaccia non sa distinguere «non ancora» da
«non le vuoi».

### Rifinitura della trascrizione
| Metodo | Path | Scopo |
|---|---|---|
| POST | `/sessions/{id}/rifinisci` | ripassa la call con Canary; risponde subito |
| GET | `/rifinitura/stato` | a che punto è, e se il modello c'è (`modello_pronto`) |
| POST | `/rifinitura/interrompi` | |

`POST /sessions/{id}/rifinisci` risponde `412` quando la call non ha trascrizione
o quando il modello non è ancora scaricato — e in quel caso il messaggio dice
**dove** scaricarlo. Una seconda richiesta sulla stessa call mentre sta già
girando risponde `200 già_avviata`, non `409`: sta succedendo quello che si sta
chiedendo, e un errore lì farebbe smettere l'interfaccia di aspettare.

L'esito distingue traccia per traccia: `rifinita`, `assente`, `vuota` e
`non_allineata` — l'ultimo quando l'audio salvato non corrisponde ai minuti della
trascrizione (vedi #45), nel qual caso **non si è riscritto niente** e `motivo`
spiega perché.

### Clienti e archivio
| Metodo | Path | Scopo |
|---|---|---|
| GET · POST | `/clienti` | elenco (con `n_call`), creazione |
| PATCH · POST | `/clienti/{id}` · `/clienti/{id}/elimina` | modifica, archiviazione, eliminazione |
| POST | `/clienti/importa` | CSV **come contenuto**, non come percorso |
| PATCH | `/sessions/{id}/cliente` | attribuzione; `null` la toglie |
| GET | `/archivio` | ricerca e filtri (`testo`, `client_id`, `senza_cliente`, `da_ms`, `a_ms`, `stato`) |

`POST .../elimina` e non `DELETE`: è la forma che il progetto usa già per
sessioni e modelli, ed è l'unica che il ponte del renderer sa mandare
(`preload.ts` espone get/post/patch).

### Export e database remoto
| Metodo | Path | Scopo |
|---|---|---|
| POST | `/sessions/{id}/export` | markdown · testo · json · contesto |
| POST | `/export/contesto/anteprima` | quanto peserebbe in token. Non scrive niente |
| POST | `/export/contesto` | il documento per un modello, anche di N call insieme |
| GET/POST | `/export/notion/*` | stato, destinazioni, schema, creazione, collegamento |
| POST | `/sessions/{id}/export/notion` · `/export/http` | invio |
| GET | `/database-remoto/stato` · `/modello` | collegamento, e cosa si può mandare |
| POST | `/database-remoto/prova` | si collega davvero e riferisce |
| POST | `/database-remoto/tabelle` · `/colonne` | ispezione, per la mappatura |
| POST | `/database-remoto/anteprima` | il DDL, **prima** di eseguirlo. Nessuna rete |
| POST | `/database-remoto/crea` · `/collega` · `/scollega` | |
| POST | `/sessions/{id}/database-remoto` · `/database-remoto/sincronizza-tutto` | invio |

### Impostazioni, modelli, sistema
| Metodo | Path | Scopo |
|---|---|---|
| GET · POST | `/settings` | |
| GET | `/providers` | i motori, con `disponibile` e `in_avvio` |
| GET | `/modelli` · `/disco` · `/dispositivi` · `/dati` | |
| POST | `/modelli/{id}/scarica` · `/sospendi` · `/avvia` · `/ferma` · `/elimina` | |
| GET | `/rilevamento/diagnostica` | cosa vede il rilevamento adesso |
| POST | `/rilevamento/ignora/{pid}` | dimentica *questa* proposta, non la funzione |
| GET | `/search` | full-text su tutte le call |
| WS | `/ws` | trascrizione, avanzamento, eventi |

`GET /health` è l'unica rotta **senza token** — serve al processo padre per
sapere quando il core è su — e riporta anche `versione` e `commit` della build
da cui viene. Non li legge da un file suo: glieli passa chi lo avvia
(`SCRIBA_VERSIONE` / `SCRIBA_COMMIT`, vedi `ui/main/sidecar.ts`), perché
interfaccia e core escono sempre dalla stessa compilazione. Un core avviato a
mano li lascia `null`, che è la verità: non appartiene a nessuna build.

## Convenzioni sugli errori

| Codice | Quando |
|---|---|
| 400 | ingresso che non può funzionare — detto **con il motivo**, non «richiesta non valida» |
| 404 | la cosa indicata non esiste |
| 409 | conflitto di stato (screenshot senza registrazione in corso) |
| 503 | il core non è ancora pronto — lo restituisce il ponte, non il core |

Un errore che l'utente può risolvere deve dire come: `postgres.spiega()` esiste
per questo — traduce «connection timed out» in «quell'indirizzo risponde solo in
IPv6, usa il pooler». Un messaggio generico manda a cercare nel posto sbagliato.

## Eventi WebSocket

`transcript` · `session_started` · `session_stopped` · `screenshot` · `analisi`
(`in_corso` | `fatto` | `errore`) · `rifinitura` (`in_corso` | `finita` |
`interrotta` | `errore`) · `modello_locale` · `call_rilevata` · `diarizzazione` ·
`database_remoto`.

`rifinitura`/`in_corso` non esce a ogni riga ma ogni dieci: su una call lunga
sarebbero centinaia di eventi che dicono la stessa cosa.

Gli eventi lunghi non si interrogano a ripetizione: un download di modello dura
fino a un'ora, e chiedere ogni secondo per un'ora sarebbe assurdo.
