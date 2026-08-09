# Scriba — handoff di design

Sistema msworks applicato a un'applicazione desktop. CSS puro, nessun
framework, nessun controllo di form nativo, nessun font di rete.

Comincia da **`index.html`**: indice visuale con tutte le schermate, i file e
le deviazioni dichiarate.

## Come leggerlo

| File | Cosa contiene |
|---|---|
| `tokens.css` | Palette msworks esatta, le aggiunte di Scriba dichiarate una per una col motivo, tema chiaro e scuro, i valori fissi dell'overlay |
| `app.css` | Tutti i componenti. È lo stesso file che passa in React |
| `comportamento.md` | 50 regole che il codice deve rispettare, più cosa serve dal core |
| `stringhe.md` | `chiave · italiano · inglese`, con la colonna che segnala le etichette di valori salvati |

## Le schermate

| Pagina | Stato |
|---|---|
| `principale-analizzata.html` | Call analizzata, pannello task aperto sulle prove |
| `principale-analizzata-en.html` | La stessa con l'interfaccia in inglese e il contenuto in italiano |
| `principale-analizzata-scuro.html` | La stessa a tema scuro: cambia solo `data-theme="dark"` sull'elemento radice |
| `principale-registrazione.html` | Registrazione in corso, colonna destra in configurazione «durante» |
| `rassegna.html` | Rassegna task a tutta finestra |
| `impostazioni.html` | Motore di analisi e Modelli locali, le due sezioni difficili |
| `archivio.html` | Ricerca dentro il parlato, raggruppata per cliente |
| `overlay-e-dialoghi.html` | Overlay in tre stati, consenso, call rilevata, i quattro livelli di errore |

Ogni pagina si apre da sola in un browser e carica `tokens.css` + `app.css`.
In `screenshots/` c'è un PNG per schermata, catturato a 2× sulla finestra
intera (2528px): a quella scala le linee da 1px e le etichette da 10,5px —
su cui il sistema si regge — restano leggibili.

Montserrat arriva da Google Fonts **solo in queste anteprime**, perché il
pacchetto giri anche fuori dal progetto. Nell'applicazione viaggia dentro
l'installer come quattro `.woff2` (400/700/800/900, subset latin, circa 120 KB
in tutto) in `ui/renderer/font/`: Scriba funziona offline e un font di rete
sarebbe una schermata che cambia aspetto a seconda della connessione.

## Le tre deviazioni da msworks, dichiarate

**Il rosso non è il colore della CTA.** msworks usa il rosso per l'azione
primaria; qui è riservato a cinque cose: registrazione in corso, dati che
escono dal computer, azione distruttiva, guasto che blocca, priorità critica.
L'azione primaria è Ink pieno. Se «Analizza la call» fosse rossa, il pallino
della registrazione smetterebbe di significare qualcosa.

**Il tema scuro esiste.** msworks dice di non averlo, ma ce l'ha già e non lo
sa: le sue sezioni su fondo nero hanno testo `#B9B9B6`, label `#9A9A98`, bordi
`#3A3A38`. Il tema scuro di Scriba è quella terna promossa da trattamento di
sezione a trattamento di pagina. Una sola aggiunta necessaria: `#C60001` su
`#111111` fa 3,4:1, quindi serve un rosso schiarito, dichiarato come unica
eccezione alla palette.

**Due scale tipografiche.** La regola dei 17px nasce dal testo corrente letto
di seguito, e nella finestra quel testo è la trascrizione: 15px a riposo, 16px
in registrazione — sale, non scende. Controlli, metadati e celle hanno una
scala d'interfaccia a parte, 10,5-14px.

## Componenti che il design system non ha

Il DS di msworks non ha Dialog, Tooltip, Toast, Tabs, Table, Progress, perché
un sito non ne ha bisogno. Sono derivati nella sua grammatica, non presi
altrove: schede con filetto Ink da 2px (mai pillole), progress come traccia
1px più riempimento Ink senza raggio, popover come piano bordato, keycap come
riquadro 2px, chevron come due bordi ruotati di 45°.

Le superfici che galleggiano non hanno ombra: il contenuto sotto si scurisce
del 12% e la superficie resta bordata e piatta.
