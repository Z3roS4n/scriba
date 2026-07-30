# Scriba — Bad practices (cosa NON fare)

> Lista viva. Ogni volta che un errore viene individuato in review, si aggiunge qui.

- ❌ `any` per zittire il compilatore. Usare `unknown` + narrowing.
- ❌ Logica di dominio dentro i componenti o le server actions.
- ❌ Import diretto del client DB fuori dal modulo dedicato.
- ❌ Segreti con prefisso pubblico (es. `NEXT_PUBLIC_`).
- ❌ Float sugli importi monetari. Usare un tipo decimale.
- ❌ Modificare lo schema DB fuori dal sistema di migrazione.
- ❌ Stringhe hardcoded sparse per testi/valori di dominio.
- ❌ Integrazione esterna senza scheda in `.claude/integrations/`.
- ❌ Task completato senza report in `reports/`.
- ❌ Lasciare i dati di una call nel solo WAL. Il consolidamento automatico di SQLite è
  passivo e rinuncia in silenzio: si chiama `Store.consolida()` nei punti in cui il lavoro
  diventa definitivo (vedi `D-009`).
- ❌ Uccidere il core invece di fermarlo. `os._exit`/`kill()` saltano lo spegnimento, e con
  esso il consolidamento del database. E su Windows `kill()` non prende l'albero: in
  sviluppo il core è un nipote di Electron, e sopravvive.
- ❌ Continuare a usare un database che non passa il controllo di integrità. Si mette da
  parte con tutto il suo WAL, non si prova ad aggiustarlo scrivendoci dentro.
