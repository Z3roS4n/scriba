# AGENTS.md — {{NAME}}

Regole per gli agenti AI (Claude Code) che lavorano su questo repo.

## Prima di implementare
1. Leggi `.claude/project/README.md` e i doc numerati `01`–`09` pertinenti al task.
2. Leggi `.claude/project/07-bad-practices.md`: non ripetere errori già noti.
3. Se il task tocca un servizio esterno, leggi/crea la scheda in `.claude/integrations/`.
4. Se il progetto ha `.claude/project/design/` (redesign/nuovo design UI in corso), leggi
   `design/design-system.md` e `design/decisions.md` prima di toccare qualsiasi schermata.

## Durante
- Rispetta `06-code-style.md` (naming, confini, test, **commenti solo dove strettamente necessari**).
- Stack React/Next: rispetta `08-react-next-performance.md` **mentre scrivi** (no waterfall di
  `await`, no stato derivato in `useEffect`, `next/dynamic` per i pesi, props client minimali).
- Ogni decisione non ovvia → registrala in `.claude/project/02-tradeoffs.md` come `D-00X` (o in
  `design/decisions.md` come `D-UI-0X` se è una decisione di design/UI).
- Modifiche a schema DB: solo tramite migrazioni versionate, mai a mano.
- Segreti: mai con prefisso pubblico; validare l'env allo startup.

## A task completato (obbligatorio)
- Genera un report: `/report <nome task>` → in `.claude/project/reports/`.
- Se hai integrato un servizio esterno: scheda in `.claude/integrations/` + riga nel registro (`README.md`).
- Aggiorna i doc di progetto toccati dalla decisione (stesso commit).

## Commit
- Author: `{{EMAIL}}`. **Mai co-author.** Messaggi imperativi in inglese.

## Comandi rapidi (slash-command)
- `/report <task>` — nuovo report datato
- `/research <argomento>` — nuova nota di ricerca
- `/integration <servizio>` — nuova scheda integrazione
- `/setup-project` — (ri)genera la struttura `.claude/`
- `/design-setup` — genera `.claude/project/design/` + `roadmap-frontend.md` per un redesign UI
