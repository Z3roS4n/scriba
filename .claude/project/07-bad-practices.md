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
