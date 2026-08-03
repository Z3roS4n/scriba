# PostgreSQL (database remoto)

> Tiene una copia delle call su un PostgreSQL dell'utente — Supabase o altro — nello schema che sceglie lui e con i dati che sceglie lui. **Gated**: senza URL e mappatura salvati, l'unica cosa che non funziona è la sincronizzazione; il resto di Scriba non se ne accorge (`stato()["collegato"] === false`).

## Scopo

Le call vivono in uno SQLite su un computer solo, e quel computer si rompe. Questo connettore non è un export — è una copia che si tiene aggiornata: si riesegue quante volte si vuole e il risultato è lo stesso, perché ogni riga si riconosce dalla sua chiave naturale invece che dall'ordine in cui è stata scritta.

Due strade, entrambe richieste:

1. **Farsi creare le tabelle** (`crea`) — si scelgono i dati, Scriba mostra il DDL, e dopo l'ok lo esegue. Nomi e tipi sono giusti per costruzione.
2. **Mappare su tabelle che esistono già** (`collega` con `tabelle`) — si legge `information_schema.columns` e si dice, campo per campo, in quale colonna va. Per ogni campo si propongono **solo** le colonne che possono davvero riceverlo: offrire un `text` per una scadenza vuol dire lasciar scegliere un errore che si vedrà al primo invio.

Sotto sono la stessa cosa: in entrambi i casi la configurazione finisce per dire, tabella per tabella, «questo campo va in questa colonna», e `invia()` non sa quale strada sia stata presa.

## Driver e versione

- `psycopg[binary]==3.2.10`. La variante `binary` porta con sé libpq: nessun compilatore, nessun PostgreSQL da installare sulla macchina di chi usa Scriba.
- Nel pacchetto serve `psycopg_binary` fra gli `hiddenimports` dello spec PyInstaller: psycopg sceglie la sua implementazione a runtime dentro un try/except, e l'analisi statica non segue un import condizionale. Senza quella riga il pacchetto contiene psycopg ma non libpq, e il collegamento fallisce **solo** sulla macchina di chi installa.

## Autenticazione

L'URL di connessione, che contiene la password. Niente OAuth, niente token: è un database.

## Variabili d'ambiente

Nessuna. L'URL vive in `database_remoto.json` accanto al database SQLite, **cifrato con DPAPI** — la chiave dell'account Windows. È l'unico segreto di Scriba che non sta in chiaro, e la ragione è che non è una chiave API di un servizio: è la password di un PostgreSQL che può essere di produzione, e chi legge quel file ci entra dentro.

Se DPAPI non risponde si ripiega sul chiaro con un'etichetta esplicita (`chiaro:`) e l'interfaccia lo dice: rifiutarsi di funzionare sarebbe peggio, nascondere in quale delle due forme è finito il segreto sarebbe peggio ancora.

Verso l'interfaccia non torna mai: `stato()` riporta host, database, utente e modalità, mai la password.

## Modalità di connessione

**Non è un dettaglio cosmetico: cambia cosa funziona.**

| | Diretta `:5432` | Pooler transazione `:6543` | Pooler sessione |
|---|---|---|---|
| DDL | sì | sì | sì |
| Prepared statement | sì | **no** | sì |
| Su Supabase | **spesso solo IPv6** | consigliata | ripiego IPv4 |

- **Pooler in transazione:** psycopg comincia a usare gli statement preparati da solo dopo qualche esecuzione, il pooler sposta la connessione fisica sotto ai piedi, ed esce `prepared statement "_pg3_0" already exists`. Si spengono (`prepare_threshold=None`) **automaticamente**, riconoscendo la porta 6543 o un host `pooler.`: chiedere all'utente di sapere questa cosa sarebbe chiedergli di conoscere un difetto di due librerie messe insieme.
- **Diretta su Supabase:** i progetti nuovi rispondono solo in IPv6. `spiega()` riconosce il caso e lo nomina, invece di lasciare uscire «timed out» — che manda a controllare rete, password e firewall, cioè ovunque tranne dove sta il problema.

`sslmode=require` si impone se manca e l'host non è locale. Se l'utente ne ha messo uno suo si rispetta il suo, anche se più debole: è una scelta esplicita.

## Rotte usate

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/database-remoto/stato` · `/modello` | collegamento, e cosa si può mandare |
| POST | `/database-remoto/prova` | si collega davvero: versione e schemi |
| POST | `/database-remoto/tabelle` · `/colonne` | ispezione, per la mappatura |
| POST | `/database-remoto/anteprima` | il DDL prima di eseguirlo. Nessuna rete |
| POST | `/database-remoto/crea` · `/collega` · `/scollega` | |
| POST | `/sessions/{id}/database-remoto` | invio di una call |
| POST | `/database-remoto/sincronizza-tutto` | il pregresso, senza fermarsi al primo intoppo |

## Cosa si scrive

Sei tabelle, spuntabili: `call`, `task`, `analisi`, `trascrizione` (predefinite), `partecipante` e `screenshot` (no). Degli screenshot vanno solo i metadati e il testo OCR — mandare le immagini vorrebbe dire caricarle da qualche parte, e non è quello che si è chiesto a un database.

Ogni tabella creata riceve un `sincronizzato_at`. Il DDL è sempre `CREATE ... IF NOT EXISTS`, **mai** un `DROP`, **mai** un `ALTER` su una tabella preesistente: su un database che è di qualcun altro si aggiunge, non si sistema d'ufficio.

## File nel codice

- `core/scriba_core/export/sql/__init__.py` — configurazione e API pubblica
- `core/scriba_core/export/sql/modello.py` — cosa Scriba sa mandare, e l'estrazione
- `core/scriba_core/export/sql/postgres.py` — il dialetto: URL, DDL, upsert, ispezione, messaggi
- `core/scriba_core/export/sql/segreti.py` — DPAPI
- `core/scriba_core/api/database_remoto.py` — le rotte
- `ui/renderer/impostazioni/DatabaseRemoto.tsx` — la schermata a passi

## Gestione errori

Tutto quello che può fallire diventa `ErroreSql` con un messaggio che si può mostrare così com'è, tradotto da `spiega()`. Le rotte lo girano in `400`. Un invio è **una transazione per call**: o la riunione e tutto quello che contiene sono arrivati, o non è arrivato niente — una call scritta a metà è peggio di una assente, perché sembra completa.

La sincronizzazione automatica a fine analisi non fa mai fallire un'analisi riuscita: i risultati sono già al sicuro in locale, e la call resta in `sync_remoto` con esito `errore`, cioè nell'elenco di quelle da rimandare.

## Aggiungere un altro motore

Il dialetto è una manciata di funzioni: `connetti`, `cita`, `tipo_sql`, `ddl_tabella`, `upsert`, `elenca_schemi`, `elenca_tabelle`, `colonne`, `accetta`, `spiega`. MySQL vuole un file con queste stesse funzioni (`PyMySQL`, `ON DUPLICATE KEY UPDATE` al posto di `ON CONFLICT`), non una riga in `__init__.py`.

## Costi

Nessuno da parte nostra. Dipende dal piano del database dell'utente.

## Stato della verifica

**Non provato contro un server vero.** La logica è coperta da 56 test; altri 13, già scritti, girano contro un PostgreSQL reale appena ne trovano uno — `SCRIBA_PG_URL` nell'ambiente, oppure Docker in esecuzione, nel qual caso si avviano un `postgres:17-alpine` usa-e-getta e lo buttano via. Finché quei 13 non sono stati eseguiti almeno una volta, questa integrazione va considerata non verificata, ed è così che il README la elenca.

```bash
cd core && ./.venv/Scripts/python.exe -m pytest tests/test_database_remoto_vero.py -q
```
