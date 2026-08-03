# Scriba — Stack tecnico

> Versioni pinnate: `core/requirements.txt` e `ui/package.json` sono la fonte di
> verità, qui si spiega **perché**. Aggiornare a ogni cambio di dipendenza.
> Ultimo aggiornamento: 2026-08-02.

**Solo Windows 10/11.** Non è una limitazione temporanea: la cattura a due
tracce usa WASAPI, il rilevamento usa le sessioni audio di Windows, l'OCR usa
WinRT e i segreti usano DPAPI. Quattro dipendenze dal sistema, non una.

## Runtime

| Layer | Scelta | Note |
|---|---|---|
| Interfaccia | **Electron 39** + React 19 | tre bundle esbuild, nessun framework |
| Linguaggio UI | **TypeScript 5.7** strict | `tsc --noEmit`, nessun emit |
| Core | **Python 3.12** | ambiente in `core/.venv`, creato con `uv` |
| Server locale | **FastAPI 0.140** + uvicorn | 127.0.0.1, porta effimera, token |
| Database | **SQLite** (stdlib) in WAL, con FTS5 | nessun ORM: vedi sotto |
| Pacchetto | **PyInstaller onedir** + **electron-builder/NSIS** | |

**Nessun ORM.** Le query di questo progetto sono poche, mirate e piene di
ragioni che vanno scritte accanto al SQL (il perché di un indice parziale, di
un UPSERT, di una `revision` che cresce invece di una riga che si ricrea). Un
ORM le nasconderebbe senza toglierne nessuna.

## Librerie del core

| Scopo | Libreria | Perché quella |
|---|---|---|
| Audio | `PyAudioWPatch` · `sounddevice` | il loopback WASAPI non c'è in PyAudio normale |
| Trascrizione | `onnx-asr[cpu,hub]` | `cpu` evita di tirarsi dietro CUDA |
| Numerico | `numpy` · `scipy` | eco, finestre, ricampionamento |
| HTTP | `httpx` | motori di analisi e connettori di export |
| OCR | `winsdk` | OCR di sistema: nessun modello da scaricare |
| Sessioni audio | `pycaw` · `comtypes` | è così che si capisce di essere in call |
| Albero processi | `psutil` | **collega il microfono del browser all'audio di un suo figlio.** Arrivava di rimbalzo: dichiararlo è servito, un aggiornamento altrui si sarebbe portato via il rilevamento nel browser senza un errore |
| PostgreSQL | `psycopg[binary]` | `binary` porta con sé libpq: nessun compilatore, nessun PostgreSQL da installare |

**Opzionale, fuori dal pacchetto:** `pyannote.audio` per la diarizzazione. Si
porta dietro l'intero stack PyTorch (centinaia di MB) per una funzione che si usa
a fine call e non tutti vogliono. Gli import in `stt/diarizzazione.py` sono
dentro i metodi apposta: assente, la funzione resta assente con grazia.

## Dipendenze di sviluppo

`pytest` e `pyinstaller` (`core/requirements-dev.txt`). Senza il secondo
`npm run dist` si ferma a metà. Il venv è escluso dal pacchetto per nome nello
spec: è condiviso con chi ci installa cose pesanti.

## Configurazione: nessuna variabile d'ambiente

Non c'è un contratto di env, ed è una scelta. Scriba è un'applicazione che si
installa, non un servizio che si distribuisce: chi la usa non ha una shell in cui
esportare segreti. Tutto vive accanto al database, in
`%APPDATA%\scriba-ui\data`:

| File | Contenuto | Segreti |
|---|---|---|
| `settings.json` | preferenze, `llm.api_key` | in chiaro |
| `export_notion.json` | token e mappatura Notion | in chiaro |
| `database_remoto.json` | URL PostgreSQL e mappatura | **cifrato con DPAPI** |
| `scriba.sqlite` | tutto il resto | — |

L'URL del database è l'unico cifrato, e la ragione è che non è una chiave API di
un servizio: è la password di un PostgreSQL che può essere di produzione, e chi
legge quel file ci entra dentro. DPAPI non richiede né una dipendenza né una
passphrase da chiedere. Non protegge da un programma che gira come te — quello
può richiamarlo esattamente come lo richiamiamo noi — ma è la differenza fra una
password che si legge aprendo un file e una che no.

## Servizi esterni

| Servizio | Quando serve | Costo |
|---|---|---|
| Anthropic / OpenAI | solo se scegli quel motore | a consumo |
| Claude Code CLI | solo con abbonamento già attivo | incluso |
| Notion | solo se colleghi l'export | gratuito |
| PostgreSQL / Supabase | solo se colleghi il database remoto | dipende dal piano |
| Hugging Face | modelli STT e LLM al primo avvio | gratuito |

Nessuno di questi è obbligatorio: senza nessun account Scriba registra,
trascrive e analizza in locale. Ogni scheda sta in
[`.claude/integrations/`](../integrations/).
