# <Nome Servizio>

> <una riga: scopo>. **Gated**: se `SERVICE_API_KEY` non è impostata, la funzione è disattivata e non influisce sul resto dell'app.

## Scopo
<cosa fa e perché>

## Base URL / SDK e versione
- SDK `<pkg@version>` — oppure REST base URL `https://…`

## Autenticazione
<Bearer / HMAC / OAuth>

## Variabili d'ambiente
```
SERVICE_API_KEY=
SERVICE_BASE_URL=
SERVICE_WEBHOOK_SECRET=
```

## Endpoint / metodi usati
| Metodo | Path | Request | Response |
|---|---|---|---|
| POST | `/…` | `{…}` | `{…}` |

## Webhook
- Endpoint nostro: `POST /api/webhooks/<service>`
- Verifica firma: `SERVICE_WEBHOOK_SECRET`
- Eventi + mapping: <…>

## File nel codice
- `src/server/<service>/index.ts` — client lazy/gated
- `src/app/api/webhooks/<service>/route.ts` — endpoint

## Gestione errori e gating
- `isServiceConfigured()`; codici 200/400/401/503/500.

## Costi
<a consumo? flat?>

## Note / TODO
- <…>
