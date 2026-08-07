# Integrazioni esterne — Scriba

> **Norma di progetto (obbligatoria):** ogni API di terze parti, ogni webhook (in entrata o in uscita) e ogni servizio esterno integrato **deve** essere documentato qui, in `.claude/integrations/`, **contestualmente** all'integrazione (stesso incremento). Un'integrazione non documentata è incompleta.
>
> Ogni scheda contiene: scopo · base URL/SDK e versione · autenticazione · variabili d'ambiente · endpoint/metodi con shape request/response · webhook (endpoint nostro, verifica firma, eventi, mapping) · file nel codice · gestione errori e gating · costi · note/TODO.

## Registro integrazioni

| Integrazione | Tipo | Stato | Scheda |
|---|---|---|---|
| Notion | API REST (uscita) | ✅ integrata, non ancora provata su un account vero | [notion.md](notion.md) |
| PostgreSQL remoto | driver `psycopg` (uscita) | ✅ integrato, non ancora provato su un server vero | [postgres.md](postgres.md) |
| SignPath Foundation | firma del codice in CI | ⏳ da chiedere: il codice è pronto, la domanda no | [signpath.md](signpath.md) |

## Webhook in entrata (endpoint esposti dalla nostra app)

| Endpoint | Provider | Verifica | Scheda |
|---|---|---|---|
| `POST /api/webhooks/<x>` | <provider> | firma/secret | — |

## Gating / graceful degradation
Ogni integrazione è **opzionale a runtime**: senza le sue variabili d'ambiente l'app resta pienamente funzionante e la funzione appare disabilitata. Verifica con `isXxxConfigured()` per ciascuna.

Nuova scheda: `/integration <nome servizio>` oppure `node .claude/scripts/new-integration.mjs "Nome"`.
