# Changelog

Tutto quello che è cambiato in Scriba, dal più recente.
In English: [CHANGELOG.md](CHANGELOG.md).

Ogni voce è divisa in tre sezioni, ed è la più alta presente a decidere lo
scatto di versione: **Cambiamenti che rompono** (maggiore), **Funzioni nuove**
(minore), **Correzioni** (patch). Una sezione senza voci si lascia fuori.

## 0.5.0 — 7 agosto 2026

Prima release pubblicata. Il progetto esisteva già da parecchio: questa voce
copre cosa è cambiato di recente, non tutta la sua storia.

Scriba registra le call di lavoro, le trascrive mentre parli e ne ricava
riassunto, punti salienti e task. La trascrizione è sempre locale; l'analisi lo
è se lo scegli.

### Funzioni nuove

- **I nomi propri si possono correggere.** Un nome che il modello non conosce lo
  indovina da capo a ogni frase, e ogni volta in modo diverso: nella stessa call
  «Clotilde» usciva come *Tilde*, *Cotilde* e *Protile*. In Impostazioni →
  Trascrizione → Nomi propri si scrivono quelli che contano, uno per riga; i
  clienti dell'anagrafica ci entrano da soli. Il testo di partenza resta
  salvato, quindi ogni correzione è verificabile.
  ([#42](https://github.com/Z3roS4n/scriba/issues/42))
- **«Rifai la trascrizione», con la lingua imposta.** Dal vivo trascrive il
  modello più veloce, che è anche l'unico a cui la lingua **non** si può
  imporre: la deduce dall'audio e ogni tanto sbaglia — sono le frasi che
  compaiono in spagnolo dentro una call italiana. A call finita si ripassa con
  Canary, che la lingua la accetta davvero (WER 5.3% contro 6.8% su FLEURS
  italiano, misurati sulla stessa macchina). Richiede un modello da ~1 GB, da
  Impostazioni → Modelli locali.
  ([#41](https://github.com/Z3roS4n/scriba/issues/41))
- **La nota di lavoro durante la call si vede.** Veniva generata e salvata, e
  non la mostrava nessuno — dal di fuori era indistinguibile da una funzione che
  non fa niente. Ora compare accanto alla trascrizione e si aggiorna mentre la
  riunione va. L'intervallo si sceglie (5 / 10 / 15 minuti): era fisso a dieci e
  non scritto da nessuna parte, quindi su una call più corta non ne usciva
  nessuna. ([#47](https://github.com/Z3roS4n/scriba/issues/47))
- **Si vede che versione stai usando.** Impostazioni → Dati e privacy, con
  accanto il commit da cui viene la build: fra due build della stessa versione è
  l'unica cosa che le distingue.
  ([#48](https://github.com/Z3roS4n/scriba/issues/48))

### Correzioni

- **Non si perdono più frasi intere.** Quando una frase non riusciva a
  chiudersi, la successiva ne prendeva il posto: la prima spariva e la seconda
  ereditava il suo orario. Non era il modello che capiva male — era testo
  trascritto bene e perso dopo.
  ([#40](https://github.com/Z3roS4n/scriba/issues/40))
- **L'audio degli altri segue l'orologio della call.** Il sistema non consegna
  nulla mentre nessuno riproduce audio, e quei silenzi nel file salvato non
  c'erano: su una call misurata qui mancavano 24 minuti, e ogni minuto della
  trascrizione puntava altrove dentro il file. Ora il silenzio si scrive.
  **Costa spazio**: un'ora in cui gli altri parlano venti minuti passa da
  ~37 MB a ~115 MB su quella traccia.
  ([#45](https://github.com/Z3roS4n/scriba/issues/45))
- La build pacchettizzata non riportava il commit da cui veniva.
  ([#52](https://github.com/Z3roS4n/scriba/pull/52))

### Cosa sapere prima di installare

- **L'installer non è firmato.** Windows mostrerà l'avviso di SmartScreen alla
  prima apertura.
- **Le call registrate prima di questa versione non si possono rifinire sulla
  traccia degli altri.** Quel file non contiene l'informazione per riallinearlo,
  e nessun calcolo la inventa: la rifinitura se ne accorge e rinuncia su quella
  traccia dicendolo, invece di riscrivere ogni riga con il testo di un'altra. La
  tua voce si rifinisce normalmente.
- **Solo Windows.** Nessun supporto macOS o Linux.
- **L'export verso Notion e il database PostgreSQL remoto non sono mai stati
  provati contro un servizio vero.** La logica è coperta da test con le chiamate
  simulate; finché quei test non girano contro un server reale, quelle due
  integrazioni vanno considerate non verificate.
