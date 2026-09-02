# Tre ricerche nell'archivio: normale, semantica, contestuale

Issue [#104](https://github.com/Z3roS4n/scriba/issues/104),
[#105](https://github.com/Z3roS4n/scriba/issues/105),
[#106](https://github.com/Z3roS4n/scriba/issues/106) · branch
`feat/ricerca-semantica-contestuale` · versione 1.3.0.

Decisioni in `02-tradeoffs.md`, **D-022** … **D-027**.

---

## Cosa c'era prima

`Store.cerca_call()` con `LIKE` sul titolo e `MATCH` sull'indice FTS5. Trova
token. Due frasi che vogliono dire la stessa cosa con parole diverse, per
quell'indice, non si somigliano affatto — e dopo qualche mese chi cerca ricorda
l'argomento, non le parole.

Il modello di linguaggio c'era già e analizzava ogni call appena finita. Su
tutto l'archivio non lo usava nessuno. La confessione era già in pagina:
`PannelloIa` esporta le call **verso** un modello di fuori.

## Cosa c'è adesso

Tre modalità dichiarate sopra la stessa casella. Normale è quella di prima.
Semantica cerca per significato. Contestuale fa una domanda a un modello che
legge il materiale e risponde citando da dove viene, e può leggere insieme le
call dello stesso cliente vicine nel tempo.

I filtri — cliente, periodo, stato — valgono per tutte e tre e si applicano
prima. Una call esclusa non rientra nemmeno attraverso la risposta del modello.

## I due numeri che hanno deciso il progetto

Misurati con `spikes/bench_semantica.py`, che resta nel repo: 20 passaggi di
parlato di lavoro in italiano, 18 domande scritte apposta con parole diverse da
quelle dette.

| | prima giusta | fra le prime tre | MRR | ms/passaggio | MB |
|---|---|---|---|---|---|
| parole in comune (la base) | 33% | 67% | 0,502 | — | 0 |
| **e5-small fp32** | 78% | **94%** | 0,847 | 9 | 470 |
| e5-small int8 | 78% | 83% | 0,835 | 5 | 118 |
| e5-base fp32 | 89% | 89% | 0,914 | 44 | 1110 |

Due letture, e la seconda è quella che conta di più.

**La ricerca semantica vale i suoi megabyte.** Contro una base lessicale — che è
in piccolo quello che fa la FTS di oggi — 0,85 di MRR contro 0,50. Senza quel
confronto, «funziona» non avrebbe voluto dire niente.

**I punteggi di E5 sono schiacciati.** Stanno tutti fra 0,80 e 0,90 anche fra
frasi senza niente in comune: due passaggi presi a caso danno 0,878, più di
certe coppie domanda/risposta giuste. Nessuna soglia assoluta è possibile, e il
punteggio non si mostra mai a chi cerca — «0,87» si legge come «87% pertinente»
e non significa niente del genere. Il taglio è **relativo al migliore**: a −0,02
restano 2,9 passaggi su 20 e la risposta giusta c'è 18 volte su 18.

Questo ha cambiato il progetto in un punto che sembrava scontato: il taglio
relativo **non si applica** al materiale che va al modello. Applicato lì
toglierebbe di mano la call le cui parole sono più lontane da quelle della
domanda — cioè quella che #106 esisteva per far vedere. Il tetto è un numero di
passaggi, e a scartare è il modello, che li legge.

## Le guardie, e come sono state dimostrate

Ogni comportamento che regge una promessa è stato rotto apposta per vedere
fallire il test che lo copre. Nell'ordine:

| rotto | il test che se n'è accorto |
|---|---|
| la firma dell'indice dimentica `revision`/`eco` | rifinitura e filtro eco non rendevano più vecchio l'indice |
| soglia assoluta invece che relativa | passava anche quello che non c'entrava |
| la catena non si ordina nel tempo | la storia veniva raccontata alla rovescia |
| nessuna sovrapposizione fra passaggi | — **non se n'è accorto nessuno** |
| il modello può citare una call che non ha ricevuto | la call inventata arrivava a chi aveva chiesto |
| un passaggio si attacca a qualunque call | quello di una call veniva attribuito a un'altra |
| nessun tetto per call | — **non se n'è accorto nessuno** |

Le due righe vuote sono la parte utile di questo esercizio. Il test sulla
sovrapposizione usava segmenti che condividevano parole comuni — «con», «di»,
«parole» — quindi due passaggi risultavano sovrapposti anche togliendo la
sovrapposizione: passava sempre, senza verificare niente. Il test sul tetto
contava le intestazioni delle call, che sono una per call comunque. Riscritti
entrambi, e riprovati rompendo di nuovo.

## Due difetti trovati guardando la schermata, non ragionandoci

- Passando a Contestuale restavano in pagina i risultati della Semantica, dove
  si leggevano come la risposta a una domanda che nessuno aveva ancora fatto.
- Una call senza titolo lasciava una freccia sospesa nella riga della catena, e
  la catena sembrava avere un anello in meno di quelli davvero letti. Il rimedio
  ha cambiato la rotta: `session_ids` e `titoli` affiancati si disallineano al
  primo elemento che manca da uno dei due, e una catena con i titoli sfalsati
  non si distingue da una giusta. Adesso sono coppie.

## Il giro con il modello vero

Fatto una volta, fuori dai test, con `EmbedderE5` che punta ai pesi veri e tutto
il resto del codice vero — `Store`, `Indice`, la divisione in passaggi. Tre call
finte ma scritte come si parla in riunione, sei domande poste con altre parole:

```
carica 2,8s · indicizza 3 call in 0,12s (3 passaggi)
prima call giusta: 6/6
secondo giro: 0 call     dopo una rifinitura: 1 call da rifare
```

Da qui è venuto fuori l'unico difetto che né i test né il finto potevano
mostrare: **un passaggio vero è lungo circa 700 caratteri**, e nell'elenco
diventava un muro di testo alto quanto lo schermo. Il frammento della ricerca
normale è corto — la FTS ne dà una dozzina di parole — quindi la riga non aveva
mai avuto un limite. Adesso si taglia a tre righe, misurato in pagina: 455
caratteri in 61 pixel.

## Cosa non è stato verificato

- **La qualità su un archivio vero.** I numeri vengono da passaggi scritti per
  la prova. Sono onesti — le domande usano parole diverse da quelle dei passaggi,
  apposta — ma non sono un archivio di call vere.
- **Lo scaricamento dei pesi.** `scarica()` e `installato()` passano da
  `huggingface_hub`, e la cache non è stata popolata: i pesi usati per le prove
  stanno altrove, indicati a mano. È l'unico pezzo del percorso che nessuno ha
  ancora eseguito.
- **Il giro dentro l'applicazione in esecuzione.** Il codice è lo stesso, ma
  premere «Leggile» in Scriba e aspettare che finisca non l'ha fatto nessuno.
- **Le risposte della ricerca contestuale con un modello vero.** Tutti i test
  usano un modello finto: verificano cosa il codice fa della risposta, non
  quanto la risposta sia buona.

## Nota sull'ambiente

Il Python 3.12 del repo (`.tools/python`, scaricato da uv) non è più
utilizzabile su questa macchina: Application Control blocca `unicodedata.pyd`,
e senza quello non parte nemmeno `pytest`. È lo stesso criterio che blocca
l'installer non firmato di #57. La suite è stata eseguita con un interprete
3.14 di sistema, che quel criterio considera fidato: **717 test passati, 13
saltati**. Vale come verifica dei comportamenti, non della versione di Python
con cui Scriba viene spedito — quella la controlla la CI.
