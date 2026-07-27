# Integrazioni esterne — {{NAME}}

> **Norma di progetto (obbligatoria):** ogni API di terze parti, ogni webhook (in entrata o in uscita) e ogni servizio esterno integrato **deve** essere documentato qui, in `.claude/integrations/`, **contestualmente** all'integrazione (stesso incremento). Un'integrazione non documentata è incompleta.
>
> Ogni scheda contiene: scopo · base URL/SDK e versione · autenticazione · variabili d'ambiente · endpoint/metodi con shape request/response · webhook (endpoint nostro, verifica firma, eventi, mapping) · file nel codice · gestione errori e gating · costi · note/TODO.

## Registro integrazioni

| Integrazione | Tipo | Stato | Scheda |
|---|---|---|---|
| <servizio> | API / webhook | 🔜 pianificata | [_template.md](_template.md) |

## Webhook in entrata (endpoint esposti dalla nostra app)

| Endpoint | Provider | Verifica | Scheda |
|---|---|---|---|
| `POST /api/webhooks/<x>` | <provider> | firma/secret | — |

## Gating / graceful degradation
Ogni integrazione è **opzionale a runtime**: senza le sue variabili d'ambiente l'app resta pienamente funzionante e la funzione appare disabilitata. Verifica con `isXxxConfigured()` per ciascuna.

Nuova scheda: `/integration <nome servizio>` oppure `node .claude/scripts/new-integration.mjs "Nome"`.
