# Scriba

Registra e trascrive le call di lavoro in locale, mostrando il testo mentre si parla, e
ne ricava riassunto, punti salienti e task.

Gira interamente sulla tua macchina: la trascrizione usa un modello locale e anche
l'analisi AI può girare in locale. Le API esterne ci sono, ma sono un'alternativa da
scegliere, non il default.

> **Stato: in sviluppo.** Registrazione, trascrizione live e interfaccia funzionano. Le
> funzioni AI — riassunto, punti salienti, estrazione task — non sono ancora implementate.

## Come funziona

**Due tracce, mai mischiate.** Il microfono e l'audio di sistema vengono catturati
separatamente e trascritti in modo indipendente. Questo dà "io" e "gli altri" senza
bisogno di diarizzazione, con precisione perfetta e costo zero.

**Screenshot ancorati al tempo.** Durante la call una scorciatoia da tastiera cattura lo
schermo; l'immagine resta legata all'istante della call in cui l'hai presa e viene usata
come contesto quando si genera il riassunto.

**Task ricomposte, non ritagliate.** In una call vera i dettagli di un impegno sono
sparsi: il lavoro si nomina al minuto 5, la scadenza si concorda al 32, il responsabile
si decide al 48. Scriba estrae i frammenti dove sono densi e poi li ricompone, tenendo
traccia di quale pezzo di conversazione giustifica quale campo.

## Requisiti

- Windows 10/11 (la cattura audio usa WASAPI)
- Python 3.12 — installato in automatico da [uv](https://docs.astral.sh/uv/)
- ~1 GB di spazio per il modello di trascrizione, ~7 GB se usi anche l'LLM locale

Non serve una GPU NVIDIA né CUDA: la trascrizione gira su CPU e l'LLM locale usa Vulkan,
che funziona su schede AMD, NVIDIA e Intel.

## Avvio

```bash
uv venv core/.venv --python 3.12
uv pip install --python core/.venv/Scripts/python.exe PyAudioWPatch sounddevice numpy scipy "onnx-asr[cpu,hub]" fastapi "uvicorn[standard]"
```

```bash
cd ui && npm install && npm start
```

Il modello di trascrizione (~600 MB) si scarica al primo avvio.

L'app resta nell'area di notifica quando chiudi la finestra. Durante una call,
<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>S</kbd> cattura uno screenshot e lo aggancia al punto
in cui siete.

## Verificare la propria macchina

Verifica che la cattura a due tracce funzioni:

```bash
core/.venv/Scripts/python.exe spikes/list_devices.py
core/.venv/Scripts/python.exe spikes/audio_capture.py --seconds 36 --gap
core/.venv/Scripts/python.exe spikes/verify_alignment.py
```

Misura la velocità della trascrizione (il modello si scarica al primo avvio, ~600 MB):

```bash
core/.venv/Scripts/python.exe spikes/record_sample.py
core/.venv/Scripts/python.exe spikes/bench_stt.py spikes/out/sample_it.wav
core/.venv/Scripts/python.exe spikes/score_stt.py
```

## Prestazioni misurate

Su Ryzen 5 5600G (6 core) e Radeon RX 6700, senza CUDA:

| | |
|---|---|
| Trascrizione | 8.8x realtime |
| Latenza per finestra da 3s | 250 ms (p95 287 ms) |
| Drift fra le due tracce | 4 ms/ora |

## Registrare le call e la legge

Registrare una conversazione a cui partecipi ha regole diverse da paese a paese, e
registrare **gli altri** partecipanti significa trattare i loro dati personali. Scriba
chiede conferma esplicita a ogni avvio e la annota nella sessione, ma quella conferma non
sostituisce l'avviso ai partecipanti: dirglielo prima è una tua responsabilità.

## Licenza

MIT.
