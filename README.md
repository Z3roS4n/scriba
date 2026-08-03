# Scriba

Applicazione desktop per Windows che registra le call di lavoro, le trascrive mentre
parli e ne ricava riassunto, punti salienti e task — con la trascrizione e, se lo
scegli, anche l'analisi eseguite in locale sulla tua macchina.

È per chi fa riunioni di lavoro (call, colloqui, sessioni di allineamento) e vuole un
verbale utilizzabile senza affidare l'audio a un servizio in cloud per farlo.

> **Stato: in sviluppo.** Registrazione, trascrizione live, interfaccia, riassunto,
> punti salienti ed estrazione task funzionano. Vedi "Limiti noti" più sotto per cosa
> non è ancora coperto o non è mai stato misurato sul serio.

## Come si installa

Non esiste ancora un installer già pubblicato: te lo costruisci con un comando solo, e
il risultato è un `.exe` che si lancia come un programma qualunque — non un progetto
da tenere aperto in un terminale.

Per costruirlo serve avere installato:

- [Node.js](https://nodejs.org/) (per l'interfaccia Electron e per `electron-builder`)
- Python 3.12
- [uv](https://docs.astral.sh/uv/), che gestisce l'ambiente Python del core e può
  installare Python 3.12 da solo se non ce l'hai

```bash
# Ambiente Python del core. requirements-dev.txt include anche PyInstaller,
# che serve a impacchettare il core: senza, `npm run dist` si ferma a metà.
uv venv core/.venv --python 3.12
uv pip install --python core/.venv/Scripts/python.exe -r core/requirements-dev.txt

# Interfaccia + eseguibile del core + installer NSIS
cd ui
npm install
npm run dist
```

Per far girare Scriba dai sorgenti, senza costruire l'installer, basta
`core/requirements.txt`.

`npm run dist` fa tre cose in sequenza: compila l'interfaccia Electron, impacchetta il
core Python con PyInstaller (usando `core/.venv` come interprete — deve esserci già,
con le dipendenze sopra installate), e infine costruisce l'installer NSIS con
electron-builder. Il risultato è `ui/release/Scriba Setup <versione>.exe`, un
eseguibile Windows autonomo: **non richiede Python o Node sulla macchina su cui lo
installi**, solo su quella su cui lo costruisci.

L'installer non è firmato (vedi "Limiti noti"): Windows mostrerà l'avviso di
SmartScreen alla prima apertura.

In alternativa, per sviluppare o provare senza costruire l'installer:

```bash
cd ui
npm install
npm start
```

Il modello di trascrizione (~600 MB) si scarica al primo avvio; i modelli di analisi
locale (da 5,5 a 17 GB) si scaricano dalle Impostazioni, quando decidi di usarli.

## Come si usa

**Registrazione.** Scriba resta nell'area di notifica. Quando rileva che sei entrato
in una call (Zoom, Teams, Meet nel browser o altro: il rilevamento guarda chi sta
usando il microfono, non il nome del programma) propone di registrare; puoi anche
avviarla a mano. Il microfono e l'audio di sistema vengono catturati e trascritti su
due tracce separate — "io" e "gli altri" — senza bisogno di diarizzazione.

**Durante la call.** Una striscia overlay mostra la trascrizione dal vivo (scorciatoia
predefinita <kbd>Alt</kbd>+<kbd>R</kbd> per mostrarla/nasconderla).
<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> cattura uno screenshot e lo aggancia
all'istante della call in cui l'hai preso: il testo che contiene (letto via OCR,
in locale) entra nel contesto dell'analisi insieme a quello che si diceva in quel
momento. Entrambe le scorciatoie si possono cambiare dalle Impostazioni. Con più
monitor collegati scegli quale catturare: un pulsante per schermo, nella barra e
sulla striscia, senza uscire dalla riunione per cercare un menu.

**Dopo la call.** L'analisi produce: un riassunto strutturato (in breve, contesto,
decisioni prese, punti aperti, prossimi passi), i punti salienti con riferimento al
minuto, e le task — estratte in due passaggi (si raccolgono i frammenti sparsi nella
conversazione, poi si ricompongono in impegni completi con responsabile, scadenza e
priorità), ciascuna con un riferimento verificabile al punto della trascrizione da cui
viene. Puoi rivedere, correggere ed esportare in Markdown, testo semplice, JSON, verso
Notion (una pagina per call, una riga per task) o verso un endpoint HTTP generico.

**Da dare a un'altra IA.** C'è un export fatto apposta per essere incollato in un
modello: ogni affermazione porta **accanto** la citazione da cui viene, con il minuto,
invece di un riferimento da incrociare — e gli impegni che una fonte non ce l'hanno lo
dicono, invece di sembrare verificati come gli altri. Dall'archivio se ne esportano
anche molte insieme («tutto quello che ci siamo detti con questo cliente»), con il peso
in token mostrato prima, perché il contesto di un modello è finito e la trascrizione
integrale è una spunta.

**L'archivio.** Dopo qualche mese la domanda non è più «cos'ho fatto ieri» ma «cosa ci
siamo detti con questo cliente». C'è una pagina che risponde a quella: cerca dentro
quello che è stato **detto**, non solo nei titoli, e filtra per cliente, periodo e
stato. I clienti sono un'anagrafica vera — si scrivono a mano o si carica un CSV — e la
call si attribuisce da lì, riga per riga, che è il posto in cui hai davanti tutte quelle
ancora senza.

**Un database tuo, se lo vuoi.** Le call vivono in uno SQLite su questo computer, e
quel computer si rompe. Dalle Impostazioni si collega un PostgreSQL qualunque —
Supabase o altro — scegliendo lo schema, quali dati mandare e se le tabelle le deve
creare Scriba o mapparle su quelle che hai già. Risincronizzare non duplica niente:
ogni riga si riconosce dal suo identificativo. Vedi anche «Cosa esce dal computer».

**Notion, col tuo database.** Se hai già un database di impegni, colleghi quello e dici
tu quale dato di Scriba va in quale colonna — scadenza, assegnatario, priorità, la
citazione con il minuto: quello che ti serve, dove ti serve. Se non ce l'hai, Scriba te
lo crea, scegliendo tu quali campi ti interessano e quali no.

**Motore di analisi.** Dalle Impostazioni scegli se usare un modello locale (scaricato
e fatto girare sulla tua macchina tramite `llama-server`), la CLI di Claude Code se
hai un abbonamento, oppure le API di Anthropic o OpenAI con una tua chiave.

**Chiaro o scuro.** In Impostazioni → Aspetto, con l'opzione «come il sistema» che segue
Windows anche quando cambia da solo al tramonto. Vale subito, senza riavviare. La
striscia di trascrizione resta scura in ogni caso: sta sopra la finestra della riunione,
e lì il bianco abbaglia.

## Cosa esce dal computer e cosa no

Questo è il punto su cui vale la pena essere espliciti, non vago.

- **La trascrizione è sempre locale.** L'audio non lascia mai la macchina: il modello
  di trascrizione gira su questo computer, sempre, qualunque cosa tu scelga per
  l'analisi.
- **L'analisi (riassunto, punti salienti, estrazione task) può essere locale o via
  API**, a tua scelta. Locale (modello scaricato in Impostazioni) è il default.
- **Se scegli un'API esterna per l'analisi (Anthropic, OpenAI, o la CLI di Claude
  Code), il testo della trascrizione lascia la macchina**: viene mandato a quel
  servizio per generare riassunto, punti salienti e task. Non è l'audio a uscire, ma
  è comunque tutto ciò che è stato detto nella call, in chiaro. Lo stesso vale per il
  testo estratto via OCR dagli screenshot, se ne hai presi.
- L'export verso Notion o verso un endpoint HTTP è un'azione esplicita tua: scriba non
  manda niente altrove di sua iniziativa.
- **Se colleghi un database PostgreSQL remoto, i dati che scegli escono da questo
  computer** — e se fra quelli includi la trascrizione, esce tutto quello che è stato
  detto nelle tue call. Non è acceso di default: va collegato a mano dalle
  Impostazioni, e lì si sceglie tabella per tabella cosa mandare. L'indirizzo di
  connessione contiene una password, e per questo viene cifrato con la chiave del tuo
  account Windows invece di stare in chiaro accanto al database.

## Cosa succede se qualcosa va storto

Una call registrata è un'ora di lavoro che non si ripete: qui è scritto cosa fa Scriba
per non fartela perdere, perché è successo davvero durante lo sviluppo.

- **Il lavoro di una call finisce nel database mentre la registri**, non solo quando la
  fermi: ogni due minuti, più a fine registrazione e a fine analisi. SQLite scrive prima
  in un file di appoggio (il WAL) e lo travasa nel database solo ogni tanto, per conto
  suo: se l'applicazione muore prima, quel travaso non è mai avvenuto. Al peggio ora si
  perdono due minuti di trascrizione, non l'intera riunione.
- **Un database che non si legge non viene usato.** All'avvio Scriba lo controlla; se non
  passa, lo mette da parte insieme al suo WAL — in una cartella `danneggiato-<data>`
  accanto ai dati — e riparte dal backup più recente. Continuare a scriverci dentro
  renderebbe irrecuperabile quello che ancora si poteva salvare. **Quei file non vengono
  mai cancellati**, e l'applicazione lo dice con un avviso che porta alla cartella.
- **I backup li fa da sola**, all'avvio e a fine registrazione, tenendo gli ultimi cinque
  in `backup/` accanto al database. Sono copie compatte in un file solo: un backup non
  può soffrire dello stesso disallineamento che ha causato il guasto.
- **L'audio resta comunque su disco** in `audio/sessione-<n>/`, in due tracce separate.
  È l'ultima rete: finché ci sono quei file, la call non è perduta.

## Registrare le call e la legge

Scriba registra anche l'audio degli **altri partecipanti** alla call, non solo il tuo.
In Italia e nell'Unione Europea questo significa trattare i loro dati personali, e le
regole cambiano da paese a paese su cosa serve per farlo lecitamente.

L'applicazione chiede una conferma esplicita a ogni avvio della registrazione e la
annota nella sessione (data e ora della conferma restano nel database). **Questa
conferma non sostituisce l'avviso agli altri partecipanti.** Dirglielo prima di
registrare — non dopo, non a cose fatte — resta una tua responsabilità, non
dell'applicazione.

## Requisiti reali

- Windows 10/11 (la cattura audio a due tracce usa WASAPI; non gira su altri sistemi)
- ~1 GB di spazio per il modello di trascrizione, da 5,5 a 17 GB in più se usi anche
  un modello di analisi locale
- Nessuna GPU NVIDIA né CUDA necessaria: la trascrizione gira su CPU, e l'eventuale
  LLM locale usa Vulkan (funziona su schede AMD, NVIDIA e Intel)

Prestazioni misurate su Ryzen 5 5600G (6 core) e Radeon RX 6700, senza CUDA:

| | italiano parlato | inglese sintetico |
|---|---|---|
| Trascrizione | 12,6x realtime | 8,8x realtime |
| Latenza mediana, finestra da 3 s | 241 ms | 250 ms |
| p95 | 277 ms | 287 ms |
| Drift fra le due tracce | 4 ms/ora | |

Sono le prestazioni misurate su questa macchina, non una promessa generale: hardware
diverso darà numeri diversi. Le due colonne ci sono perché i numeri cambiano con il
parlato: il campione italiano è voce reale, quello inglese è sintetico.

## Limiti noti

Onestamente, non solo quello che manca ma anche quello che non è mai stato verificato:

- **Solo Windows.** Nessun supporto macOS o Linux, né in programma.
- **Nessuna firma del codice.** L'installer non è firmato digitalmente (scelta di
  progetto, non una svista): Windows SmartScreen mostrerà un avviso alla prima
  apertura.
- **Il WER (word error rate) in italiano non è mai stato misurato.** Il modello di
  trascrizione dichiara un WER su benchmark pubblici (FLEURS), ma nessuno su questo
  progetto lo ha misurato su call italiane reali.
- **Il rilevamento automatico delle call non è stato validato contro Zoom, Teams e
  Meet reali in modo sistematico.** È stato verificato il meccanismo di base (chi usa
  il microfono, chi riproduce audio) sulla macchina di sviluppo; non c'è una verifica
  strutturata contro le tre piattaforme in condizioni diverse. Se non ti propone di
  registrare, **Impostazioni → Rilevamento call → Mostra** dice cosa sta vedendo in quel
  momento e quale condizione non è soddisfatta, invece di lasciartelo indovinare.
- **`whisper-large-v3` compare in alcune schermate/dati di esempio dell'interfaccia,
  ma non esiste un motore di trascrizione che lo usi davvero.** Il motore di
  trascrizione reale, unico e predefinito, è Parakeet TDT.
- **L'export verso Notion non è mai stato provato contro un account vero.** La logica —
  scelta del database, mappatura dei campi, creazione delle colonne — è coperta da test
  con le chiamate HTTP simulate, ma nessuno l'ha ancora vista funzionare su Notion. Al
  primo collegamento reale attenzione ai nomi delle opzioni di una colonna `status`: le
  sue opzioni l'API di Notion non può crearle, e un valore che non corrisponde a nessuna
  di quelle esistenti viene semplicemente non mandato.
- **Il database remoto non è mai stato provato contro un server vero.** La logica —
  lettura dell'indirizzo, creazione delle tabelle, mappatura, sincronizzazione — è
  coperta da test, e ce ne sono altri, già scritti, che girano contro un PostgreSQL
  reale appena ne trovano uno (`SCRIBA_PG_URL`, o Docker in esecuzione: se ne creano
  uno usa-e-getta da soli). Finché quelli non sono stati eseguiti almeno una volta,
  questa integrazione va considerata non verificata. Attenzione in particolare al
  pooler di Supabase in modalità transazione: gli statement preparati vanno spenti, e
  Scriba lo fa da sé riconoscendo la porta 6543 — se ti colleghi al pooler
  dichiarando «diretta», il secondo invio fallisce.
- **La chiusura ordinata dell'applicazione non è verificata fino in fondo.** Che il core
  travasi il WAL quando gli si chiede di fermarsi è provato; che il percorso completo
  (chiusura dal tray → attesa → spegnimento del core) lo faccia sempre, no. Quello che è
  stato provato, e che vale la pena sapere, è il caso opposto: se l'applicazione **muore
  di colpo**, Windows porta con sé anche il core prima che possa travasare — per questo
  il consolidamento periodico durante la registrazione non è un lusso.
- **La diarizzazione (distinguere le singole voci dentro "gli altri") richiede
  `pyannote.audio` installato a parte** — non è nel pacchetto (l'installer NSIS
  costruito con `npm run dist` lo esclude di proposito: pesa, insieme all'intero
  stack PyTorch, centinaia di MB). Per usarla bisogna partire dal sorgente e
  aggiungere `pyannote.audio`, `torch` e un token Hugging Face nell'ambiente Python
  del core a mano.

## Documentazione interna

La documentazione di progetto — architettura, decisioni tecniche (ADR), modello dati,
endpoint, stile di codice, roadmap, packaging — vive in [`.claude/project/`](.claude/project/README.md).
È pensata per chi sviluppa Scriba (o un agente AI che lo fa), non per chi lo usa e
basta.

## Licenza

MIT. Vedi [LICENSE](LICENSE).
