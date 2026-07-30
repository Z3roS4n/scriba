# Da implementare — funzionalità nel design ma assenti nel backend

> Registro delle funzionalità che **compaiono nel design** ma per cui **non esiste ancora supporto
> backend**. Non vanno inventate al volo: si annotano qui e si valutano dopo. Ogni voce: schermata
> di origine, cosa mostra, cosa manca lato backend, disposizione, priorità.

## Legenda priorità
- **P1** — blocca la fedeltà di una schermata core; da valutare a breve.
- **P2** — utile, ma la schermata resta sensata anche senza (placeholder/stato vuoto).
- **P3** — nice-to-have / raffinamento.

## Voci

### [DA-01] Dire all'utente che il database è stato messo da parte — nessuna schermata
- **Design:** non previsto: viene da un guasto, non dal mockup.
- **Backend attuale:** c'è. All'avvio `db/manutenzione.py` controlla il database e, se non è
  leggibile, lo mette da parte e ripristina il backup più recente; `GET /health` riporta
  `db_danneggiato` con il motivo, la cartella di quarantena e il backup ripristinato.
- **Disposizione:** da implementare. Oggi lo dicono solo i log, e l'utente si ritrova
  l'elenco delle call tornato indietro senza sapere perché — che è il modo peggiore di
  scoprirlo.
- **UI ora:** niente. Serve un avviso persistente (non un toast che passa) con il percorso
  della cartella di quarantena, apribile nell'esplora risorse.
- **Priorità:** P1. **Risolta** nella issue #6, branch `fix/avviso-database-messo-da-parte`.

<!--
Template voce:

### [ID] Titolo — schermata di origine
- **Design:** cosa mostra/promette il design (rif. mockup/regione).
- **Backend attuale:** cosa esiste già e cosa manca.
- **Disposizione:** come si procede — implementare ora / rinviato (e perché) / fuori scope. Non
  implementare senza richiesta esplicita del cliente/PM, anche se sembra piccola.
- **UI ora:** come renderizzare la schermata nel frattempo (stato vuoto/disabilitato — mai dati finti).
- **Priorità:** P1/P2/P3.
-->
