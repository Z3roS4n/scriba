# {{NAME}} — Modello dati

> Fonte di verità: lo schema ORM. Questo documento spiega intento, vincoli e stati.

## Entità principali
### <Entità>
- Campi chiave: <…>
- Vincoli: <unique, FK, indici>
- Note: <soft-delete? multi-tenant? scoping?>

## Macchine a stati
### <Entità> — stati
```
DRAFT → ACTIVE → DONE
         └──→ CANCELLED
```
- Transizioni consentite e chi le innesca.

## Regole di integrità
- <invarianti che il codice deve garantire>

## Migrazioni
- Regola: solo migrazioni versionate/tracciate. Mai modifiche a schema fuori dal sistema di migrazione.
