# Brief per Claude Design — Scriba

Prompt pronti da incollare. Il **Prompt 0** va dato per primo e stabilisce il contesto;
gli altri si danno uno alla volta, uno per schermata.

Alla fine di ogni schermata chiedi l'handoff (HTML/CSS o specifiche di componenti +
token) e passalo a Claude Code per l'implementazione.

---

## Prompt 0 — Contesto (dare per primo)

```
Sto progettando l'interfaccia di Scriba, un'applicazione desktop Windows (Electron +
React) che registra le call di lavoro, le trascrive in tempo reale e poi ne estrae
riassunto, punti salienti e task.

CHI LA USA
Una persona sola, sul proprio computer, mentre è in riunione. Non è uno strumento di
squadra: non ci sono account, permessi o collaborazione.

IL CONTESTO D'USO — è la cosa che conta di più
L'app viene guardata MENTRE si è in una call. Lo schermo è già occupato dalla finestra
della riunione, da quello che si sta condividendo, dagli appunti. Chi la usa sta
parlando con qualcuno: legge di sfuggita, non si concentra sull'interfaccia. Dopo la
call invece la usa con calma, per rivedere le task e leggere il riassunto.

Sono due modi d'uso opposti e vanno progettati come tali: durante la call conta la
leggibilità periferica e il non dare fastidio; dopo conta la densità di informazione.

VINCOLI TECNICI
- Electron con Chromium recente: CSS moderno disponibile senza limiti di compatibilità.
- Solo tema scuro, per ora. L'app sta accanto a finestre di riunione, spesso a schermo
  condiviso, e un fondo chiaro a tutto schermo dà fastidio.
- I controlli di form devono essere sempre stilizzati, mai quelli nativi: su Windows
  ignorano il tema scuro e stonano.
- Font di sistema (Segoe UI): l'app è offline, non può caricare font da rete.
- Nessuna icona da libreria esterna: o SVG inline o caratteri. Stessa ragione.
- Le animazioni devono essere sobrie: durante una call un movimento sul bordo dello
  schermo attira l'occhio e distrae da quello che si sta dicendo.

TONO
Italiano, asciutto, senza gergo tecnico. L'app dice cosa succede e cosa fare, non
"Operazione completata con successo". Niente esclamazioni, niente emoji.

Nei prossimi messaggi ti descriverò una schermata alla volta con tutte le sue
funzioni e i suoi stati. Per ognuna voglio: struttura, gerarchia, spaziature, e i
token di colore/tipografia. Chiedimi pure quello che non ti torna prima di disegnare.
```

---

## Prompt 1 — Finestra principale

```
Prima schermata: la finestra principale (1180x780 di default, ridimensionabile,
minimo 820x560).

STRUTTURA ATTUALE — da rivedere, non da conservare
Barra in alto, poi tre colonne: elenco call (240px) | trascrizione (flessibile) |
pannello analisi (360px o 34%). Sotto i 1100px di larghezza il pannello analisi
sparisce. Questa divisione funziona ma è banale: se hai un'idea migliore, proponila.

BARRA IN ALTO
- Nome dell'app.
- Stato: pallino + testo. Stati possibili: "Avvio del core...", "Carico il modello...",
  "Pronto", "Registrazione" (pallino rosso pulsante), "Modello non disponibile".
- Cronometro, visibile solo mentre registra (mm:ss).
- Pulsanti: Screenshot (attivo solo in registrazione), Esporta, Impostazioni,
  Registra / Ferma.
- Un'area avvisi che compare quando serve (es. "La scorciatoia Alt+R è già usata da
  un'altra applicazione").

ELENCO CALL
Ogni voce: titolo (o "Call #12" se senza titolo), data e ora, durata, e un'indicazione
se è quella in corso. Ordinate dalla più recente. Serve anche uno stato per call:
registrata / analizzata / analisi non riuscita.

TRASCRIZIONE — il cuore della schermata
Righe con: minuto (mm:ss), chi ha parlato, testo.
- Due parlanti: "Io" (dal microfono) e "Altri" (dall'audio del computer). Devono
  distinguersi a colpo d'occhio senza dover leggere l'etichetta.
- Il testo compare PROVVISORIO mentre la persona parla e viene sostituito da quello
  definitivo quando finisce la frase. Il provvisorio deve essere visibilmente
  incerto: chi legge deve sapere di non poterci fare affidamento. Oggi è grigio
  corsivo — trova qualcosa di meglio se c'è.
- Gli screenshot catturati durante la call si intercalano nella trascrizione nel punto
  in cui sono stati presi.
- Scorre da sola seguendo il parlato, ma si ferma se l'utente scorre indietro a
  rileggere.
- Una riga può essere evidenziata da fuori: cliccando il minuto di una task si salta
  lì e la riga lampeggia.

PANNELLO ANALISI (a destra, tre schede)
1. Riassunto: markdown con titoletti, elenchi puntati, riferimenti tipo [05:00].
2. Punti salienti: righe "[mm:ss] **Etichetta** — spiegazione".
3. Task: la parte più importante, la descrivo nel prompt successivo.
In cima: un pulsante "Analizza la call" / "Analisi in corso..." / "Rianalizza", e a
lavoro finito il costo e il modello usato.

STATI DA PROGETTARE
- Prima apertura: nessuna call registrata.
- Call selezionata ma non ancora analizzata.
- Analisi in corso (dura minuti: deve essere chiaro che si può chiudere e tornare).
- Analisi fallita, con il motivo e cosa fare.
- Registrazione in corso senza che nessuno abbia ancora parlato.
```

---

## Prompt 2 — Le task e le loro prove

```
La scheda "Task" del pannello analisi. È la funzione per cui l'applicazione esiste, e
merita un trattamento a sé.

IL PROBLEMA CHE RISOLVE
In una riunione vera i dettagli di un impegno sono sparsi: il lavoro si nomina al
minuto 5, la scadenza si concorda al 32, il responsabile si decide al 48. L'app li
ricompone in un'unica task. Ma è un modello linguistico a farlo, quindi può sbagliare:
per questo ogni campo mostra DA DOVE viene.

COSA CONTIENE UNA TASK
- Titolo.
- Descrizione (facoltativa).
- Responsabile (può mancare, o essere "altri" quando non si sa il nome).
- Scadenza: una data risolta (2026-08-14) più le parole con cui è stata detta
  ("entro il quattordici"). A volte c'è solo la seconda.
- Priorità: bassa / media / alta / critica, oppure assente.
- Confidenza: un numero da 0 a 1.
- Un segno "da confermare" quando il modello non è sicuro.
- Le PROVE: per ogni campo, il minuto e la frase esatta detta in riunione.
  Esempio reale:
    [05:00] titolo    «dovremmo preparare i mockup della dashboard»
    [32:00] scadenza  «diciamo entro il quattordici»
    [48:00] chi       «per i mockup se ne occupa Marco»

COSA DEVE POTER FARE L'UTENTE
- Leggere la task e capire in due secondi se è giusta.
- Cliccare il minuto di una prova e saltare a quel punto della trascrizione.
- Confermare, modificare o scartare la task.
- Vedere subito quali task sono da confermare e quali no.

LA TENSIONE DA RISOLVERE
Le prove sono ciò che rende una task verificabile invece che solo plausibile: senza,
resta l'affermazione di un modello. Ma sono anche tante — tre o quattro righe per
task, e le task sono dieci o quindici. Mostrarle tutte sempre rende la lista
illeggibile; nasconderle del tutto toglie il senso alla funzione.

Progetta questo equilibrio. Considera che l'utente le rilegge a call finita, con
calma, e che il gesto più frequente è "confermo, confermo, questa no, confermo".
```

---

## Prompt 3 — Overlay (la striscia durante la call)

```
Seconda finestra: un overlay che sta sopra tutte le altre e mostra la trascrizione
mentre si parla. Si apre e si chiude con Alt+R.

CARATTERISTICHE
- Senza cornice, sfondo semitrasparente scuro con sfocatura.
- Sempre in primo piano, anche sopra applicazioni a schermo intero.
- Trascinabile da qualunque punto della barra superiore.
- Ridimensionabile. Default 460x260, minimo 320x120.
- Ricorda dove è stata messa.

CONTENUTO
- Barra: pallino di stato, cronometro (o il nome dell'app se non registra), pulsanti
  Scatta / Registra o Ferma / ingrandisci / chiudi.
- Le ultime 6 righe di trascrizione, con chi ha parlato e il testo. Le più vecchie
  sfumano, così l'occhio va su quello che si sta dicendo adesso.
- Stato vuoto quando non registra, che ricorda la scorciatoia.

IL VINCOLO CHE GUIDA TUTTO
Questa finestra sta sopra la riunione. Ogni pixel che occupa è un pixel di qualcos'altro
che copre, e ogni movimento che fa ruba attenzione a una conversazione in corso. Deve
farsi leggere con la coda dell'occhio e poi sparire dalla coscienza.

Da qui: poche righe, niente animazioni vistose, contrasto sufficiente a leggere su
qualunque sfondo ci si trovi sotto, e comandi che non si premono per sbaglio mentre si
sposta la finestra.

Progetta anche una variante ancora più ridotta — solo una o due righe — per chi vuole
il minimo indispensabile.
```

---

## Prompt 4 — Impostazioni

```
La schermata delle impostazioni. Deve contenere TUTTO: oggi alcune cose si cambiano
solo modificando un file, e non va bene.

Valuta tu se farne un dialogo a sezioni, una finestra a sé con barra laterale, o
altro. Le sezioni sono queste.

1. MOTORE DI ANALISI
Quattro scelte, mutuamente esclusive:
- Modello locale: non esce nulla dal computer, ma è lento (una call di un'ora richiede
  una decina di minuti).
- Abbonamento Claude: usa un abbonamento già attivo, nessun costo a consumo, circa tre
  minuti per un'ora di call. La trascrizione viene inviata ad Anthropic.
- API Anthropic / API OpenAI: richiedono una chiave, si paga a consumo.
Per ognuna: se è disponibile adesso o no, e in caso contrario cosa fare per renderla
tale. Quando i dati escono dal computer va detto sempre, anche sull'opzione già
scelta: è la conseguenza che si dimentica più facilmente.

2. MODELLI LOCALI — la parte nuova, progettala con cura
L'utente deve poter installare i modelli dall'interfaccia, senza toccare un terminale.
- Elenco dei modelli disponibili con: nome, dimensione del file (da 5 a 17 GB),
  a cosa serve (trascrizione o analisi), se è già installato.
- Per quelli non installati: un pulsante per scaricarli, con avanzamento (percentuale,
  GB scaricati su totali, velocità, tempo rimanente). Un download può durare un'ora.
- Deve essere interrompibile e riprendibile: si riprende da dove si era fermato.
- Verifica di integrità a fine download, con esito visibile.
- Spazio libero su disco, e un avviso se non basta PRIMA di iniziare.
- Per il modello di analisi serve anche avviarlo e fermarlo, e vedere se è acceso.
- Un modo per cancellare un modello che non si usa più e liberare spazio.
Stati: non installato / in download / in verifica / installato / in uso / errore.

3. TRASCRIZIONE
- Lingua principale.
- Quale microfono e quale uscita audio usare (elenchi di dispositivi).
- Sensibilità del filtro che riconosce quando il microfono riprende l'altoparlante.

4. RILEVAMENTO AUTOMATICO DELLE CALL
- Attivo o no.
- Dopo quanti secondi proporre di registrare.
- Se proporre soltanto o avviare da solo (di default: solo proporre).

5. SCORCIATOIE
- Mostra/nascondi overlay (default Alt+R).
- Screenshot (default Ctrl+Shift+S).
Devono essere modificabili, e va detto subito se una combinazione è già presa da
un'altra applicazione: Windows la rifiuta in silenzio, e senza segnalarlo l'utente
resta a premere un tasto che non fa niente. Ideale: si preme la combinazione e viene
catturata, invece di scriverla a mano.

6. ANALISI
- Analizzare da solo a fine call, oppure a richiesta.
- Note incrementali durante la call.

7. DATI E PRIVACY
- Dove stanno i file (database, audio, screenshot), con un modo per aprire la cartella.
- Quanto spazio occupano.
- Cancellare l'audio di una call tenendo la trascrizione.
- Cancellare tutto di una call.

8. EXPORT
- Cartella predefinita.
- Collegamento a Notion o a un servizio esterno (non ancora implementato: progetta lo
  spazio, marcandolo come non disponibile).

Ci sono due tipi di impostazione qui dentro e vanno distinti visivamente: quelle che
cambiano solo una preferenza, e quelle che hanno conseguenze — mandare i dati fuori
dal computer, scaricare 17 GB, cancellare registrazioni.
```

---

## Prompt 5 — Dialoghi e momenti

```
Ultimi pezzi: i momenti in cui l'app interrompe l'utente. Sono pochi di proposito.

1. AVVIO REGISTRAZIONE
Chiede un titolo (facoltativo) e la conferma di aver avvisato i partecipanti.
La conferma è obbligatoria per procedere.

Il testo dice che registrare gli altri significa trattare i loro dati personali, e che
la spunta viene annotata nella sessione ma non sostituisce l'averglielo detto.

Va progettato con attenzione: non deve sembrare un fastidio burocratico da spuntare
senza leggere, ma nemmeno un avvertimento allarmante. È una responsabilità reale
enunciata con calma.

2. CALL RILEVATA
L'app si accorge da sola che si è entrati in una riunione e propone di registrare.
Compare in basso a destra, non al centro: arriva mentre si sta entrando in call, e una
finestra modale in quel momento è un'interruzione.
Contenuto: "Sembra che tu sia in una call su Zoom", la conseguenza (include l'audio
degli altri), e due scelte: Registra / No grazie.
"No grazie" dimentica solo questa proposta: alla riunione dopo la domanda torna.

3. ANALISI IN CORSO
Dura minuti — fino a dieci con il modello locale. Deve essere chiaro che si può
chiudere la finestra e tornare dopo, che il lavoro continua. Se possibile, mostrare a
che punto è (riassunto, punti salienti, estrazione task, unione).

4. ERRORI
Alcuni casi reali:
- "Il modello di analisi non è raggiungibile" — con cosa fare per avviarlo.
- "Nessun dispositivo di loopback: si registrerebbe solo la tua voce."
- "La scorciatoia Alt+R è già usata da un'altra applicazione."
- "Spazio insufficiente per scaricare il modello: servono 7 GB, ne restano 3."
Ogni errore deve dire cosa è successo e cosa si può fare. Progetta il posto dove
compaiono e quanto sono invadenti a seconda della gravità.
```

---

## Cosa chiedere come handoff

Alla fine di ogni schermata:

```
Dammi l'handoff per lo sviluppatore:
- HTML + CSS della schermata, autonomo e funzionante, con dati finti realistici
- i token (colori, tipografia, spaziature, raggi, ombre) come variabili CSS
- gli stati alternativi in copie separate, non descritti a parole
- le note sul comportamento che il codice deve rispettare
Niente framework: CSS puro. Lo integro io in React.
```

---

## Da non perdere nella revisione

Comportamenti che nascono da problemi già incontrati sul campo. Se il nuovo design li
rompe, va rivisto il design, non il comportamento.

- **Il testo provvisorio si distingue da quello definitivo.** Sta ancora cambiando.
- **Ogni campo di una task mostra da dove viene.** È l'unica difesa contro un modello
  che sbaglia con sicurezza.
- **La conferma sul consenso non si salta**, nemmeno quando la call è stata rilevata
  automaticamente.
- **Quando i dati escono dal computer va detto**, anche sull'opzione già in uso.
- **L'overlay non ruba il fuoco** quando compare: durante una call la tastiera serve
  alla riunione.
- **Lo scorrimento automatico si ferma** se l'utente sta rileggendo.
- **Un'operazione lunga si può abbandonare** e ritrovare finita.
