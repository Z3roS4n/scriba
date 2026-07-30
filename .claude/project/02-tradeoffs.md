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
