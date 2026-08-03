# Scriba — Architettura

> Ultimo aggiornamento: 2026-08-02. Documento vivo: aggiornare a ogni decisione
> architetturale, nello stesso commit che la introduce.

## Visione

Un'applicazione desktop Windows che registra le riunioni di lavoro, le trascrive
mentre si parla e ne ricava riassunto, punti salienti e task — con la
trascrizione sempre in locale e l'analisi in locale se lo si sceglie. È per chi
fa call di lavoro e vuole un verbale utilizzabile senza affidare l'audio a un
servizio in cloud per ottenerlo.

## Diagramma logico

```
        ┌──────────────────────── Electron (Node) ─────────────────────────┐
        │  main/index.ts     finestre, tray, scorciatoie globali, schermi  │
        │  main/sidecar.ts   avvia e sorveglia il core                     │
        │  main/preload.ts   ponte: get/post/patch, eventi, tema           │
        │        │                                                          │
        │        │ contextBridge (il renderer non vede ne' Node ne' token)  │
        │  ┌─────┴────────────────────────────────────────────────────┐    │
        │  │ renderer/  index.tsx · overlay.tsx · Impostazioni.tsx    │    │
        │  │ tre bundle, tre processi, stesso preload                 │    │
        │  └──────────────────────────────────────────────────────────┘    │
        └───────────────────────────┬──────────────────────────────────────┘
                                    │ HTTP + WebSocket su 127.0.0.1
                                    │ porta effimera + token
        ┌───────────────────────────┴──────────────────────────────────────┐
        │                    core Python (FastAPI/uvicorn)                  │
        │                                                                   │
        │  recorder.py ──┬── audio/capture.py   mic + loopback WASAPI       │
        │                └── stt/streaming.py   Parakeet, due tracce        │
        │                                                                   │
        │  ai/analyze.py ─── llm/providers.py   local · claude-cli · API    │
        │  detect/call.py ── detect/probe.py    (processo separato: COM)    │
        │  export/ ───────── markdown · testo · json · notion · http · sql  │
        │  db/store.py ───── SQLite WAL + FTS5                              │
        └───────────────────────────┬──────────────────────────────────────┘
                                    │
       ┌────────────────────────────┼───────────────────────────┐
       │                            │                           │
  %APPDATA%\scriba-ui\data    llama-server (locale)      servizi esterni
  scriba.sqlite · audio/      su 127.0.0.1:8080          Anthropic · OpenAI
  screenshots/ · backup/                                 Notion · PostgreSQL
```

## Componenti chiave

### 1. Processo principale Electron (`ui/main/`)

Possiede le finestre (principale, impostazioni, overlay), l'icona nell'area di
notifica, le scorciatoie globali e il ciclo di vita del core. **Non contiene
logica di dominio**: inoltra comandi. È l'unico processo che conosce il token
del core — il renderer non lo riceve mai, così una pagina compromessa non può
parlare col core per conto suo.

- `sidecar.ts` trova il core in sviluppo (`core/.venv`) o nel pacchetto
  (`resources/core-dist/`) risalendo di uno da `app.getAppPath()`. Lo spegne
  chiudendo stdin e, se non basta, con `taskkill /T /F`.
- `preload.ts` espone una superficie ristretta e uguale per tutte e tre le
  finestre. Il tema è l'unica cosa sincrona: serve prima che la pagina esista.

### 2. Renderer (`ui/renderer/`)

Tre bundle esbuild, tre processi: finestra principale, impostazioni, overlay.
Non condividono stato — quello che devono sapere insieme passa da un evento del
processo principale (`tema:cambiato`, `schermi:cambiati`) o si rilegge dal core.
I file condivisi (`tipi.ts`, `tema.ts`, `schermi.ts`, `scriba.d.ts`) esistono
perché tre copie della stessa struttura divergono alla prima modifica.

### 3. Core Python (`core/scriba_core/`)

| Modulo | Responsabilità |
|---|---|
| `server.py` | FastAPI: ciclo di vita, registrazione, analisi, WebSocket |
| `api/` | Rotte per argomento, con `Contesto` esplicito invece della chiusura |
| `recorder.py` · `audio/` | Cattura mic + loopback WASAPI su due tracce separate |
| `stt/` | Parakeet in streaming, cancellazione dell'eco, diarizzazione opzionale |
| `ai/` | Analisi in due passaggi, note correnti, OCR degli screenshot |
| `llm/` | I motori dietro un'unica interfaccia: locale, CLI Claude, API |
| `detect/` | Rilevamento call: `call.py` decide, `probe.py` osserva |
| `export/` | Markdown, testo, JSON, Notion, HTTP generico, `sql/` remoto |
| `db/` | `store.py` (accesso), `manutenzione.py` (controllo e backup) |
| `models_manager.py` | Download, avvio e stato dei modelli locali |

### 4. La sonda audio, in un processo suo

`detect/probe.py` gira **fuori** dal core. Le API COM che enumera fanno terminare
bruscamente il processo che le interroga a ripetizione — non sollevano
un'eccezione, muore e basta, dentro `comtypes`. Un processo che registra una
riunione non può morire perché una funzione di comodità ha interrogato il mixer.
Se cade la sonda, cade lei, e `call.py` la riavvia.

## Flussi principali

**Registrazione → verbale.** `POST /session/start` → `recorder.py` apre due
tracce WASAPI → `stt/streaming.py` emette segmenti provvisori e poi definitivi →
`db/store.py` li scrive (con FTS) → il WebSocket li spinge all'interfaccia in
tempo reale → `POST /session/stop` → analisi automatica dopo 2 s →
`ai/analyze.py` produce riassunto, salienti e task con le loro prove → il
risultato torna via WebSocket, e se un database remoto è collegato la call ci
viene sincronizzata.

**Rilevamento.** `probe.py` stampa una riga JSON per giro (chi ha il microfono,
chi riproduce) → `call.py` applica le regole → dopo `conferma_s` chiama
`on_call` → il core pubblica l'evento → l'interfaccia propone di registrare.
Proporre, non avviare: registrare altre persone non è una decisione che spetta a
un programma.

**Sincronizzazione remota.** `export/sql/modello.py` estrae le righe →
`export/sql/postgres.py` genera DDL e upsert → una transazione per call, così o
la riunione c'è per intero o non c'è.

## Struttura repo

```
core/
  scriba_core/        il core (vedi tabella sopra)
  tests/              pytest, ~490 test
  requirements*.txt
ui/
  main/               processo principale Electron
  renderer/           i tre bundle React
    impostazioni/     una sezione per scheda
  build-resources/    grafica dell'installer NSIS
  electron-builder.yml
assets/               logo: scriba.png (sorgente) e scriba.ico (7 misure)
scripts/              build del core, generazione icona e grafica installer
spikes/               prove isolate che richiedono hardware o account veri
.claude/project/      questi documenti
.claude/integrations/ una scheda per servizio esterno
```
