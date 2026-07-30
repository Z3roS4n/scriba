# Decisioni di design

> Log delle decisioni prese durante il redesign UI — scope, processo, scelte tecniche.
> Per i gap funzionali (design → nessun backend) vedi [da-implementare.md](da-implementare.md);
> per lo stile vedi [design-system.md](design-system.md).

## D-UI-01 — Scope

Si rivede **tutta** l'interfaccia esistente, che è stata scritta funzionale e mai
progettata: finestra principale, overlay, impostazioni, dialoghi.

Fuori scope per ora: tema chiaro (l'app sta accanto a finestre di riunione, spesso a
schermo condiviso, e un fondo chiaro a tutto schermo dà fastidio) e macOS.

## D-UI-02 — Processo

Il design si fa con Claude Design, a partire dal brief in
[brief-per-claude-design.md](brief-per-claude-design.md). Una schermata alla volta:
si consegna l'handoff (HTML + CSS autonomo, token come variabili, stati alternativi in
copie separate) e si implementa in React fedelmente, sezione per sezione, aggiornando
[roadmap-frontend.md](../roadmap-frontend.md).

Il brief è scritto attorno al contesto d'uso, non all'estetica: l'app viene guardata
mentre si è in riunione, di sfuggita, con lo schermo già occupato. È il vincolo che
decide quasi tutte le scelte.

## D-UI-03 — I comportamenti non si negoziano col design

Alcune cose nell'interfaccia attuale nascono da problemi incontrati sul campo, non da
preferenze. Se il nuovo design le rompe, si rivede il design.

- Il testo provvisorio si distingue da quello definitivo: sta ancora cambiando, e chi
  legge deve saperlo.
- Ogni campo di una task mostra da quale frase della riunione viene. È l'unica difesa
  contro un modello che sbaglia con sicurezza.
- La conferma sul consenso non si salta, nemmeno quando la call è stata riconosciuta
  da sola.
- Quando i dati escono dal computer va detto, anche sull'opzione già in uso.
- L'overlay non ruba il fuoco: durante una call la tastiera serve alla riunione.
- Lo scorrimento automatico si ferma se l'utente sta rileggendo.
- Un'operazione lunga si può abbandonare e ritrovare finita.

## D-UI-04 — Tutte le impostazioni dall'interfaccia

Oggi alcune cose si cambiano solo modificando `settings.json` a mano. Il nuovo design
deve esporre tutto, inclusa l'**installazione dei modelli locali**: elenco, download
con avanzamento, ripresa dopo un'interruzione, verifica di integrità, spazio su disco,
avvio e arresto del modello di analisi, cancellazione.

Sono download da 5 a 17 GB che durano fino a un'ora: vanno progettati come operazioni
lunghe e interrompibili, non come un pulsante che gira.

## D-UI-05 — Due modi d'uso opposti nella stessa applicazione

Durante la call conta la leggibilità periferica e il non dare fastidio; dopo la call
conta la densità di informazione. L'overlay serve il primo caso, la finestra principale
il secondo, e non vanno progettati con lo stesso criterio.

## D-UI-06 — Un modale più largo, solo per le tabelle etichetta + controllo

Il modale del design è 480px. La mappatura di Notion è una tabella di dodici righe
«nome del campo + selettore»: a 480px l'etichetta e il selettore si accavallano, e
accorciare i testi renderebbe la schermata più stretta ma meno comprensibile — che è
il contrario di quello che serve mentre si decide dove finiscono i propri dati.

`Modal` accetta quindi una `larghezza` facoltativa (560px per la mappatura). Non è un
permesso generale: per tutto il resto vale 480px, e allargare un modale per far stare
più roba dentro è il segnale che quella roba andava in una schermata.

## D-UI-07 — Il collegamento a un servizio esterno è una schermata a passi

Notion chiedeva due campi da incollare a mano (token e id del database) in mezzo a una
riga di impostazioni. Un id sbagliato e un'integrazione non condivisa danno lo stesso
errore, quindi chi lo incollava non aveva modo di capire cosa fosse andato storto.

Ora è un modale a passi: token → quale database (elenco di quelli visibili) o creane uno
→ cosa va in quale colonna. Vale come convenzione per i prossimi connettori: l'utente
sceglie da un elenco di cose che esistono, non digita un identificativo.
