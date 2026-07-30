# AGENTS.md — Scriba

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

## Issue: si aprono su GitHub, e si lavora da lì
Ogni difetto, mancanza o richiesta diventa **prima** una issue su GitHub
([Z3roS4n/scriba](https://github.com/Z3roS4n/scriba/issues)), poi codice. Niente correzioni
al volo senza issue: un difetto che vive solo in una conversazione è un difetto che si
ripresenta, e chi arriva dopo non ha modo di sapere che era già noto.

**Come si scrive.** Linguaggio descrittivo, non telegrafico:
- Titolo = il **sintomo** come lo vede chi usa l'app, non la diagnosi.
- Corpo: cosa succede · cosa ci si aspetterebbe · perché succede (con i riferimenti al
  codice, `file:riga`) · come riprodurlo · cosa resta da decidere.
- Se la causa non è certa, si scrive che non è certa. Un'ipotesi presentata come causa fa
  perdere tempo a chi la prende in carico.

**Come si lavora.** Mai su `main`. Un branch per issue, o per gruppo di issue che si
risolvono insieme, con un nome che dice di cosa si tratta:
`fix/<sintomo>`, `feat/<funzione>`, `chore/<lavoro>`. `main` resta la versione che gira:
un branch si può abbandonare, una modifica fatta direttamente su `main` no.

**Come si chiude.** Il commit o la PR che la risolve la cita (`Closes #N`). La issue è il
posto dove sta la storia del difetto: le decisioni non ovvie prese risolvendola vanno
comunque in `02-tradeoffs.md`, perché una issue chiusa nessuno la rilegge.

**Contributi pubblici.** Una issue chiusa da una PR di qualcuno che non è il maintainer
viene registrata **automaticamente** in [.claude/project/contributi.md](.claude/project/contributi.md)
dal workflow `.github/workflows/registra-contributi.yml`. Il registro non si compila a mano:
ricordarselo è esattamente ciò che non funziona.

## Commit
- Usa l'identità Git già configurata in locale. **Mai co-author.** Messaggi imperativi in inglese.

## Comandi rapidi (slash-command)
- `/report <task>` — nuovo report datato
- `/research <argomento>` — nuova nota di ricerca
- `/integration <servizio>` — nuova scheda integrazione
- `/setup-project` — (ri)genera la struttura `.claude/`
- `/design-setup` — genera `.claude/project/design/` + `roadmap-frontend.md` per un redesign UI
