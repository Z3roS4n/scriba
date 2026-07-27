# Scriba — Stack tecnico

> Versioni pinnate alla prima installazione; aggiornare qui a ogni upgrade.

**Versioni installate (2026-07-27):** <framework x.y · linguaggio · runtime · …>

## Runtime & framework
| Layer | Scelta | Note |
|---|---|---|
| Framework | **<…>** | |
| Linguaggio | **<…>** strict | |
| Deploy | **<…>** | |
| DB | **<…>** | |
| ORM | **<…>** | |
| Auth | **<…>** | |
| File / storage | **<…>** | |

## Librerie applicative
| Scopo | Libreria | Motivo |
|---|---|---|
| UI kit | **<…>** | |
| Form / validazione | **<…>** | |
| Test | **<…>** | |
| Lint / format | **<…>** | |

## Variabili d'ambiente (contratto)
```
DATABASE_URL=
AUTH_SECRET=
# … un segreto per riga; nessun prefisso NEXT_PUBLIC_ sui segreti
```
Regola: validare l'env allo startup con uno schema (`src/lib/env.ts`).

## Servizi esterni e piani
- **<servizio>**: <account, ambienti sandbox/prod, costi>
