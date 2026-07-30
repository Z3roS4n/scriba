# Notion

> Manda una call su Notion: una pagina per la riunione, una riga per ogni task confermata, nelle colonne che l'utente ha scelto. **Gated**: senza token e database salvati, l'export Notion è l'unica cosa che non funziona — il resto di Scriba non se ne accorge (`stato()["collegato"] === false`, e l'interfaccia mostra il collegamento da fare).

## Scopo

Le task che Scriba estrae dalla riunione servono nel sistema di lavoro di chi le ha ricevute, non dentro Scriba. Il connettore le porta là dove vengono già gestite, portandosi dietro la prova (il minuto e la frase da cui la task viene): senza quella, una riga arrivata da un modello non è verificabile.

Due modi, entrambi richiesti:

1. **Adattare un database che esiste già** — si sceglie fra quelli condivisi con l'integrazione, e si dice per ogni campo di Scriba in quale colonna va. La corrispondenza per nome resta come *proposta* già compilata (`proponi_mappa`), non come decisione.
2. **Farsi creare un database** — si scelgono i campi che interessano e Scriba crea le colonne col tipo giusto (`crea_database`). La mappa non si indovina: le colonne le abbiamo fatte noi.

## Base URL / SDK e versione

- REST `https://api.notion.com/v1`, header `Notion-Version: 2022-06-28`, client `httpx`.
- Nessun SDK: le chiamate usate sono sei, e un SDK in più da aggiornare non le renderebbe più chiare.

## Autenticazione

`Authorization: Bearer <token dell'integrazione interna>`. Il token si crea su notion.so/my-integrations, e **va condiviso** con la pagina o il database di destinazione dal menù «…»: senza quel passaggio Notion risponde 404 su risorse che esistono.

## Variabili d'ambiente

Nessuna. Il token è dell'utente, non del progetto: vive in `export_notion.json` accanto al database SQLite, **non** in `settings.json` (quel file ha un formato di credenziali suo, `llm.api_key`) e non nell'ambiente. Verso l'interfaccia non torna mai indietro: `stato()` dice *se* c'è, mai quale sia.

## Endpoint / metodi usati

| Metodo | Path | Request | Response |
|---|---|---|---|
| POST | `/search` | `{filter: {property: "object", value: "database"\|"page"}, page_size, start_cursor?}` | `{results: [...], has_more, next_cursor}` |
| GET | `/databases/{id}` | — | `{title, properties: {nome: {type, select?: {options}, status?: {options}}}}` |
| POST | `/databases` | `{parent: {type: "page_id", page_id}, title, properties}` | `{id}` |
| POST | `/pages` | `{parent: {database_id}, properties, children}` | `{id}` |
| PATCH | `/pages/{id}` | `{properties}` | `{id}` |
| GET/PATCH/DELETE | `/blocks/{id}/children`, `/blocks/{id}` | `{children}` | `{results, has_more}` |

Vincoli dell'API che il codice rispetta:

- 100 blocchi per chiamata (si usano 90 per margine), 2000 caratteri per `rich_text`.
- Le opzioni di un `select`/`multi_select` **si creano** mandando un nome nuovo; quelle di uno `status` **no**. Per questo `_valore_proprieta` cerca fra le opzioni esistenti (`Fatto`/`Done`/`Completato`…) e, se nessuna corrisponde, per lo `status` non manda niente invece di far rifiutare la riga.
- Un database si crea solo dentro una **pagina**, non nello spazio di lavoro: da qui l'elenco di pagine in `elenca_destinazioni`, che scarta le righe dei database (per l'API sono pagine anche loro).

## Rotte nostre (l'interfaccia parla solo con queste)

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/export/notion/stato` | collegato sì/no, database, mappatura |
| GET | `/export/notion/campi` | i campi mappabili: **è qui la definizione**, la UI non la ridefinisce |
| POST | `/export/notion/destinazioni` | database e pagine visibili all'integrazione |
| POST | `/export/notion/schema` | proprietà del database + mappa proposta |
| POST | `/export/notion/collega` | salva token/database/mappatura (mappatura verificata prima di salvare) |
| POST | `/export/notion/database` | crea il database e lo collega |
| POST | `/export/notion/scollega` | dimentica tutto |
| POST | `/sessions/{id}/export/notion` | manda la call |

## File nel codice

- `core/scriba_core/export/notion.py` — tutto il connettore: catalogo dei campi (`CAMPI`), configurazione, mappatura, creazione, invio.
- `core/scriba_core/api/export.py` — le rotte, sottili.
- `ui/renderer/impostazioni/Notion.tsx` — collegamento a passi: token → database (o creazione) → mappatura.
- `ui/renderer/tipi.ts` — le forme condivise (`CampoNotion`, `StatoNotion`, `SchemaNotion`, …).
- `core/tests/test_export_formati.py` — `FakeNotion`: Notion in memoria con lo stesso contratto REST.
- `ui/scripts/anteprima/ponte-finto.js` — Notion finto per guardare la schermata senza Electron né core.

## Gestione errori e gating

- `NotionError` → 400 con un messaggio che dice cosa fare. 401 diventa «Notion ha rifiutato il token», 403/404 diventa «non lo trova, oppure l'integrazione non è stata condivisa con quella pagina»: sono i due errori che capitano davvero, e sono indistinguibili se non si nominano.
- Una mappatura sbagliata (colonna assente, tipo incompatibile, due campi sulla stessa colonna) viene rifiutata **prima** di salvare: non resta mezzo stato.
- Una riga-task che fallisce non blocca le altre: si scrive `export_status = 'error'` con il motivo e si prosegue.
- Idempotenza: la pagina della call è in `export_notion.json`, la riga di ogni task in `tasks.export_ref`. Cambiare database azzera entrambi (`_azzera_riferimenti`), altrimenti si aggiornerebbero righe nel database vecchio riportando «aggiornati» a database nuovo vuoto.

## Costi

Nessuno: l'API di Notion è gratuita. Il limite è ~3 richieste al secondo per integrazione; un invio fa una chiamata per la pagina della call più una per task (più quelle dei blocchi), quindi una call normale ci sta dentro senza throttling. Se un giorno servisse mandare decine di call in fila, va aggiunto un backoff sul 429.

## Note / TODO

- **Non verificato contro un account Notion vero** — nessuna credenziale disponibile: i test coprono la logica con le chiamate HTTP simulate. Il primo collegamento reale va guardato con attenzione, in particolare i nomi delle opzioni di `status` e la creazione del database.
- La pagina della call è una riga nello stesso database delle task. Se si volesse separarla (pagina figlia della pagina genitore, task nel database) cambierebbe la forma dello stato salvato: da valutare solo se qualcuno lo chiede.
- `people` non è fra i tipi accettati per l'assegnatario: richiederebbe di risolvere il nome detto a voce in un utente Notion, che è un'inferenza in più su un dato che serve certo.
- La ricerca si fermava a 5 pagine da 100 risultati (`_PAGINE_DI_RICERCA`): chi ha più di 500 database non li trova scorrendo un elenco. Se capita, serve un campo di ricerca che passi `query` a `/search`.
