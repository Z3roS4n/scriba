# .claude/project — Documenti di progetto Scriba

Documenti essenziali per uno sviluppo coerente. **Leggerli prima di implementare; aggiornarli quando una decisione cambia (stesso commit).**

| Doc | Contenuto |
|---|---|
| [01-architecture.md](01-architecture.md) | Architettura, componenti, flussi, struttura repo |
| [02-tradeoffs.md](02-tradeoffs.md) | Registro decisioni (ADR) + decisioni aperte |
| [03-stack.md](03-stack.md) | Stack, librerie, env contract, servizi esterni |
| [04-data-model.md](04-data-model.md) | Modello dati, vincoli, macchine a stati |
| [05-api-endpoints.md](05-api-endpoints.md) | Server actions, route handlers, convenzioni errori |
| [06-code-style.md](06-code-style.md) | Stile codice, naming, UI, test, git |
| [07-bad-practices.md](07-bad-practices.md) | Cosa NON fare (lista viva) |
| [08-react-next-performance.md](08-react-next-performance.md) *(solo stack React/Next)* | Direttive performance: waterfall, bundle, RSC, re-render |
| [09-roadmap.md](09-roadmap.md) | Fasi con checklist e criteri di verifica |
| [10-packaging.md](10-packaging.md) | Come si costruisce l'installer Windows (PyInstaller + electron-builder), dove sono i pezzi, cosa verificare |
| `reports/` | Report datati `{DATA}-{ORA}.report-{NOME}.md` per ogni modifica completata |
| `research/` | Note di ricerca datate `{DATA}.{NOME}.md` |
| `design/` *(solo se il progetto ha un redesign/nuovo design UI)* | Sistema di design, decisioni, gap funzionali — generato da `/design-setup` |
| `roadmap-frontend.md` *(sibling di `design/`)* | Avanzamento del redesign UI per fase/sezione |

## Convenzioni operative
- Commit: author `Thepro007002001@gmail.com`, **niente co-author**.
- Dopo ogni task completato con successo: report in `reports/`.
- Ogni integrazione esterna documentata in `.claude/integrations/` (stesso incremento).
- Se il progetto include un redesign/nuovo design UI, la documentazione di stile/decisioni/gap vive
  **solo** in `design/` — non duplicarla nei doc numerati né lasciarla solo in chat.
