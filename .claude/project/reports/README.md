# reports/ — Report di avanzamento

Un report per ogni task completato con successo. Naming **obbligatorio**:

```
{YYYY-MM-DD-HH-mm}.report-{slug-task}.md
```

Esempio: `2026-07-11-13-56.report-fase3-stripe-pagamenti.md`

Genera con lo slash-command `/report <nome task>` (Claude Code) oppure:
```
node .claude/scripts/new-report.mjs "nome task"
```

Struttura del report: Cosa è stato fatto · File toccati · Sicurezza/idempotenza · Verifiche · Rinviato · Prossimo.
