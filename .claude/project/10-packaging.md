# Scriba — Packaging (installer Windows)

> Come si costruisce, da dove viene ogni pezzo, cosa verificare dopo ogni modifica.
> Aggiornare questo file quando cambia qualcosa nel packaging (stesso commit).

## In breve

Due impacchettamenti separati, uniti da un solo eseguibile finale:

1. **Core Python → eseguibile standalone** (PyInstaller, onedir). Non richiede
   Python installato sulla macchina di destinazione.
2. **UI Electron → installer NSIS** (electron-builder). Non richiede Node.
   L'eseguibile del core (punto 1) viene copiato dentro come `extraResource`.

I modelli AI (STT Parakeet dentro il pacchetto `onnx_asr`, LLM di analisi
scaricabili dalle Impostazioni) **non entrano** in nessuno dei due pacchetti:
si scaricano al primo avvio, come da decisione di progetto. Il core
pacchettizzato è ~290 MB già di suo (onnxruntime, scipy, le proiezioni WinRT
per l'OCR, i binari PortAudio): aggiungerci anche solo il modello LLM più
piccolo (5,5 GB) renderebbe l'installer un download assurdo.

## Come si costruisce

```powershell
cd ui
npm run dist
```

Espande in tre passi (anche eseguibili singolarmente):

```powershell
npm run build        # main + renderer (esistente, invariato)
npm run build:core   # scripts/build-core.ps1 -> dist/core/scriba_core/scriba_core.exe
npx electron-builder --config electron-builder.yml   # -> release/Scriba Setup <versione>.exe
```

`build:core` usa `core/.venv` come interprete: PyInstaller deve *importare
per davvero* `scriba_core` e le sue dipendenze per scoprire cosa impacchettare,
quindi gira con lo stesso Python che le ha già installate. Se in
`core/.venv` manca PyInstaller (o pip, che un venv creato con `uv venv` non
ha di serie) lo script lo installa al volo.

Output finale: `ui/release/Scriba Setup <versione>.exe` (~180 MB, installer
NSIS non firmato, per-utente — non richiede privilegi di amministratore).

## Struttura dei file di packaging

| File | Cosa fa |
|---|---|
| `scripts/pyinstaller/entry_point.py` | Punto di ingresso del core pacchettizzato: fuori da `core/scriba_core/` perché quel pacchetto usa import relativi, validi solo se importato come pacchetto, non se PyInstaller parte da uno script interno. |
| `scripts/pyinstaller/scriba_core.spec` | Cosa impacchettare: hidden import, dati (schema.sql, modelli ONNX di preelaborazione), DLL native (onnxruntime, PortAudio, WinRT), esclusioni. |
| `scripts/build-core.ps1` | Wrapper che invoca PyInstaller con l'interprete giusto, bootstrap di pip/PyInstaller se mancano. |
| `ui/electron-builder.yml` | Config di electron-builder: NSIS, icona, `extraResources` per copiare l'eseguibile del core, nessuna firma. |
| `ui/main/sidecar.ts` | Trova ed avvia il core, in sviluppo o pacchettizzato — vedi sotto. |

## Come sidecar.ts trova il core nei due mondi

`index.ts` (fuori dal mio perimetro, non toccato) passa a `Sidecar` un
`projectRoot = resolve(app.getAppPath(), '..')`. Questo valore **cambia da
solo** fra sviluppo e pacchetto, senza che nessuno debba ricordarsene:

- **Sviluppo**: Electron parte da `ui/` (`electron .`), quindi
  `app.getAppPath()` è `ui/` e `projectRoot` è la radice `scriba/`. Il core si
  cerca in `core/.venv/Scripts/python.exe` e si avvia con
  `python -m scriba_core.server <db> --watch-parent`, esattamente come prima.
- **Pacchettizzato**: `app.getAppPath()` punta a `resources/app.asar`, quindi
  `projectRoot` diventa `resources/` — la cartella in cui
  `electron-builder.yml` copia `dist/core/scriba_core/` come
  `core-dist/scriba_core/`. Il core si cerca in
  `core-dist/scriba_core/scriba_core.exe` e si avvia direttamente (nessun
  `-m`: l'eseguibile PyInstaller *è* già l'interprete più il modulo).

`Sidecar.resolveCommand()` prova prima il percorso di sviluppo, poi quello
pacchettizzato, e solleva un errore chiaro se non trova né l'uno né l'altro.
Non c'è una riga da cambiare a mano passando da un mondo all'altro.

**Verificato**: con `core/.venv` presente (macchina di sviluppo) l'app
pacchettizzata e installata *non* lo trova comunque, perché `projectRoot` in
quel caso è dentro `AppData\Local\Programs\Scriba\resources\`, dove non
esiste una sottocartella `core`. Confermato leggendo `ExecutablePath` del
processo `scriba_core.exe` realmente in esecuzione dopo l'installazione: punta
a `...\resources\core-dist\scriba_core\scriba_core.exe`, non al venv.

## Un bug di packaging non ovvio: la sonda di rilevamento chiamate

`core/scriba_core/detect/call.py` isola in un processo separato le chiamate
COM che possono far morire il processo che le usa (vedi i commenti nel file:
`comtypes` a volte solleva un'eccezione non intercettabile). Lo fa così:

```python
subprocess.Popen([sys.executable, "-m", "scriba_core.detect.probe", str(self.intervallo_s)], ...)
```

Funziona in sviluppo perché `sys.executable` è un vero interprete Python, che
capisce `-m`. In un eseguibile PyInstaller, `sys.executable` è l'eseguibile
pacchettizzato stesso — che non è un interprete generico, è *solo* quello che
il suo entry point gli dice di fare. Senza rimedio, `-m scriba_core.detect.probe
2.0` sarebbe arrivato all'argparse del server come argomento sconosciuto,
l'exit code sarebbe stato 2 a ogni tentativo, e dopo 20 ripartenze fallite
(`CADUTE_CONSECUTIVE_MAX` in `call.py`) il rilevamento automatico delle
chiamate si sarebbe disattivato in silenzio — un difetto che non si vede
finché qualcuno non nota che l'app non propone più di registrare.

Non potendo toccare `core/scriba_core/`, il rimedio sta nell'unico file che
possiedo dentro quel confine: `scripts/pyinstaller/entry_point.py` riconosce
l'argomento `-m` ed emula il comportamento di `python -m` con `runpy`, in modo
generico (non solo per `detect.probe`, per qualunque modulo invocato allo
stesso modo in futuro). `scriba_core.detect.probe` va anche aggiunto agli
hidden import nello spec, perché è passato come stringa a `subprocess.Popen`,
non con un `import`: l'analisi statica di PyInstaller non lo troverebbe da
sola.

**Verificato**: `scriba_core.exe -m scriba_core.detect.probe 2.0` lanciato a
mano stampa righe JSON reali (`{"microfono": [...], "riproducono": [...]}`),
lo stesso output che produce in sviluppo.

## `core/.venv` è condiviso con altri task — attenzione al bloat

L'ambiente virtuale del core è lo stesso usato da chi sviluppa le altre
funzioni. Durante questo lavoro, mentre `core/.venv` veniva usato anche per
costruire il pacchetto, un altro task ci ha aggiunto la diarizzazione dei
partecipanti (`core/scriba_core/stt/diarizzazione.py`), che usa
`pyannote.audio` — e con lui l'intero stack PyTorch: `torch`, `lightning`,
`pandas`, `scikit-learn`, `matplotlib`, `sympy`, `optuna`, `sqlalchemy`,
`opentelemetry`. Il venv è passato da ~0,5 GB a **1,3 GB** (torch da solo,
527 MB). Una ricostruzione del core, senza ancora nessuna esclusione mirata,
è passata da 274 MB a **729 MB** senza che il resto del codice di
`scriba_core` fosse cambiato di una riga.

Due cause distinte, due rimedi:

1. `collect_all("onnxruntime")` include anche `onnxruntime.transformers` e
   `onnxruntime.quantization` — strumenti di conversione modelli, mai usati a
   runtime da Scriba — che a loro volta importano PyTorch *se PyTorch è
   disponibile nell'ambiente*. Con PyTorch assente quegli import fallivano in
   silenzio e PyInstaller li scartava; con PyTorch presente, li impacchetta
   per intero. Rimedio: tolti esplicitamente `onnxruntime.transformers`,
   `.quantization`, `.tools`, `.training` da quello che `collect_all` porta
   dentro.
2. La diarizzazione stessa non entra mai in gioco durante l'analisi statica
   di PyInstaller (gli import di `torch`/`pyannote.audio` in
   `diarizzazione.py` sono dentro i metodi, non in cima al file — è così che
   `Diarizzatore.disponibile()` può rispondere falso con grazia quando
   mancano), ma un `excludes` esplicito nello spec la esclude comunque per
   sicurezza: `torch`, `torchaudio`, `torchvision`, `torchcodec`, `pyannote`,
   `lightning`, `pytorch_lightning`, `pandas`, `sklearn`/`scikit-learn`,
   `matplotlib`, `sympy`, `optuna`, `sqlalchemy`, `alembic`, `opentelemetry`.

**È una lacuna dichiarata, non una svista**: la diarizzazione **non è
disponibile** nel pacchetto installato. `GET /diarizzazione/disponibile`
risponde `{"disponibile": false}` — verificato per davvero lanciando
l'eseguibile pacchettizzato — e il resto dell'applicazione continua
esattamente come progettato: «Io» e «Altri», senza eccezioni che risalgono.
Un installer da oltre un giga per una funzione facoltativa che gira solo a
call finita non sarebbe un installer, per lo stesso motivo per cui i modelli
AI stanno fuori.

**Misurato, con e senza l'esclusione** (stesso venv, stesso spec a parte
`excludes`):

| | Dimensione core pacchettizzato | Installer finale |
|---|---|---|
| Senza escludere PyTorch/pyannote | 729 MB | *(non costruito: gia' chiaro dal core)* |
| **Con l'esclusione (attuale)** | **288 MB** | **174 MB** |

Verificato dopo l'esclusione, su un'installazione reale: il core si avvia,
`/health` risponde `{"modello":"pronto"}` (la trascrizione, che usa
`onnxruntime`/`scipy`/`numpy` — **non** PyTorch — funziona), e
`/diarizzazione/disponibile` risponde `{"disponibile": false}` senza errori.

Se **davvero** un giorno la diarizzazione dovrà entrare nel pacchetto (es.
offerta come componente opzionale scaricabile a parte, sul modello dei
modelli LLM), questa lista va tolta di proposito — non scoperta perché il
pacchetto è cresciuto di un giga da un giorno all'altro.

## Dimensioni misurate

| Cosa | Dimensione |
|---|---|
| `dist/core/scriba_core/` (eseguibile PyInstaller onedir) | 288 MB |
| `ui/release/win-unpacked/` (app Electron scompattata) | 614 MB |
| `ui/release/Scriba Setup <versione>.exe` (installer NSIS, compresso) | 174 MB |
| Cartella di installazione finale (`%LOCALAPPDATA%\Programs\Scriba`) | ~614 MB |

Senza l'esclusione di PyTorch/pyannote (vedi sezione sul venv condiviso più
sopra), il solo core pacchettizzato sale a 729 MB.

Le voci più pesanti dentro il core pacchettizzato: `scipy` (~69 MB, per una
sola funzione — `resample_poly` in `audio/capture.py` — ma è quello che c'è),
`winsdk` (~42 MB, le proiezioni WinRT per l'OCR degli screenshot),
`onnxruntime` (~40 MB). Nessuna riguarda i modelli scaricati a runtime, che
restano fuori per definizione.

## Dati utente: dove stanno, e restano lì

`app.getPath('userData')` non dipende da come l'app è stata avviata (dev o
installata): dipende dal campo `name` di `ui/package.json` (`scriba-ui`), non
da `productName` di electron-builder (`Scriba`). Quindi in **entrambi** i
casi i dati stanno in `%APPDATA%\scriba-ui\data\` — mai dentro la cartella di
installazione, mai toccati da un aggiornamento o da una disinstallazione.

`electron-builder.yml` ha `deleteAppDataOnUninstall: false` esplicito (NSIS
di norma non tocca `%APPDATA%` comunque, ma è scritto per non lasciarlo
implicito).

**Verificato con un'installazione reale**, non solo letto dal codice:

1. Installer silenzioso (`/S`) su questa macchina → installa in
   `%LOCALAPPDATA%\Programs\Scriba\` (per-utente, `perMachine: false`, nessun
   prompt UAC).
2. Avviato `Scriba.exe` dall'installazione vera (non `npm run dev`): il core
   pacchettizzato si carica, `/health` risponde `{"ok":true,"modello":"pronto"}`.
3. **Test del processo orfano** (la preoccupazione esplicita del progetto,
   vedi i commenti in `sidecar.ts` e `models_manager.py`): ucciso a forza il
   processo Electron principale, per simulare un crash invece di una chiusura
   pulita. Risultato: sia i processi renderer che `scriba_core.exe` (compresa
   la sua copia del modello STT in RAM, ~830 MB) sono terminati da soli entro
   pochi secondi, grazie al meccanismo già esistente di `--watch-parent` (il
   core si accorge che lo stdin è stato chiuso e si spegne). Nessun processo
   rimasto ad occupare il microfono.
4. Disinstallato (`/S`): la cartella di installazione sparisce,
   `%APPDATA%\scriba-ui\data\scriba.sqlite` resta.

## Nessuna firma del codice

Decisione di progetto presa all'inizio (progetto personale, open source):
`win.signAndEditExecutable: false` in `electron-builder.yml`. Windows mostra
l'avviso di SmartScreen alla prima apertura dell'installer — atteso, non un
difetto. Verificato con `Get-AuthenticodeSignature` sull'installer prodotto:
`NotSigned` sia per `Scriba Setup <versione>.exe` sia per `Scriba.exe` dentro
`win-unpacked/`.

## Cosa resta da fare

- **Non testato**: registrazione audio vera end-to-end (mic + loopback) dal
  pacchetto installato — la verifica di questo lavoro si è fermata a
  "il core pacchettizzato parte, carica il modello, risponde su `/health`, e
  si spegne pulito col padre". Non ho aperto una call vera né premuto
  "Registra" dall'interfaccia installata: fuori dal perimetro di un task di
  packaging, ma vale la pena rifarlo una volta a mano prima di distribuire
  l'installer a qualcun altro.
- **Icona generica nella tray**: `main/index.ts` (fuori dal mio perimetro)
  disegna un'icona minimale a runtime invece di caricarne una vera — non
  legato al packaging, ma si nota di più in un pacchetto "finito".
- **`author` mancante in `ui/package.json`**: electron-builder lo segnala
  come warning non bloccante in ogni build. Aggiungerlo è una riga, ma tocca
  un campo di metadata condiviso: lasciato a chi possiede quel file per
  intero.
- Nessuno step di CI costruisce questo pacchetto automaticamente: per ora è
  un comando da lanciare a mano (`npm run dist`).
