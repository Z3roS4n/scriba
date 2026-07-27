# {{NAME}} — API, actions & route handlers

> Convenzioni per mutazioni (server actions) e endpoint HTTP (route handlers).

## Principi
- Server actions = thin controller; la logica vive nei servizi (`src/server/services`).
- Route handlers solo per: webhook in ingresso, cron, download file, API pubblica.
- Validazione input con schema condiviso (stesso schema del form).

## Server actions
| Action | Input | Output | Servizio |
|---|---|---|---|
| `createX` | `{…}` | `{…}` | `services/x.ts` |

## Route handlers
| Metodo | Path | Scopo | Protezione |
|---|---|---|---|
| POST | `/api/webhooks/<provider>` | callback esterno | firma/secret |
| GET  | `/api/cron/<job>` | job schedulato | `Bearer CRON_SECRET` |

## Convenzioni errori
- Errori di dominio tipizzati; risposta HTTP coerente (400/401/403/404/409/500).
- Idempotenza per i webhook: transizioni di stato atomiche.
