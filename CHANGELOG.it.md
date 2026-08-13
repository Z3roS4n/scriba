# Changelog

Tutto quello che è cambiato in Scriba, dal più recente.
In English: [CHANGELOG.md](CHANGELOG.md).

Ogni voce è divisa in tre sezioni, ed è la più alta presente a decidere lo
scatto di versione: **Cambiamenti che rompono** (maggiore), **Funzioni nuove**
(minore), **Correzioni** (patch). Una sezione senza voci si lascia fuori.

## 1.1.4 — 13 agosto 2026

### Correzioni

- **Un'analisi finita veniva buttata via se lo «Interrompi» arrivava
  all'ultimo momento.** Riassunto, punti salienti e task erano già scritti: a
  mancare erano le due righe che segnano la call come analizzata. Su una call
  di due ore voleva dire dieci minuti di lavoro — e su un motore a consumo,
  soldi già spesi — sostituiti da «Analisi non riuscita». L'ultimo confine non
  interrompe più; tutti quelli prima sì.
- **Il riquadro dell'errore prendeva il posto dell'analisi invece di starle
  sopra.** Un tentativo fallito o interrotto adesso lascia visibile quello che
  c'è, compreso quello che il tentativo stesso aveva scritto prima di
  fermarsi.
- Il pannello dice cos'è successo davvero — «Interrotta dall'utente.» —
  invece del generico «L'ultima analisi non è riuscita.», che non dice niente
  proprio quando serve saperlo.

## 1.1.3 — 13 agosto 2026

### Correzioni

- **L'interfaccia rispondeva male durante la registrazione.** Il cronometro
  della barra teneva il suo stato nel componente radice e batteva due volte al
  secondo, quindi due volte al secondo si ridisegnavano elenco call,
  trascrizione e pannello analisi — con un elemento per riga di trascrizione, e
  una call lunga ne ha un paio di migliaia. Adesso il cronometro ridisegna il
  cronometro.
- **Quando la rifinitura si rifiutava di riallineare le tracce**, il pannello
  diventava un muro rosso che diceva due volte la stessa cosa, un paragrafo per
  traccia, con il pulsante «Rifai» appeso in fondo. Il motivo descrive la call,
  non la traccia: adesso si dice una volta, con le tracce nominate insieme, il
  rosso come filo a sinistra invece che su otto righe, e il comando accanto
  all'esito. Usciva anche in italiano dentro un'interfaccia in inglese.

## 1.1.2 — 11 agosto 2026

### Correzioni

- **Mentre l'analisi lavorava l'elenco delle fasi usciva sfasciato**: la nota
  di ogni fase andava a capo una parola per riga — «67» / «s», «4» / «di» /
  «6» / «blocchi» — e i titoli slittavano verso destra. Fasi e note erano
  anche in italiano dentro un'interfaccia in inglese: la traduzione c'era nel
  core e non la chiamava nessuno, e le note viaggiano sul websocket, dove la
  lingua di chi guarda non arriva. Adesso escono come gettone e la frase la
  scrive l'interfaccia.
- **Con l'analisi non riuscita i tre pulsanti uscivano dal pannello**, il
  terzo tagliato a metà, e avevano tre altezze diverse. E da quella schermata
  sparivano «Distingui le voci» e «Rifai la trascrizione»: lavorano
  sull'audio, non sul risultato dell'analisi, e non si vedevano proprio quando
  rifare la trascrizione è la cosa più sensata da provare.
- Quattro frasi restavano in italiano perché il metro delle stringhe scartava
  qualunque testo con dentro una parentesi tonda. Una di quelle è la riga che
  dice che il modello Canary non è scaricato — cioè quello che si legge
  andando a cercare proprio quel pulsante.

## 1.1.1 — 11 agosto 2026

### Correzioni

- **Undici schermate uscivano senza stile.** Con il foglio di stile 1.0
  diverse classi hanno cambiato nome; i componenti hanno continuato a
  scrivere i nomi vecchi, quindi quelle regole non si applicavano a niente.
  Nella nota di lavoro l'etichetta e il minuto uscivano attaccati — «NOTA DI
  LAVOROfino a 29:59» — e modelli, prove, scorciatoie, percorsi dei file,
  clienti, fasi dell'analisi e scatti nella striscia comparivano col testo
  nudo. Trentacinque classi, adesso rinominate come le chiama il design o
  scritte come aggiunte dichiarate.
- **Il pulsante «Analizza la call» poteva restare irraggiungibile a call
  finita.** Con le note incrementali accese le note lo spingevano sotto il
  bordo di una colonna che non scorreva. Quattro rami del pannello avevano
  lo stesso difetto. A call finita la nota sta adesso sotto il pulsante
  invece che sopra, perché il pulsante è quello che si viene a cercare.
- **Durante la call la colonna di destra non scorreva.** La nota di lavoro
  cresce a ogni aggiornamento — ognuna riscrive dentro di sé le precedenti —
  quindi dalla seconda in poi il fondo restava tagliato via, senza barra e
  senza modo di arrivarci.
- **Nella nota di lavoro si vedevano gli asterischi del Markdown** invece del
  grassetto. C'erano due renderer per lo stesso testo e solo uno lo faceva;
  adesso è uno solo, e rende come elenchi anche quelli numerati.
- Tre frasi restavano in italiano con l'interfaccia in inglese: il «fino a»
  della nota, l'avviso sul motore nel pannello analisi e l'esito dell'export
  nell'archivio.

## 1.1.0 — 10 agosto 2026

### Funzioni nuove

- **Scriba parla inglese.** Impostazioni → Aspetto → Lingua dell'interfaccia:
  italiano, inglese, o come il sistema. Vale subito, senza riavviare, per la
  finestra principale, le impostazioni, la striscia sopra la call, il menu
  della barra e il messaggio che compare se il core non parte. Non tocca la
  lingua delle call, che resta in Trascrizione: un'interfaccia in inglese
  sopra una riunione in italiano è il caso normale, non un errore.
- Date, ore e dimensioni seguono la lingua: «14 ago 2026» e «6,4 GB» in
  inglese diventano "14 Aug 2026" e "6.4 GB".
- Anche i testi che nascono nel core tornano nella stessa lingua: i motori di
  analisi con i loro rimedi, le fasi dell'analisi, la nota sotto ogni modello
  locale, l'elenco dei campi Notion, il modello dati del database remoto e i
  messaggi d'errore. La lingua viaggia in `Accept-Language`, aggiunta in un
  punto solo: nessuna rotta può dimenticarsene.
- Quello che Scriba confronta non si traduce. `local`, `confirmed`, `mic` e
  gli altri identificatori restano uguali nelle due lingue: si etichettano
  dove si mostrano, mai dove si controllano.

## 1.0.0 — 9 agosto 2026

### Cambiamenti che rompono

- **L'interfaccia è rifatta da capo.** Scriba adotta il design system di M's
  Works: nuovo carattere (Montserrat, dentro l'installer, funziona offline),
  nuova palette, e soprattutto una scala unica per i controlli — un pulsante
  ha la stessa misura ovunque, e un campo di testo prende l'altezza del
  pulsante che gli sta accanto. Niente si perde per strada, ma **diverse cose
  hanno cambiato posto**, e le più notevoli sono queste:
  - L'elenco delle call non scrive più lo stato («analizzata», «registrata»)
    su ogni riga. Al suo posto dice quello che cambia una decisione: quante
    task aspettano una conferma, quante ce ne sono, o che l'analisi non è
    riuscita. Il cliente sta sulla stessa riga, a sinistra.
  - Nel pannello dell'analisi, «Rifai la trascrizione» e le voci distinte sono
    scese in fondo: sono lavori che si fanno sulla trascrizione a call finita,
    non comandi dell'analisi, e in testa facevano aprire il pannello su tre
    controlli prima di qualsiasi contenuto.
  - La piega delle righe riprese dall'altoparlante è passata dalla barra del
    titolo alla prima riga della trascrizione, dove sono le righe di cui parla.
  - La confidenza di una task si scrive **solo sotto 0,80**, dove cambia una
    decisione. Stampata su ogni riga era una colonna di numeri che non
    leggeva nessuno.
  - «Passa in rassegna» compare solo sopra le cinque task da confermare. Sotto
    quella soglia si lavora in riga, e il conteggio resta comunque.

### Funzioni nuove

- **La ricerca nell'archivio mostra la frase, non solo il titolo.** Cercando
  una parola dentro il parlato, ogni risultato riporta il punto in cui è stata
  detta, con la parola evidenziata. L'indice full-text c'era da sempre e
  serviva solo a filtrare. Le righe riprese dall'altoparlante non vengono mai
  citate: sarebbero le tue stesse parole restituite come se le avesse dette
  l'altro.
- **Gli screenshot si vedono nella trascrizione.** Dove prima c'era un
  rettangolo con scritto «screenshot 1280×760» adesso c'è la schermata. Il
  clic la apre a dimensione piena come prima; se il file è stato spostato o
  cancellato, la riga lo dice invece di mostrare un'immagine rotta.

### Correzioni

- **Le righe riprese dall'altoparlante non sembrano più tue.** Arrivano dal
  microfono, quindi prendevano il filetto e la fascia con cui si riconosce
  «Io» a colpo d'occhio — mentre l'etichetta accanto diceva «ripresa». A
  guardarla era tua, a leggerla no.
- **I menù a tendina non aprono più una finestra di sistema.** Erano `select`
  nativi: su Windows ignorano il tema dell'applicazione e aprono un menù
  chiaro sopra una finestra scura, con un carattere che non è quello
  dell'interfaccia.
- **I campi di testo usano il carattere dell'interfaccia.** Un campo non lo
  eredita da solo, e nessuno gliel'aveva detto: ogni casella rendeva nel
  carattere predefinito del browser.

## 0.6.3 — 9 agosto 2026

### Correzioni

- **Scriba può finalmente contenere un font proprio.** Tre cose lo impedivano,
  e nessuna delle tre dava errore: il CSP delle pagine non permetteva i font
  nemmeno se locali, la build copiava sei file per nome e quindi non avrebbe
  mai portato dentro una cartella, e i file non c'erano. Il risultato sarebbe
  stato un'applicazione che parte nel carattere di ripiego e sembra a posto.
  Ora Montserrat viaggia dentro l'installer con la sua licenza SIL OFL, e la
  build **si ferma** se un font o un'immagine dichiarati in un foglio di stile
  non finiscono nel pacchetto. L'interfaccia non cambia aspetto: il carattere
  entrerà in uso con il nuovo design.
  ([#81](https://github.com/Z3roS4n/scriba/issues/81))

## 0.6.2 — 9 agosto 2026

### Correzioni

- **La nota di lavoro si vede durante la call.** Era montata solo nei rami del
  pannello che durante una registrazione non vengono mai raggiunti: la
  funzione esisteva, si aggiornava, e non la si poteva guardare proprio nel
  momento per cui è fatta. Aveva perfino un messaggio d'attesa scritto per
  quel momento — «La prima arriva dopo i primi dieci minuti di call» — che
  nessuno poteva aver letto. ([#70](https://github.com/Z3roS4n/scriba/issues/70))
- **La priorità di una task non si perde più.** Si scriveva a mano, e
  qualunque cosa diversa da `bassa`, `media`, `alta` o `critica` — bastava la
  maiuscola — faceva fallire la scrittura: il campo tornava com'era, senza
  dire niente. Ora i quattro valori si scelgono, il core rifiuta gli altri
  spiegando quali valgono, e un salvataggio che non riesce lo dice nel punto
  in cui si è premuto, tenendo il testo scritto. Vale per tutti e quattro i
  campi, non solo per la priorità.
  ([#71](https://github.com/Z3roS4n/scriba/issues/71))
- **Il costo dell'analisi è scritto in dollari, perché in dollari è.** Il
  pannello ci appendeva un `€` senza convertire niente: un numero sbagliato di
  poco e sempre nella stessa direzione, cioè di quelli che rileggendo non si
  notano mai. ([#72](https://github.com/Z3roS4n/scriba/issues/72))
- **Se il microfono scelto non c'è più, Scriba lo dice.** Quando la periferica
  scelta nelle impostazioni è stata scollegata, la registrazione ripiega su
  quella predefinita: il core lo segnalava da sempre e l'interfaccia non lo
  ascoltava. Ora compare un avviso col nome del dispositivo che sta davvero
  registrando. ([#73](https://github.com/Z3roS4n/scriba/issues/73))
- **Con l'archivio o la rassegna aperti la finestra si comanda ancora.**
  Sparivano riduci, ingrandisci e chiudi: in una finestra senza cornice quella
  barra è la cornice, e restava solo Alt+F4. Insieme a loro sparivano gli
  avvisi, che non parlano della call guardata ma del core che non è partito o
  del modello che non si è caricato — e uno che arrivava mentre il piano era
  aperto non lo vedeva nessuno.
  ([#74](https://github.com/Z3roS4n/scriba/issues/74))

## 0.6.1 — 8 agosto 2026

### Correzioni

- **L'overlay non finisce più nella condivisione dello schermo.** Chi
  condivideva lo schermo durante una call mostrava a tutti i presenti la
  striscia con la trascrizione dal vivo di quello che si stavano dicendo. Nel
  codice c'era un commento che prometteva il contrario, ma la chiamata che
  serviva non era mai stata scritta. Ora la striscia è esclusa dalla cattura —
  compresa quella degli scatti di Scriba, dove si vuole la slide che sta sotto
  e non la propria trascrizione sopra.
  ([#69](https://github.com/Z3roS4n/scriba/issues/69))

## 0.6.0 — 7 agosto 2026

### Funzioni nuove

- **L'analisi esce nella lingua della call.** Riassunto, punti salienti, task e
  nota di lavoro seguono la lingua scelta in Impostazioni → Trascrizione: una
  riunione in inglese produce un riassunto in inglese, con i titoli delle
  sezioni in inglese. Prima usciva sempre in italiano, e al modello veniva
  detto che la trascrizione era italiana anche quando non lo era — cioè una
  cosa falsa su quello che aveva davanti.
  ([#61](https://github.com/Z3roS4n/scriba/issues/61))

### Correzioni

- **La lingua scelta nelle impostazioni ora vale davvero.** La leggeva solo
  «Rifai la trascrizione»: la registrazione partiva sempre in italiano, quindi
  ogni call risultava italiana nell'archivio e negli export anche quando non lo
  era. Le call registrate prima restano marcate «it», perché così sono state
  registrate. ([#61](https://github.com/Z3roS4n/scriba/issues/61))

## 0.5.1 — 7 agosto 2026

### Correzioni

- **Le frasi che il microfono riprende dall'altoparlante non finiscono più nel
  riassunto come tue.** Il microfono raccoglie sempre un po' di quello che esce
  dalle cuffie, anche a volume basso, e quelle frasi venivano attribuite a chi
  registra: il riassunto faceva dire a te quello che aveva detto l'altro.
  Misurato su sei call registrate, **una riga del microfono su tre** era la
  ripetizione di una riga degli altri — 352 in tutto. Ora vengono riconosciute e
  tenute fuori da riassunto, note di lavoro ed export.

  L'impostazione in Impostazioni → Trascrizione non c'entrava: il criterio è
  preciso — sulle stesse registrazioni segnala il 34,5 % delle righe confrontate
  con quello che l'altoparlante aveva appena detto e lo 0,2 % confrontate con
  quello di dieci minuti prima, dove eco non ce ne può essere. A non funzionare
  era il momento. Una frase degli altri entrava nel filtro solo una volta
  finita, e l'eco sul microfono finisce molto prima: il confronto avveniva con
  qualcosa che non era ancora stato detto. Ora conta anche l'ipotesi in corso, e
  a call finita si ricontrolla tutto.

  Quelle righe **non vengono cancellate**: in cima alla trascrizione compare «N
  righe riprese dall'altoparlante», e aprendolo si vedono, sbiadite ed
  etichettate come riprese invece che come parole tue. Una riga su tre è troppo
  per buttarla via senza lasciare niente da controllare.

  Vale per le call registrate d'ora in poi. Quelle già registrate restano come
  sono: le righe di eco che contengono ci sono davvero, e nessuno torna indietro
  a rivederle da solo.
  ([#59](https://github.com/Z3roS4n/scriba/issues/59))

L'installer resta non firmato: Windows mostra l'avviso di SmartScreen, e con
Smart App Control attivo lo rifiuta del tutto.

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
