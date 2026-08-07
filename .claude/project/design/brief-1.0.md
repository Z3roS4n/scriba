# Brief per Claude Design — Scriba 1.0

> Il prompt qui sotto è **pronto da incollare**, per intero, in una conversazione con
> Claude Design in cui è disponibile il sistema di design **msworks** e a cui è allegato
> questo repository.
>
> Sostituisce [brief-per-claude-design.md](brief-per-claude-design.md), che descrive
> l'app di fine luglio 2026 e da allora è invecchiato: metà delle schermate elencate qui
> in quel brief non c'erano.

---

```
Devi ridisegnare l'interfaccia di Scriba, per intero, applicando il sistema di design
msworks. È il design che farà uscire la versione 1.0.0: dopo verranno solo patch, quindi
questa è la passata in cui le cose si sistemano, non una a cui seguirà una seconda.

Ti allego il repository. Contiene l'applicazione vera, i suoi documenti di progetto e il
design precedente. Alla fine ti dico cosa leggere e cosa invece è vecchio e va ignorato.


═══ COS'È SCRIBA ═══

Un'applicazione desktop Windows (Electron + React, core Python locale) che registra le
call di lavoro, le trascrive mentre si parla, e a call finita ne ricava un riassunto,
i punti salienti e le task — ognuna con le frasi della riunione che la giustificano.

Trascrizione e analisi possono girare interamente sul computer di chi la usa. È una
scelta di prodotto, non un dettaglio tecnico: molte delle schermate qui sotto esistono
per rendere quella scelta governabile (quali modelli hai, quanto spazio occupano, cosa
esce dal tuo computer e cosa no).

CHI LA USA
Una persona sola, sul proprio computer. Nessun account, nessun permesso, nessuna
collaborazione. Non è software di squadra e non deve sembrarlo.

IL CONTESTO D'USO — è la cosa che decide quasi tutto
L'app viene guardata MENTRE si è in call. Lo schermo è già occupato dalla finestra della
riunione, da quello che si sta condividendo, dagli appunti. Chi la usa sta parlando con
qualcuno: legge di sfuggita, non si concentra sull'interfaccia.
Dopo la call la usa con calma, per rivedere le task e leggere il riassunto.

Sono due modi d'uso opposti e vanno progettati come tali: durante la call conta la
leggibilità periferica e il non dare fastidio; dopo conta la densità di informazione.
Non applicare lo stesso criterio a entrambi.


═══ LE DUE COSE CHE TI CHIEDO ═══

▸ 1. Applicare msworks.

msworks è la fonte di verità per il linguaggio visivo: palette, tipografia, scala
spaziale, raggi, elevazione, forma dei controlli, densità.

Comincia dichiarando i token che stai applicando — nome, valore esatto, e a cosa
corrisponde in Scriba. Non arrotondare i colori: se msworks usa un nero desaturato verso
un colore, va copiato com'è.

Dove msworks e i vincoli di Scriba si scontrano, **dillo e proponi**, non scegliere in
silenzio. I vincoli sono più avanti, e sono pochi ma reali (l'app è offline, gira in
Electron, e alcune cose nascono da difetti già incontrati sul campo).

▸ 2. Togliere i rimbalzi verso le impostazioni.

Questa è la parte di prodotto, ed è importante quanto la prima.

Oggi troppe schermate ti fermano e ti mandano altrove. Le impostazioni sono una FINESTRA
SEPARATA: uscire da dove stavi significa perdere il posto, sistemare la cosa, tornare
indietro, ritrovare la call, e riprendere. Casi veri, presi dal codice:

  · L'analisi fallisce perché il modello locale non è avviato. Il pannello mostra due
    pulsanti — «Avvia il modello locale» e «Usa un altro motore» — e **tutti e due non
    fanno altro che aprire le impostazioni**. Il pannello sa qual è il problema e non
    può risolverlo. (ui/renderer/Analisi.tsx)

  · «Rifai la trascrizione» richiede un modello da ~1 GB non ancora scaricato. La
    risposta è una frase: «Impostazioni → Modelli locali (circa 1 GB)». Un'istruzione
    scritta, dove poteva esserci un comando. (ui/renderer/Rifinitura.tsx)

  · La scorciatoia dell'overlay è occupata da un'altra applicazione. Compare un avviso
    con «Cambia scorciatoia», che apre le impostazioni. (ui/renderer/index.tsx)

  · Il filtro che riconosce quando il microfono riprende l'altoparlante ha tre livelli,
    in Impostazioni → Trascrizione. Ma te ne accorgi leggendo una trascrizione sbagliata,
    che è in un'altra finestra.

  · I nomi propri che il modello sbaglia si correggono con un glossario, in Impostazioni
    → Trascrizione. Il momento in cui ti serve è mentre leggi il nome storpiato.

  · Il cliente di una call si attribuisce dall'elenco call; l'anagrafica clienti sta in
    Impostazioni → Clienti.

  · Esporti dalla barra in alto; la cartella, il formato e il collegamento a Notion
    stanno in Impostazioni → Export e → Notion.

  · Microfono e uscita audio si scelgono in Impostazioni → Trascrizione. Il momento in
    cui contano è quando premi Registra.

Il principio che ti chiedo di applicare: **un'impostazione vive dove si vede la sua
conseguenza.** Le impostazioni restano il posto dove c'è tutto e dove si va a cercare,
ma non devono essere l'unico posto dove si può agire.

Da qui una domanda che ti giro perché la risolva tu: le impostazioni devono restare una
finestra separata? Oggi lo sono. Un pannello dentro la finestra principale costerebbe
spazio ma toglierebbe il salto. Valuta e motiva.

Attenzione: non voglio che ogni impostazione compaia ovunque. Un'interfaccia in cui ogni
schermata contiene mezzo pannello di configurazione è peggio del problema. Il criterio è
il momento: si mostra quando è quel momento, non sempre.


═══ LE SUPERFICI DA DISEGNARE ═══

Tre finestre. Nessuna è nuova, tutte vanno rifatte.

──── A. FINESTRA PRINCIPALE (1180×780, ridimensionabile, minimo 820×560)

Oggi: barra in alto, poi tre colonne — elenco call | trascrizione | pannello analisi.
Funziona ma è la disposizione più ovvia possibile. Se hai un'idea migliore, proponila:
non c'è niente da conservare per affezione.

BARRA IN ALTO
  · nome dell'app; stato (avvio del core / carico il modello / pronto / registrazione,
    con pallino rosso / modello non disponibile); cronometro solo in registrazione
  · selettore dello schermo da catturare, quando ce n'è più di uno
  · Screenshot (solo in registrazione), Esporta, Archivio, Impostazioni, Registra/Ferma
  · un'area avvisi che compare quando serve

ELENCO CALL
  Titolo (o «Call #12»), data e ora, durata, cliente, numero di task e quante sono da
  confermare, stato (registrata / analizzata / analisi non riuscita), e quale è in corso.

TRASCRIZIONE — il cuore della finestra
  · righe: minuto (mm:ss), chi ha parlato, testo. Due parlanti: «Io» (microfono) e
    «Altri» (audio del computer). Devono distinguersi senza leggere l'etichetta.
  · il testo compare PROVVISORIO mentre la persona parla e viene sostituito dal
    definitivo a fine frase. Il provvisorio deve essere visibilmente incerto.
  · gli screenshot presi durante la call si intercalano nel punto in cui sono stati presi
  · scorre da sola seguendo il parlato, e si ferma se l'utente scorre indietro
  · una riga può essere evidenziata da fuori: cliccando il minuto di una task si salta lì
  · a diarizzazione fatta compare una striscia «dai un nome alle voci», con le voci
    trovate ancora senza nome
  · RIGHE DI ECO (nuovo): il microfono riprende sempre un po' di quello che esce dalle
    cuffie, e quelle frasi sono le stesse che ha detto l'altro. Vengono riconosciute
    (una riga su tre, misurato) e tenute fuori da riassunto, note ed export, ma NON
    cancellate: in cima compare «N righe riprese dall'altoparlante» e aprendolo si vedono,
    sbiadite, etichettate «ripresa» e mai attribuite a «Io». Questa è la parte che ho
    disegnato peggio: rifalla.

NOTA DI LAVORO (nuovo)
  Durante la call, ogni 5/10/15 minuti, viene scritta una nota che riassume quello che
  si è detto finora. Ogni nota riscrive la precedente incorporandola: quella da mostrare
  è l'ultima, ma le precedenti esistono. Oggi è un pannello accanto alla trascrizione.

PANNELLO ANALISI — tre schede
  1. Riassunto: markdown con titoletti, elenchi, riferimenti tipo [05:00] cliccabili.
  2. Punti salienti: righe «[mm:ss] Etichetta — spiegazione».
  3. Task: la parte più importante, sotto.
  In cima: «Analizza la call» / «Analisi in corso…» / «Rianalizza», e a lavoro finito il
  costo e il modello usato. Più «Rifai la trascrizione» (sotto).

TASK E PROVE — la funzione per cui l'applicazione esiste
  In una riunione vera i dettagli di un impegno sono sparsi: il lavoro si nomina al
  minuto 5, la scadenza si concorda al 32, il responsabile si decide al 48. L'app li
  ricompone. Ma è un modello linguistico a farlo, quindi può sbagliare — e per questo
  ogni campo mostra DA DOVE viene.

  Una task ha: titolo, descrizione (facoltativa), responsabile (può mancare), scadenza
  (una data risolta più le parole con cui è stata detta — a volte solo le seconde),
  priorità (bassa/media/alta/critica o assente), confidenza 0-1, un segno «da confermare»,
  e le prove: per ogni campo, il minuto e la frase esatta.

      [05:00] titolo    «dovremmo preparare i mockup della dashboard»
      [32:00] scadenza  «diciamo entro il quattordici»
      [48:00] chi       «per i mockup se ne occupa Marco»

  La tensione da risolvere: le prove sono ciò che rende una task verificabile invece che
  soltanto plausibile. Ma sono tre o quattro righe per task, e le task sono dieci o
  quindici. Mostrarle sempre rende la lista illeggibile; nasconderle toglie il senso alla
  funzione. Il gesto più frequente, a call finita, è «confermo, confermo, questa no,
  confermo».

  Esiste già una modalità a sé per questa passata (una rassegna a tutta finestra, con la
  trascrizione ferma sulle righe citate). Tienila o sostituiscila, ma il ritmo va servito.

RIFINITURA DELLA TRASCRIZIONE
  A call finita si può ripassare tutto con un modello più preciso ma più lento. Non è
  sempre possibile: se l'audio salvato non corrisponde ai minuti della trascrizione, la
  rifinitura **rinuncia su quella traccia e lo dice**, invece di riscrivere ogni riga con
  il testo di un'altra. Va progettato l'esito per traccia: rifinita / non allineata (con
  il motivo) / assente / vuota. E l'avanzamento, che dura minuti ed è interrompibile.

ARCHIVIO
  Ricerca a testo pieno su tutte le call, con filtri: cliente, senza cliente, intervallo
  di date, stato. È la risposta alla domanda «cosa ci siamo detti con questo cliente
  negli ultimi tre mesi». Oggi è una schermata modesta e merita di meglio.

DIALOGHI E MOMENTI
  · Consenso: prima di registrare si chiede un titolo (facoltativo) e la conferma di aver
    avvisato i partecipanti. La conferma è obbligatoria. Va scritto con attenzione: non
    un fastidio burocratico da spuntare senza leggere, e nemmeno un allarme. È una
    responsabilità reale, enunciata con calma.
  · Call rilevata: l'app si accorge da sola che sei entrato in riunione e propone di
    registrare. Compare in basso a destra, mai al centro. «No grazie» dimentica solo
    quella proposta.
  · Analisi in corso: dura minuti, fino a dieci con il modello locale. Deve essere chiaro
    che si può chiudere e tornare dopo. Quattro fasi reali da mostrare.
  · Errori, oggi su quattro livelli di invadenza: barra in alto (non impedisce niente) ·
    riquadro nel pannello (blocca una funzione) · riquadro prima di cominciare
    (cambierebbe il risultato senza dirlo) · riquadro nel punto in cui si è premuto.
    Nessuno è modale. Casi veri: «il modello di analisi non è raggiungibile», «nessun
    dispositivo di loopback: si registrerebbe solo la tua voce», «la scorciatoia Alt+R è
    già usata da un'altra applicazione», «spazio insufficiente: servono 7 GB, ne restano 3».
  · Database messo da parte: all'avvio l'app verifica il database e, se non è leggibile,
    lo sposta in quarantena e ripristina l'ultimo backup. L'elenco call torna indietro, e
    va detto — con il percorso della cartella, apribile. È un avviso persistente, non un
    messaggio che passa.

──── B. OVERLAY (senza cornice, 460×260, minimo 320×120; variante ridotta minimo 280×72)

La striscia che sta sopra tutte le finestre e mostra la trascrizione mentre si parla.
Si apre e si chiude con una scorciatoia.

  · barra: pallino di stato, cronometro (o il nome dell'app se non registra), Scatta,
    Registra/Ferma, ingrandisci, chiudi
  · le ultime righe di trascrizione. Le più vecchie sfumano, così l'occhio va su quello
    che si sta dicendo adesso
  · stato vuoto quando non registra, che ricorda la scorciatoia
  · una variante ancora più ridotta — una o due righe — per chi vuole il minimo

IL VINCOLO CHE GUIDA TUTTO: questa finestra sta sopra la riunione. Ogni pixel che occupa
è un pixel di qualcos'altro che copre, e ogni movimento che fa ruba attenzione a una
conversazione in corso. Deve farsi leggere con la coda dell'occhio e poi sparire dalla
coscienza.

Nota: sotto l'overlay può esserci qualunque cosa, quindi non usa i token di tema — resta
scuro anche a tema chiaro. Se msworks ha un trattamento per superfici sovrapposte a
contenuto arbitrario, applicalo qui.

──── C. IMPOSTAZIONI (oggi finestra separata — vedi la domanda sopra)

Undici sezioni. Alcune sono grandi quanto una schermata a sé.

  1. MOTORE DI ANALISI — quattro scelte esclusive: modello locale (niente esce dal
     computer, ma una call di un'ora richiede una decina di minuti) · abbonamento Claude
     (nessun costo a consumo, ~3 minuti per un'ora, la trascrizione va ad Anthropic) ·
     API Anthropic · API OpenAI (chiave, si paga a consumo). Per ognuna: se è disponibile
     adesso, e in caso contrario cosa fare. **Quando i dati escono dal computer va detto
     sempre**, anche sull'opzione già scelta.

  2. MODELLI LOCALI — la sezione più impegnativa. Elenco con nome, dimensione (da 1 a
     17 GB), a cosa serve, se è installato. Download con avanzamento (percentuale, GB,
     velocità, tempo rimanente), sospendibile e riprendibile dal punto in cui era anche
     dopo aver chiuso l'app. Verifica di integrità come stato visibile. Spazio libero, e
     l'avviso PRIMA di cominciare. Per il modello di analisi anche avvia/ferma e se è
     acceso. Ed eliminare per liberare spazio.
     Stati: non installato / in download / in verifica / installato / in uso / errore.
     Sono operazioni che durano fino a un'ora: vanno progettate come tali, non come un
     pulsante che gira.

  3. TRASCRIZIONE — lingua · microfono e uscita audio · sensibilità del filtro eco (tre
     livelli) · glossario dei nomi propri (uno per riga, più i clienti dell'anagrafica) e
     quanto essere aggressivi nel correggerli.

  4. RILEVAMENTO CALL — attivo o no · dopo quanti secondi proporre · se proporre soltanto
     o avviare da solo (di default: solo proporre) · una diagnostica che mostra cosa il
     rilevamento sta vedendo adesso.

  5. SCORCIATOIE — overlay e screenshot. Si catturano premendole, non si scrivono. Un
     conflitto va detto subito: Windows rifiuta la registrazione in silenzio, e senza
     segnalarlo l'utente resta a premere un tasto che non fa niente.

  6. ASPETTO — tema chiaro / scuro / come il sistema. Si applica subito e a tutte e tre
     le finestre.

  7. ANALISI — analizzare da solo a fine call o a richiesta · note di lavoro durante la
     call, e ogni quanto.

  8. CLIENTI — anagrafica, con quante call per cliente, archiviazione, eliminazione,
     importazione da CSV.

  9. DATABASE REMOTO — collegamento a un PostgreSQL esterno per sincronizzare le call.
     Prova del collegamento, ispezione di tabelle e colonne, anteprima del DDL **prima**
     di eseguirlo, creazione o collegamento a tabelle esistenti, mappatura delle colonne.

  10. DATI E PRIVACY — dove stanno i file e quanto occupano, con un modo per aprire la
      cartella · cancellare l'audio di una call tenendo la trascrizione · cancellare tutto
      di una call · la versione in uso e il commit da cui viene la build.

  11. EXPORT — cartella e formato predefiniti (markdown, testo, json, «contesto» per un
      modello) · collegamento a Notion, che è già una procedura a passi: token → quale
      database, scelto da un elenco di quelli visibili → cosa va in quale colonna.
      Convenzione da mantenere: **l'utente sceglie da un elenco di cose che esistono, non
      digita un identificativo.**

Ci sono due tipi di impostazione qui dentro e vanno distinti visivamente: quelle che
cambiano una preferenza, e quelle che hanno conseguenze — mandare i dati fuori dal
computer, scaricare 17 GB, cancellare registrazioni.


═══ QUELLO CHE NON SI NEGOZIA ═══

Nascono da difetti incontrati sul campo, non da preferenze. Se il tuo design li rompe, si
rivede il design.

  · Il testo provvisorio si distingue dal definitivo: sta ancora cambiando, e chi legge
    deve saperlo. (Nell'implementazione attuale non è corsivo: il corsivo rallenta la
    lettura periferica proprio quando serve leggere di sfuggita. Trova di meglio se c'è,
    ma sappi perché quella scelta è lì.)
  · Ogni campo di una task mostra da quale frase viene. È l'unica difesa contro un
    modello che sbaglia con sicurezza.
  · La conferma sul consenso non si salta, nemmeno quando la call è stata riconosciuta da
    sola.
  · Quando i dati escono dal computer va detto, anche sull'opzione già in uso.
  · L'overlay non ruba il fuoco quando compare: durante una call la tastiera serve alla
    riunione.
  · Lo scorrimento automatico si sospende se l'utente sta rileggendo, e riparte solo con
    un gesto esplicito.
  · Un'operazione lunga si può abbandonare e ritrovare finita.
  · Una funzione senza supporto dietro si mostra disabilitata e detta, mai con dati finti.


═══ VINCOLI TECNICI ═══

  · Electron con Chromium recente: CSS moderno senza problemi di compatibilità.
  · Tre finestre = tre bundle separati. Un componente condiviso fra finestra principale
    e overlay va bene, ma sono processi diversi: quello che cambia in una non cambia
    nell'altra da sé.
  · Tema chiaro E scuro, più «come il sistema». (Il design precedente era solo scuro: non
    è più vero.) I token stanno in una palette chiara sul `:root` e una scura come
    sovrascritture — se msworks è organizzato diversamente, dimmelo e lo adeguo.
  · L'applicazione è OFFLINE. Niente si scarica a runtime: né font da Google Fonts, né
    icone da CDN, né fogli di stile remoti.
    Ma un font può VIAGGIARE DENTRO il pacchetto: l'installer pesa già 170 MB, un file
    di font non cambia niente. Quindi se msworks ha un carattere suo, usalo e dimmi quali
    file servono — non ripiegare su Segoe UI credendo che sia obbligatorio. Il vincolo è
    la rete, non il font.
  · Icone: SVG inline. Se msworks usa una libreria, dammi la tabella di mappatura completa
    invece di lasciare che ogni schermata scelga da sé.
  · NESSUN controllo di form nativo: su Windows `<select>`, checkbox e `<progress>`
    ignorano il tema dell'app e aprono popup di sistema chiari su un'app scura. Tutto ciò
    che sembra un controllo va costruito.
  · Animazioni sobrie. Durante una call un movimento sul bordo dello schermo attira
    l'occhio e distrae da quello che si sta dicendo.
  · Sotto certe larghezze qualcosa deve cedere. Oggi: sotto 1100 px sparisce il pannello
    analisi, sotto 900 px anche l'elenco call; la trascrizione non sparisce mai. Rivedi le
    soglie se il tuo impianto ne vuole altre, ma la regola «la trascrizione resta» tienila.

TONO
Italiano, asciutto, senza gergo. L'app dice cosa succede e cosa fare, non «Operazione
completata con successo». Niente esclamazioni, niente emoji. I testi che vedi nel codice
sono stati scritti con cura: se ne cambi uno, cambialo perché è meglio, non per riempire
un riquadro.


═══ COSA LEGGERE NEL REPOSITORY ═══

DA LEGGERE
  · ui/renderer/                        l'interfaccia attuale, tutta
  · ui/renderer/tokens.css, app.css     i token e i componenti di oggi
  · .claude/project/design/handoff/     il design precedente: HTML+CSS autonomo per ogni
                                        schermata e stato, più comportamento.md, che
                                        spiega PERCHÉ ogni regola è lì. Leggi almeno
                                        quello: è la memoria dei problemi già incontrati.
  · .claude/project/design/decisions.md  le decisioni di design prese finora (D-UI-01…07)
  · .claude/project/05-api-endpoints.md  cosa il core sa fare davvero: è il confine fra
                                        una schermata progettabile e una da inventare
  · .claude/project/02-tradeoffs.md      le decisioni di prodotto, se ti serve il perché
  · CHANGELOG.it.md                      cosa è cambiato di recente e cosa non funziona

DA IGNORARE
  · .claude/project/design/brief-per-claude-design.md — è il brief di fine luglio.
    Descrive un'app senza note di lavoro, senza rifinitura, senza archivio, senza clienti,
    senza database remoto, senza Notion, senza tema chiaro. Se lo leggi ti fai un'idea
    sbagliata di cosa c'è.
  · .claude/project/design/design-system.md — è un modello mai compilato. Sarà il tuo
    risultato a riempirlo, non il contrario.
  · ui/scripts/anteprima/ — ponteggio di sviluppo, non fa parte del prodotto.


═══ COME VOGLIO L'HANDOFF ═══

Per ogni schermata, quando l'abbiamo decisa:

  · HTML + CSS autonomo e funzionante, con dati finti realistici — italiani, plausibili,
    della lunghezza vera (una frase di trascrizione non è «Lorem ipsum», è lunga trenta
    parole e ogni tanto finisce a metà)
  · i token come variabili CSS, per entrambi i temi
  · gli stati alternativi in FILE SEPARATI, non descritti a parole
  · le note di comportamento che il codice deve rispettare — nel formato di
    handoff/comportamento.md, che è la parte del lavoro precedente che è servita di più
  · niente framework: CSS puro. All'integrazione in React ci penso io.

E, alla fine di tutto, il design-system.md compilato: palette, tipografia, forma,
mappatura delle icone, convenzioni di componente. È il file che verrà letto da chi
implementerà le patch dopo la 1.0, quando questa conversazione non ci sarà più.


═══ COME PROCEDIAMO ═══

Non disegnare ancora.

Prima dimmi: cosa hai capito, cosa manca, e cosa in msworks non si applica bene a
un'applicazione di questo tipo. Poi propone**mi** l'impianto della finestra principale —
a parole e con uno schema, non ancora in HTML — insieme alla tua risposta sulle
impostazioni: finestra separata o no, e dove finiscono le impostazioni che oggi
costringono a uscire.

Da lì andiamo una schermata alla volta.
```

---

## Note per chi consegna il brief (non fanno parte del prompt)

- **msworks non l'ho visto.** Il prompt gli chiede di dichiarare i token che applica e di
  segnalare i conflitti invece di risolverli in silenzio: è l'unico modo onesto di
  scrivere un brief attorno a un sistema di design che chi lo scrive non ha davanti.
- **Il vincolo sui font era più stretto del necessario.** Il brief precedente diceva
  «font di sistema, l'app è offline». Vero il divieto di scaricarli a runtime, falso che
  non se ne possano spedire: l'installer pesa già 170 MB. Corretto qui, perché altrimenti
  la tipografia di msworks verrebbe buttata via per un vincolo che non esiste.
- **La domanda sulle impostazioni è lasciata aperta di proposito.** È la decisione di
  impianto che più cambia il risultato, e va presa guardando il design, non prima.
- **Una schermata alla volta.** Il brief chiede di non disegnare subito: una conversazione
  che parte a produrre HTML al primo messaggio produce dodici schermate coerenti fra loro
  e sbagliate insieme.
