# Scriba — Stile codice & UI

## Linguaggio
- Type-safety strict. Vietato `any` (usare `unknown` + narrowing); cast solo con commento che spiega perché è sicuro.
- Tipi di dominio esportati dai servizi e riusati: la UI non ridefinisce mai le shape.
- Una sola fonte di validazione (schema condivisi tra form e server).

## Commenti nel codice
Commentare **solo dove strettamente necessario** perché uno sviluppatore (anche senza AI) capisca
il codice — un vincolo nascosto, il perché di una scelta non ovvia, una regola di dominio che il
nome della variabile non può portare da solo. Se il codice è già chiaro da sé (nomi espressivi,
struttura semplice), **non scriverlo**. Niente commenti che ripetono cosa fa il codice, niente
narrazione del task/fix corrente, niente commenti "decorativi" o di sezione superflui.

## Naming
- File: kebab-case. Componenti: PascalCase. Funzioni/variabili: camelCase. Enum: SCREAMING_SNAKE.
- Il dominio parla inglese nel codice; la UI nella lingua utente. Termini intraducibili commentati.

## Struttura & confini
- `src/server/**` non importabile dai client component (guardia `server-only`).
- Logica di dominio nei servizi, NON nelle actions (thin) né nei componenti.
- Client DB solo via un modulo unico. Import diretto altrove = errore in review.
- Utility pure (money, date, formatters) in `src/lib`, testate unit.

## UI
- Design system unico; tema neutro/professionale, accent singolo (token in `globals.css`).
- Niente `alert()`/`confirm()` nativi — dialog del design system.
- **Controlli di form sempre stilizzati, mai nativi** (`<select>`/checkbox/radio nativi ignorano il
  tema — vedi `.claude/project/design/design-system.md` se il progetto ha un redesign in corso).
- Ogni tabella: empty state con CTA, skeleton in loading, errori con retry.
- Accessibilità: label su ogni input, focus visibile, contrasto AA.

## Test
- Unit sulla logica critica; golden-file dove l'output è un artefatto stabile.
- Integrazione: actions su DB di test. E2E sui flussi critici.
- Il codice critico non si merge senza test.

## Git & processo
- Commit: usa l'identità Git già configurata in locale, **mai co-author**. Messaggi imperativi in inglese.
- Feature branch per lavori multi-commit.
- Dopo ogni task: report in `.claude/project/reports/{DATA}-{ORA}.report-{NOME}.md`.
