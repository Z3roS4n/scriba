# {{NAME}} — Performance React / Next.js (App Router)

> **Solo per stack React/Next.** Se il progetto non è React/Next, elimina questo file.
>
> Direttive per evitare i problemi di performance tipici, distillate dal guidebook
> *Vercel React Best Practices* (70 regole, 8 categorie — qui le alto-impatto più facili da
> violare). Ogni voce cita il `prefix-regola` del guidebook per approfondire. Rispettarle
> **mentre si scrive**, non come fix a posteriori.

## 1. Eliminare i waterfall (impatto CRITICO)
Ogni `await` sequenziale su dati **indipendenti** aggiunge una latenza di rete piena. È il killer #1.

- **Fetch indipendenti in parallelo** con `Promise.all` (o util tipo `better-all` per dipendenze
  parziali). Mai `const a = await x(); const b = await y();` se `b` non dipende da `a`.
  `[async-parallel, async-dependencies]`
- **Ristruttura i componenti** perché i fetch partano insieme, non annidati a cascata; per liste,
  incatena i fetch per-item dentro un unico `Promise.all`. `[server-parallel-fetching, server-parallel-nested-fetching]`
- **Await tardivo**: avvia le promise presto, `await` solo nel ramo dove il valore serve davvero
  (soprattutto nei route handler / server actions). `[async-defer-await, async-api-routes]`
- **Condizione sincrona economica prima dell'await**: controlla i flag sync prima di awaitare
  valori remoti. `[async-cheap-condition-before-await]`
- **Streamma con `Suspense`**: avvolgi le parti lente in `<Suspense>` e definisci `loading.tsx`
  (ed `error.tsx`) per ogni route non banale — così la shell appare subito. `[async-suspense-boundaries]`

## 2. Bundle size (impatto CRITICO)
Meno JS iniziale = TTI e LCP migliori.

- **`next/dynamic`** per componenti pesanti o raramente visibili (editor, canvas, grafici, mappe,
  viewer PDF): non zavorrare il primo caricamento. `[bundle-dynamic-imports]`
- **Import diretti, no barrel file** (`import x from "lib/x"`, non `import { x } from "lib"`):
  i barrel trascinano l'intero modulo nel bundle/trace. `[bundle-barrel-imports, bundle-analyzable-paths]`
- **Carica moduli solo quando la feature si attiva** e **terze parti (analytics/logging) dopo
  l'hydration**, mai nel path critico. `[bundle-conditional, bundle-defer-third-party]`
- **Preload su hover/focus** per velocità percepita sulle azioni probabili. `[bundle-preload]`

## 3. Server-side / RSC (impatto ALTO)
- **Props ai client component minimali**: passa solo i campi che servono, non interi oggetti ORM.
  Ogni prop di un client component viene serializzata nel payload HTML. `[server-serialization, server-dedup-props]`
- **`React.cache()`** per deduplicare le letture per-request (es. la funzione che risolve
  sessione/utente/azienda, chiamata sia nel layout sia nella pagina). `[server-cache-react]`
- **Autentica/scopa le server actions come le API route**: l'identità (utente/tenant) si risolve
  sempre server-side dalla sessione, mai da input del client. `[server-auth-actions]`
- **Niente stato mutabile a livello di modulo** che dipende dalla request in RSC/SSR: è condiviso
  tra richieste/utenti → data leak. `[server-no-shared-module-state]`
- **I/O statico (font, loghi, config) hoistato a livello di modulo**, non rifatto a ogni render;
  usa `after()` per lavoro non bloccante post-risposta. `[server-hoist-static-io, server-after-nonblocking]`

## 4. Re-render (impatto MEDIO)
- **Deriva lo stato durante il render, NON con `useEffect` + setState.** È l'anti-pattern più
  comune: causa render doppi, flicker e i warning `set-state-in-effect`. Se un valore si calcola
  dalle props/stato, calcolalo inline (o `useMemo`), non sincronizzarlo con un effetto.
  `[rerender-derived-state-no-effect, rerender-derived-state]`
- **Non definire componenti dentro altri componenti**: a ogni render è un tipo nuovo → React
  smonta e rimonta tutto il sottoalbero. Estraili fuori. `[rerender-no-inline-components]`
- **Logica di interazione negli event handler, non negli effetti** che reagiscono allo stato.
  `[rerender-move-effect-to-event]`
- **`useTransition` / `useDeferredValue`** per update non urgenti (filtri, ricerche, tabelle
  dense) così l'input resta reattivo. `[rerender-transitions, rerender-use-deferred-value]`
- **`useState(() => …)`** per init costose; **setState funzionale** (`setX(x => …)`) per callback
  stabili; **`useRef`** per valori transienti ad alta frequenza che non devono ri-renderizzare.
  `[rerender-lazy-state-init, rerender-functional-setstate, rerender-use-ref-transient-values]`

## 5. Rendering (impatto MEDIO)
- **Condizionali in JSX con ternario, non `&&`**: `cond ? <X/> : null`, così non renderizzi mai
  `0`/`NaN` per errore. `[rendering-conditional-render]`
- **`content-visibility`** per liste lunghe fuori viewport; **`Activity`** per mostrare/nascondere
  invece di montare/smontare. `[rendering-content-visibility, rendering-activity]`
- **JSX statico hoistato** fuori dal componente; **`suppressHydrationWarning`** solo per i mismatch
  attesi (es. tema/data client-only). `[rendering-hoist-jsx, rendering-hydration-suppress-warning]`

## 6. JavaScript (impatto BASSO — solo hot path)
Micro-ottimizzazioni: applicarle **solo** su percorsi caldi provati, non ovunque (leggibilità prima).
`Set`/`Map` per lookup ripetuti O(1), `Map` indice invece di `find` in loop, early-exit, `toSorted`
per immutabilità, `flatMap` per map+filter in un passo, hoist di `RegExp` fuori dai loop.
`[js-set-map-lookups, js-index-maps, js-early-exit, js-tosorted-immutable, js-flatmap-filter, js-hoist-regexp]`

---

**Fonte completa**: skill `vercel-react-best-practices` (70 regole con esempi corretto/sbagliato per
ognuna). Consultarla quando serve il dettaglio o un caso non coperto qui.
