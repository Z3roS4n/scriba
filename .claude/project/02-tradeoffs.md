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
