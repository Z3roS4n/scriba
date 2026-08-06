# Scriba — Decisioni & trade-off (ADR)

> Ogni decisione non ovvia va registrata qui con un ID `D-00X`. Le decisioni aperte in fondo.

## Registro decisioni

### D-001 — Core Python come sidecar, UI in Electron
- **Contesto:** serve un'app desktop con cattura audio, STT locale, overlay e tray. Sulla
  macchina non è installato Rust, ed è installato Node 24 e Python 3.14.
- **Opzioni:** A) Tauri v2 (Rust) · B) Electron puro · C) Python + Qt · D) core Python
  sidecar + shell Electron.
- **Scelta:** D.
- **Motivo:** le due parti davvero difficili sono il loopback WASAPI e lo streaming STT
  con parziali. In Python sono entrambe un `pip install`; in Node e in Rust sono lavoro
  custom. Tauri è tecnicamente superiore per packaging (installer 5-15 MB contro
  90-150 MB) ma richiede MSVC Build Tools e COM grezzo per l'audio: il prototipo costerebbe
  3-5 volte tanto. Electron puro è escluso perché i binding npm di whisper.cpp sono
  wrapper file-based senza streaming, fermi da due anni.
- **Conseguenze:** il core non sa che Electron esiste — comunica su WebSocket locale. La
  shell è sostituibile con Tauri in seguito senza toccare audio, STT e AI. Prezzo pagato:
  due runtime da impacchettare e un ciclo di vita del processo figlio da gestire (Job
  Object + heartbeat, altrimenti restano sidecar orfani che tengono il microfono).
- **Data:** 2026-07-27

### D-002 — Parakeet locale come STT di default, API dietro la stessa interfaccia
- **Contesto:** la richiesta iniziale era "API Whisper OpenAI oppure modelli locali". La
  macchina è AMD senza CUDA, quindi `faster-whisper` su GPU è fuori gioco.
- **Opzioni:** A) API OpenAI · B) whisper.cpp con Vulkan · C) `onnx-asr` +
  `parakeet-tdt-0.6b-v3` int8 su CPU.
- **Scelta:** C come default, A disponibile, B come eventuale passata di rifinitura.
- **Motivo:** Parakeet dichiara WER italiano 3.00% su FLEURS, migliore di
  `gpt-4o-transcribe`. Gira su CPU lasciando la GPU libera, non richiede driver né
  PyTorch (solo numpy + onnxruntime), e costa zero. **Misurato su questa macchina: RTFx
  8.8x, latenza mediana 250 ms su finestre da 3 s.**
- **Conseguenze:** il default è gratis, offline e privato. Le API restano utili su audio
  rumoroso e per latenza sub-secondo. Nota di costo: con due tracce separate le API si
  pagano doppie.
- **Data:** 2026-07-27

### D-003 — llama.cpp Vulkan spedito come binario, Gemma 4 12B di default
- **Contesto:** anche l'analisi (riassunto, task) deve poter girare in locale, con
  modelli scaricabili dall'interfaccia.
- **Opzioni:** A) dipendere da Ollama installato dall'utente · B) LM Studio · C)
  `llama-cpp-python` · D) spedire `llama-server` Vulkan come binario.
- **Scelta:** D, con `unsloth/gemma-4-12b-it-GGUF` UD-Q4_K_XL come modello di default.
- **Motivo:** su RDNA2 Vulkan batte ROCm (~+20%), e gfx1031 non è supportato dall'HIP SDK
  su Windows: la scelta del backend è obbligata. Ollama non elenca gfx1031 fra i target e
  `HSA_OVERRIDE_GFX_VERSION` è documentato solo per Linux; in più dipendere da
  un'installazione utente è fragile per un'app che deve auto-configurarsi. LM Studio non è
  ridistribuibile. Le wheel Vulkan di `llama-cpp-python` sono cronicamente indietro.
- **Conseguenze:** controlliamo noi la versione del motore, e abbiamo accesso diretto a
  GBNF, `response_format: json_schema` e `--n-cpu-moe`. Gemma 4 è preferita a Qwen3.5-9B
  (che ha IFEval più alto) perché la sua architettura è convenzionale: il DeltaNet ibrido
  di Qwen è recente in llama.cpp e va verificato sul build pinnato prima di adottarlo.
- **Data:** 2026-07-27

### D-004 — Due tracce separate al posto della diarizzazione
- **Contesto:** serve sapere chi ha detto cosa.
- **Opzioni:** A) mixare l'audio e usare pyannote · B) tenere mic e loopback separati.
- **Scelta:** B, con la diarizzazione dei singoli partecipanti rimandata a un passo
  offline opzionale.
- **Motivo:** la separazione "io vs loro" per sorgente è esatta per costruzione, costa
  zero e funziona in tempo reale. La diarizzazione vera è probabilistica, e le soluzioni
  realtime richiedono CUDA.
- **Conseguenze:** `transcript_segments.speaker_raw` (mic/loopback) è ground truth e non
  va mai sovrascritto; i nomi dei singoli partecipanti sono un livello di inferenza
  separato, da confermare. Non si può promettere l'etichetta per singolo partecipante in
  tempo reale.
- **Data:** 2026-07-27

### D-005 — Le citazioni delle task le ricostruisce il codice, non il modello
- **Contesto:** ogni task deve portarsi dietro le prove: quale pezzo di conversazione
  giustifica il titolo, quale la scadenza, quale il responsabile.
- **Opzioni:** A) il modello scrive la citazione letterale e il timestamp · B) il modello
  emette `segment_id` + offset e il codice ricostruisce testo e tempo dal DB.
- **Scelta:** B.
- **Motivo:** un modello da 12B tende a parafrasare invece di copiare e ad allucinare i
  timestamp. È il modo principale in cui questa funzione fallisce, e non si risolve con
  un prompt migliore. Chiedendo solo un riferimento, l'errore diventa impossibile.
- **Conseguenze:** le evidence sono verificabili per costruzione. `task_evidence.quote`
  conserva comunque una copia del testo, così se un segmento viene rifinito la citazione
  già mostrata all'utente resta stabile.
- **Data:** 2026-07-27

### D-006 — Timeline ibrida: contigua nei tratti, riancorata sui buchi
- **Contesto:** il loopback WASAPI non consegna pacchetti mentre nessuna applicazione
  riproduce audio. Chi concatena i chunk anticipa tutto ciò che viene dopo una pausa.
- **Opzioni:** A) concatenare e reinserire i buchi misurando la distanza fra gli arrivi ·
  B) posizionare ogni chunk in modo assoluto dal suo timestamp · C) ibrido.
- **Scelta:** C — contiguo finché i chunk arrivano di seguito, salto alla posizione
  assoluta quando la consegna si interrompe oltre 50 ms.
- **Motivo:** misurato in Fase 1. A accumula ~200 ms di errore per ogni pausa. B non
  accumula ma lascia micro-buchi di ~1 ms per chunk (2 s di zeri su 36 s di traccia),
  udibili come click. L'ibrido non ha nessuno dei due difetti.
- **Conseguenze:** silenzio ricostruito sceso da 2.064 s a 0.035 s sulla traccia mic; le
  due timeline coincidono entro 15 ms su 36 s.
- **Data:** 2026-07-27

### D-007 — Core pacchettizzato con PyInstaller onedir, UI con electron-builder/NSIS
- **Contesto:** Scriba si avviava solo dalla cartella di sviluppo (nessun installer). Il
  core ha dipendenze native pesanti (onnxruntime, PyAudioWPatch, sounddevice, scipy,
  winsdk) che notoriamente rompono i pacchetti PyInstaller.
- **Opzioni:** A) onefile PyInstaller · B) onedir PyInstaller · C) lasciare il core come
  script Python e richiedere Python installato sulla macchina di destinazione.
- **Scelta:** B — onedir per il core, extraResource dentro un installer NSIS
  (electron-builder) per la UI. Vedi `.claude/project/10-packaging.md` per i dettagli.
- **Motivo:** onefile si autoestrae in una cartella temporanea a ogni avvio (centinaia di
  MB ricopiati ogni volta, riscansionati dall'antivirus). C richiederebbe che l'utente
  installi Python e le dipendenze native a mano, che è esattamente il problema che il
  packaging deve risolvere. `app.getAppPath()` risolto da Electron cambia da solo fra
  sviluppo (`ui/`) e pacchetto (`resources/`), e questo è quello che `sidecar.ts` usa per
  trovare il core nei due mondi senza un interruttore manuale.
- **Conseguenze:** trovato e risolto un bug non ovvio — `detect/call.py` isola la sonda
  COM lanciando `sys.executable -m scriba_core.detect.probe`, invocazione che ha senso
  solo con un vero interprete Python. L'entry point del core pacchettizzato
  (`scripts/pyinstaller/entry_point.py`) emula `-m` con `runpy` per restare compatibile
  senza toccare `core/scriba_core/`. Il core pacchettizzato pesa ~290 MB (nessun modello
  AI incluso, quelli restano scaricabili dall'interfaccia): la parte piu' pesante e'
  `scipy`, usata per una sola funzione (`resample_poly`). `core/.venv` e' condiviso con
  chi sviluppa altre funzioni (es. diarizzazione via PyTorch): lo spec esclude
  esplicitamente PyTorch e affini, altrimenti una build del core puo' gonfiarsi di 400+ MB
  senza che il codice del core sia cambiato — successo davvero durante questo lavoro.
- **Data:** 2026-07-29

### D-008 — Le colonne di Notion le decide l'utente, non il connettore
- **Contesto:** il connettore Notion indovinava le colonne confrontando il nome di ogni
  proprietà del database con una lista di alias (`assegnatario`/`assignee`/`responsabile`…).
  Una colonna chiamata diversamente veniva saltata in silenzio, e non c'era modo di dire
  «la scadenza va in *Quando*» né di partire senza un database già adatto.
- **Opzioni:** A) allungare la lista di alias · B) mappatura esplicita scelta dall'utente ·
  C) pretendere un database con nomi di colonna fissi, creandolo noi e basta.
- **Scelta:** B come base, più la creazione guidata (C) come scorciatoia per chi non ha
  ancora un database. A resta, ma solo come **proposta** già compilata da correggere.
- **Motivo:** gli alias sono una scommessa sul vocabolario di qualcun altro: perdono
  sempre, e perdono in silenzio, che è il modo peggiore. Pretendere nomi fissi (C da solo)
  significa chiedere a chi ha già un database di impegni di rifarlo. Con la mappatura
  esplicita la scelta è visibile e correggibile; con la creazione guidata chi parte da zero
  non deve costruire niente a mano.
- **Conseguenze:** la mappa (`{campo → nome proprietà}`) vive in `export_notion.json` e
  viene **verificata contro lo schema vero** prima di essere salvata: colonna assente, tipo
  incompatibile e due campi sulla stessa colonna diventano un errore leggibile invece di un
  400 di Notion a metà invio. `mappa: null` significa «nessuna scelta fatta»: chi aveva
  collegato Notion prima continua a funzionare col riconoscimento per nome. Un valore di
  dominio conosce i suoi sinonimi (`alta`/`Alta`/`High`) così da riusare le opzioni che il
  database ha già invece di duplicarle, e uno `status` non mandato è meglio di una riga
  rifiutata: le sue opzioni non si possono creare dall'API. Cambiare database azzera gli id
  remoti salvati, altrimenti si aggiornerebbero righe nel database vecchio riportando
  «aggiornati» con quello nuovo vuoto. Prezzo pagato: sei chiamate REST in più (ricerca,
  schema, creazione) e una schermata a passi al posto di due campi da incollare.
- **Data:** 2026-07-30

### D-009 — Il WAL si consolida quando i dati diventano definitivi, non quando decide SQLite
- **Contesto:** una call di due ore è stata persa dal database. Il file principale era
  fermo allo stato di due giorni prima, tutto il lavoro successivo stava in un `-wal` da
  4 MB, e quel WAL è finito disallineato dal database («database disk image is
  malformed»). Della call si è salvato solo l'export Markdown fatto a mano.
- **Cause trovate:** (a) il consolidamento automatico di SQLite è **passivo** e rinuncia in
  silenzio se un'altra connessione sta usando il WAL — durante una call è sempre vero, due
  tracce scrivono un segmento al secondo; (b) allo spegnimento non consolidava nessuno,
  perché il core veniva **ucciso** (`os._exit` sul guinzaglio dello stdin, `child.kill()`
  dal lato Electron) e l'uccisione salta l'unico momento in cui SQLite l'avrebbe fatto da
  sé; (c) in sviluppo il core vero è un **nipote** di Electron — il `python.exe` del venv
  creato con uv ri-esegue l'interprete di base — quindi `kill()` uccideva lo stub e
  lasciava il core vivo col database aperto: al build successivo ne partiva un altro sullo
  stesso file.
- **Opzioni:** A) alzare `wal_autocheckpoint` · B) un checkpoint periodico a tempo · C)
  consolidare nei punti in cui il lavoro diventa definitivo, più spegnimento ordinato.
- **Scelta:** C. A non risolve niente (il problema non è la soglia, è che il checkpoint
  passivo rinuncia); B mette in sicurezza a caso invece che quando serve.
- **Conseguenze:** `Store.consolida()` (`wal_checkpoint(TRUNCATE)`, con ritentativi) viene
  chiamata a fine registrazione, a fine analisi e allo spegnimento. Il core chiede a
  uvicorn di fermarsi e solo dopo 4 s esce di forza; `Sidecar.stop()` chiude lo stdin,
  attende 6 s e poi uccide **l'albero** (`taskkill /T`), così chi si ferma per primo è
  sempre il core. Rete di sicurezza: all'avvio un `quick_check`, e un database illeggibile
  viene messo da parte con tutto il suo WAL e sostituito dal backup più recente invece di
  continuare a scriverci dentro (`db/manutenzione.py`); i backup sono `VACUUM INTO` — un
  file solo, che non può soffrire dello stesso disallineamento — tenuti in rotazione di 5,
  fatti all'avvio e a fine registrazione. Aggiunto il lucchetto di istanza singola in
  Electron: due app sulla stessa cartella dati sono due core sullo stesso database.
- **Prezzo pagato:** qualche centinaio di ms a fine call, una copia del database per call,
  e fino a 6 s di attesa alla chiusura dell'app.
- **Data:** 2026-07-30

### D-010 — I clienti sono una tabella, e le call sincronizzate si riconoscono dall'uuid
- **Contesto:** dopo qualche mese la domanda non è più «cos'ho fatto ieri» ma «cosa ci
  siamo detti con questo cliente». Serviva un'entità cliente, e serviva mandare le call su
  un database remoto senza duplicarle a ogni invio.
- **Opzioni per il cliente:** A) un campo di testo su `sessions` con autocompletamento ·
  B) una tabella con chiave esterna.
- **Scelta:** B. Rinominare un cliente deve valere per tutte le sue call insieme, e un
  testo libero diventa tre grafie della stessa azienda nel giro di un mese. I nomi si
  confrontano su una forma normalizzata tenuta in una colonna sua (`nome_norm`, unique):
  è lì che si decide se due righe di un CSV importato sono lo stesso cliente.
- **Opzioni per l'identità remota:** A) `tasks.id` · B) un `uuid` per ogni riga.
- **Scelta:** B. `tasks.id` è un contatore di **questo** file: due installazioni si
  sovrascriverebbero a vicenda, e ricostruire il database locale — è già successo, vedi
  D-009 — rimescolerebbe ogni riferimento.
- **Conseguenze:** ogni tabella del modello remoto dichiara la sua chiave naturale, e una
  mappatura che se la dimentica viene **rifiutata al collegamento**, con il motivo, invece
  di accumulare doppioni silenziosi. Un test gira su tutte le tabelle e pretende che ne
  abbiano una. Duplicare le task di una riunione dentro il sistema di lavoro di qualcuno è
  un danno vero, non un fastidio.
- **Prezzo pagato:** due migrazioni (`sessions.client_id`, `tasks.uuid`) e la disciplina di
  non riusare `export_target`, che ne regge una sola ed è di Notion: il database remoto
  tiene il suo stato in `sync_remoto`.
- **Data:** 2026-08-01

### D-011 — Il rilevamento si guarda invece di indovinarlo
- **Contesto:** «non mi ha proposto di registrare» ha almeno cinque cause — sonda ferma,
  processo escluso, microfono senza segnale, nessun audio in riproduzione, attesa di
  conferma non scaduta — e dall'esterno sono indistinguibili.
- **Opzioni:** A) tentare un rimedio sull'ipotesi più probabile · B) rendere osservabile il
  ragionamento e poi guardare.
- **Scelta:** B, prima di toccare le regole. Un rimedio scelto fra cinque ipotesi ha una
  probabilità su cinque di essere quello giusto, e le altre quattro volte cambia il
  comportamento senza sistemare niente.
- **Conseguenze:** `GET /rilevamento/diagnostica` riporta l'esito dell'ultimo giro processo
  per processo, con il perché scritto a parole, più lo stato della sonda (viva, ripartenze,
  se ha rinunciato — cosa che prima succedeva in silenzio). Legge lo stato dell'ultimo giro
  e **non** interroga le API audio: due processi che leggono insieme quelle interfacce COM
  si disturbano, ed è la ragione per cui la sonda vive in un processo suo.
- **Trovato costruendolo:** `psutil` non era dichiarato fra le dipendenze, e arrivava di
  rimbalzo. È quello che collega il microfono di un browser all'audio che esce da un suo
  processo figlio: un aggiornamento altrui si sarebbe portato via il rilevamento delle call
  nel browser senza un errore, solo smettendo di funzionare.
- **Sospetto aperto, non confermato:** su questa macchina ogni processo con una sessione
  microfono riporta un picco di **esattamente 0.0**, Edge compreso, e la regola li scarta
  come sessioni vecchie. `probe.py` afferma il contrario come dato misurato. Se non regge
  durante una call vera, nessuna riunione può essere riconosciuta. Serve una call vera.
- **Data:** 2026-08-01

### D-012 — Scuro resta il predefinito, anche ora che il chiaro si può scegliere
- **Contesto:** il tema chiaro esisteva già ed era completo — in `tokens.css` è il `:root`,
  e lo scuro sono 74 sovrascritture sopra — ma era irraggiungibile per una riga scritta a
  mano in ognuna delle tre pagine.
- **Opzioni:** A) predefinito «come il sistema», come fanno quasi tutte le applicazioni ·
  B) predefinito scuro, con «come il sistema» fra le scelte.
- **Scelta:** B. Scriba è sempre stato scuro: far cambiare aspetto da sola a
  un'applicazione già installata, perché qualcun altro ha deciso un default, è una sorpresa
  che nessuno ha chiesto.
- **Conseguenze:** il valore iniziale arriva dal ponte, letto in modo sincrono dal processo
  principale da `settings.json` e applicato nel **preload** — la CSP delle pagine vieta gli
  script inline, e quello è l'unico codice che gira prima del documento. Anche
  `backgroundColor` delle finestre segue, altrimenti il tema chiaro comincerebbe con un
  lampo nero a ogni apertura. Le tre finestre sono tre processi: l'evento `tema:cambiato`
  le allinea, perché vederne due di colori diversi sarebbe peggio che non poterlo cambiare.
- **Eccezione, voluta:** il vetro dell'overlay resta scuro in entrambi i temi — le sue
  regole non usano nessun token di colore. Sta sopra la finestra di una riunione, spesso a
  schermo intero e spesso scura: un rettangolo bianco lì è un abbaglio.
- **Data:** 2026-08-02

### D-013 — L'export per un modello dichiara quello che non ha una fonte
- **Contesto:** serviva poter dare analisi e task a un modello. Il JSON aveva già tutto,
  comprese le prove per campo, ma le lega per `segment_id`: un modello dovrebbe incrociare
  gli id prima di poter ragionare, spendendo contesto per un lavoro che possiamo fare noi
  una volta sola.
- **Scelta:** un formato nuovo (`export/contesto.py`) dove ogni affermazione porta
  **accanto** la citazione da cui viene, scritta per esteso, con il minuto.
- **La parte che conta di più:** quello che una fonte non ce l'ha viene **detto**. Una task
  senza prove non diventa una task con prove implicite — si scrive che non ne ha, e che va
  trattata come un'ipotesi. Senza questa distinzione l'ipotesi del primo modello diventa
  la premessa del secondo, e l'errore si consolida invece di restare visibile. Per lo
  stesso motivo l'intestazione spiega che cos'è una citazione e che cos'è interpretazione:
  senza, «nessuna citazione» si legge come una dimenticanza invece che come un dato.
- **Il peso si mostra prima.** Il contesto di un modello è finito e una call di due ore
  sono ~800 segmenti: la trascrizione integrale è una spunta, spenta di default, e
  `/export/contesto/anteprima` dice quanto pesa senza scrivere niente. Scoprirlo quando il
  documento viene troncato è tardi.
- **Più call insieme,** perché la domanda vera è «dammi tutto quello che ci siamo detti con
  questo cliente» — e la selezione esiste già nell'archivio, filtrata.
- **Data:** 2026-08-03

### D-014 — Una frase che si apre si chiude sempre, anche a mani vuote
- **Contesto:** `_finalize` poteva uscire senza emettere niente (VAD che non risente
  parlato, passata completa che restituisce vuoto) dopo che i provvisori erano già usciti.
  Il segmento restava aperto, e il primo provvisorio della frase **successiva** lo rifiniva:
  la frase di prima veniva cancellata e quella dopo ereditava il suo istante di inizio.
  Non era il modello che capiva male — era testo trascritto bene e perso dopo.
- **Scelta:** l'invariante è «chi ha emesso un provvisorio emette un definitivo», senza
  eccezioni. Un definitivo **vuoto** è un messaggio pieno: vuol dire «non è rimasto niente,
  butta via quello che avevi». Il recorder cancella il segmento, i due renderer tolgono la
  riga provvisoria.
- **Quando la passata finale non produce niente si tiene l'ultimo provvisorio.** Imperfetto
  batte mancante: l'audio resta sul disco e la trascrizione si può rifare, ma una riga che
  non c'è nessuno la nota finché non gli serve — e intanto il riassunto e le task sono
  nati senza.
- **Il recorder non si fida comunque.** Riconosce un segmento rimasto aperto dall'istante
  di inizio diverso, lo chiude com'era e **lo scrive nel log**. È ridondante rispetto
  all'invariante di sopra, ed è voluto: il difetto era invisibile proprio perché nessuno
  dei due lati sapeva di dover controllare.
- **Data:** 2026-08-06

### D-015 — I nomi propri si correggono dopo, e solo dove il rischio è basso
- **Contesto:** un nome fuori vocabolario viene indovinato da capo a ogni frase e
  ogni volta diversamente («Clotilde» → *Tilde*, *Cotilde*, *Protile*). Non è estetica:
  una task assegnata a *Giulio* invece che a Giulia è sbagliata, e la ricerca
  nell'archivio non trova la call. Parakeet non ha un aggancio per ricevere un
  vocabolario prima — le famiglie transducer non ne hanno uno e onnx-asr non lo espone.
- **Scelta:** correzione **a valle**, sui soli segmenti definitivi, contro un glossario
  che unisce i termini scritti a mano e i nomi dei clienti già in anagrafica.
- **La parte difficile non è trovare i nomi: è non rovinarli.** Prendere *Protile* vuol
  dire ammettere tre modifiche su otto lettere, e a quella distanza ci sta anche
  **Matilde**, che è un'altra persona. Correggere un nome giusto in uno sbagliato è
  peggio del difetto di partenza: il primo lo si vede rileggendo, il secondo no. Da qui
  tre regole che valgono più della soglia:
  1. **Serve il segnale della maiuscola.** Su una parola sola, senza, si corregge solo
     ciò che combacia già: «totale» dista una lettera da «Tonale».
  2. **Nel dubbio non si tocca.** Due termini entrambi compatibili con la stessa parola
     la lasciano com'è — i nomi vicini si proteggono a vicenda.
  3. **L'originale resta** in `transcript_segments.testo_originale`. L'app sta mettendo
     in bocca a qualcuno una parola che il modello non ha sentito: dev'essere
     annullabile e verificabile.
- **Il livello lo sceglie chi usa l'app,** e `prudente` è il default: allargare la rete
  è una decisione con un costo, non un miglioramento gratuito da attivare di nascosto.
- **Non si tocca il provvisorio.** Una correzione che compare e sparisce mentre si legge
  è peggio del nome sbagliato.
- **Data:** 2026-08-06

## Decisioni aperte

- **OA-1** — Passare a Qwen3.5-9B come LLM di default? Ha IFEval più alto e KV cache più
  economico, ma serve prima verificare che il build llama.cpp pinnato supporti la sua
  architettura DeltaNet.
- **OA-2** — Loopback per processo (registrare solo Zoom, non Spotify) via
  `ActivateAudioInterfaceAsync` + `PROCESS_LOOPBACK`: non esposto da PyAudioWPatch,
  richiederebbe un'estensione nativa. Da valutare quando il resto è stabile.
- **OA-3** — Estensione Chrome per rilevare Google Meet in modo affidabile: senza, un
  meeting in un tab di background non è distinguibile. Da decidere se vale l'attrito di
  installare un'estensione.
