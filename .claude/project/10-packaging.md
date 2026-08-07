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

## Versione: una sola, in `ui/package.json`

Da lì la leggono electron-builder (nome dell'artefatto, proprietà del file su
Windows, chiave di disinstallazione), il processo principale via
`app.getVersion()`, e — attraverso l'ambiente del sidecar — il core, che la
riporta in `/health`. Una seconda copia da qualche parte vorrebbe dire vederle
divergere, e il modo in cui questo tipo di errore si scopre è leggere un log e
non sapere a quale build appartiene.

Si alza con `scripts/versione.ps1` (`patch` | `minore` | `maggiore`, oppure un
numero esatto), che riscrive **solo quel campo** con una regex invece di
riserializzare il JSON: `ConvertTo-Json` riordinerebbe le chiavi e il diff
diventerebbe l'intero file.

**Non si alza a ogni build.** Durante lo sviluppo se ne fanno molte con lo
stesso numero, ed è proprio lì che serve distinguerle: a farlo è il commit, che
`npm run build` scrive in `dist/versione.json` insieme alla data e a un flag
`pulito` che dice se l'albero aveva modifiche non salvate. Se git non risponde
il commit resta `null` — un valore inventato sarebbe peggio di uno assente.

Per anni la versione è stata `0.1.0` su una ventina di installer diversi (#48):
il numero è ripartito da `0.5.0`, che riflette dov'è il prodotto invece di dove
era il primo giorno.

### Ogni fix esce come release

Regola di progetto (vedi `AGENTS.md`): un fix in `main` diventa una release su GitHub.
Il numero si alza **nella PR del fix** — su `main` non si committa — e insieme al numero
si scrive la voce nei due changelog.

**Il changelog non sta nella descrizione della release** ma in `CHANGELOG.md` (inglese) e
`CHANGELOG.it.md` (italiano): una descrizione su GitHub non si cerca, non entra in un
diff e non si trova guardando il repository. La descrizione si limita a due righe e ai
collegamenti, che `scripts/rilascia.ps1` genera da solo puntando al tag appena creato —
non a `main`, così restano quelli di quella versione anche quando i file cambiano.

Le sezioni sono tre (`### Breaking changes`, `### New features`, `### Fixes`) ed è la più
alta con delle voci a decidere lo scatto. Lo script **confronta lo scatto dichiarato con
quello fatto** e si ferma se non coincidono: senza quel controllo la classificazione
diventa decorativa, e un numero che non riflette cosa c'è dentro è peggio di nessun
numero. Controlla anche che **entrambe** le lingue abbiano la voce.

L'installer viene allegato. Non è firmato, e questo va scritto nel changelog: chi scarica
incontra l'avviso di SmartScreen e deve sapere perché. `-SenzaInstaller` lo esclude.

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
nessun certificato configurato in `electron-builder.yml`. Windows mostra
l'avviso di SmartScreen alla prima apertura dell'installer — atteso, non un
difetto. Verificato con `Get-AuthenticodeSignature` sull'installer prodotto:
`NotSigned` sia per `Scriba Setup <versione>.exe` sia per `Scriba.exe` dentro
`win-unpacked/`.

**Come NON si esprime questa decisione:** con `win.signAndEditExecutable:
false`, che è quello che c'era scritto fino alla issue dell'icona. Quel flag
non spegne solo la firma, spegne l'intero passaggio che riscrive
l'eseguibile — lo stesso che ci incide dentro icona, nome prodotto, versione
e autore. Con `false` l'`.exe` restava con l'icona di Electron e senza
identità in Gestione attività, e il campo `win.icon` poco sopra veniva
ignorato in silenzio.

Ora sta a `true` (il predefinito). electron-builder scrive icona e metadati, e
firma **solo** se trova un certificato: non essendocene nessuno, non firma. La
decisione di partenza è intatta, il pacchetto ha la sua faccia.

## Icona

`assets/scriba.ico` contiene sette misure (16, 24, 32, 48, 64, 128, 256), non
una sola: Windows sceglie quella giusta invece di rimpicciolire la più grande,
e sotto i 32 pixel — area di notifica, barra delle applicazioni — la differenza
si vede. Si rigenera da `assets/scriba.png` con
`powershell -ExecutionPolicy Bypass -File scripts/genera-icona.ps1`, a mano
quando il logo cambia: il `.ico` prodotto sta nel repository, così chi
costruisce l'installer non deve rigenerarlo.

**L'area di notifica è un'altra cosa.** `assets/tray/` contiene quattro `.ico`
disegnati per i 16 pixel, non il logo rimpicciolito: inchiostro chiaro o scuro
a seconda della **barra** (non del tema di Scriba), e un anello che si riempie
di rosso solo mentre si registra. Si rigenerano con
`scripts/genera-icona-tray.ps1`, e sono scritti con immagini **BMP** invece che
PNG: sotto i 48 pixel è la forma che tutto sa leggere, ed è anche ciò che
rende quelle icone verificabili da uno script invece che solo a occhio.

L'icona serve in due posti diversi, e sono due meccanismi distinti:

| Dove | Da cosa arriva |
|---|---|
| `.exe` (Esplora risorse, Gestione attività, barra) | `win.icon` inciso da electron-builder |
| Finestre e area di notifica | file letto a runtime, via `extraResources` |

Il secondo passa da `ICONA` in `main/index.ts`, che è
`join(PROJECT_ROOT, 'assets', 'scriba.ico')`. Lo stesso percorso vale in
sviluppo e nel pacchetto perché `PROJECT_ROOT` risale di uno da
`app.getAppPath()`: in sviluppo cade sulla radice del repository,
pacchettizzato su `resources/`, dove `extraResources` copia `assets/`. Stesso
trucco di `core-dist`.

## Grafica dell'installer

Sta in `ui/build-resources/`, che è quello che `directories.buildResources`
indica. electron-builder li prende **per convenzione dal nome**: non serve
dichiararli, basta che si chiamino così e siano della misura giusta.

| File | Misura | Dove si vede |
|---|---|---|
| `installerHeader.bmp` | 150×57 | barra in alto di ogni pagina |
| `installerSidebar.bmp` | 164×314 | pagine di benvenuto e di fine |
| `uninstallerSidebar.bmp` | 164×314 | le stesse, disinstallando |
| `installerIcon.ico` / `uninstallerIcon.ico` | — | i due eseguibili |
| `license.txt` | — | pagina della licenza (copia di `LICENSE`) |

Si rigenera tutto con
`powershell -ExecutionPolicy Bypass -File scripts/genera-grafica-installer.ps1`,
a mano quando cambia il logo. I colori non sono scelti a occhio: sono
campionati da `assets/scriba.png` (punto `#F0605F`, disco `#171A21`).

Tre vincoli che lo script rispetta e che è facile violare rifacendo la grafica
a mano:

1. **I BMP a 24 bit.** NSIS non legge il canale alfa: un BMP a 32 bit si vede
   con lo sfondo nero o sporco.
2. **L'intestazione chiara.** La barra in alto di MUI2 è bianca di sistema e
   quel colore non si cambia. Una grafica scura lì dentro diventa un rettangolo
   nero incollato sul bianco. Il pannello laterale invece occupa tutto il
   riquadro, e lì il tema scuro del prodotto ci sta.
3. **Antialiasing in scala di grigi, non ClearType.** ClearType usa i
   sottopixel dello schermo e lascia frange colorate *dentro il file*:
   invisibili a dimensione naturale, evidenti appena NSIS scala il bitmap su
   uno schermo ad alta densità.

**Verificato**: l'icona estratta da `Scriba Setup <versione>.exe` è quella di
Scriba, e `builder-debug.yml` mostra `MUI_PAGE_LICENSE` con il percorso di
`build-resources/license.txt`. **Non verificato**: che i tre BMP si vedano
davvero nelle pagine. NSIS li impacchetta nel blocco compresso, quindi non si
leggono dal file prodotto; l'unico modo è aprire l'installer e guardarlo.

## Cosa resta da fare

- **Non testato**: registrazione audio vera end-to-end (mic + loopback) dal
  pacchetto installato — la verifica di questo lavoro si è fermata a
  "il core pacchettizzato parte, carica il modello, risponde su `/health`, e
  si spegne pulito col padre". Non ho aperto una call vera né premuto
  "Registra" dall'interfaccia installata: fuori dal perimetro di un task di
  packaging, ma vale la pena rifarlo una volta a mano prima di distribuire
  l'installer a qualcun altro.
- **Verificare l'icona sul pacchetto vero**, non solo in sviluppo: che
  `Scriba.exe` la mostri in Esplora risorse e in Gestione attività, e che la
  finestra e l'area di notifica la carichino da `resources/assets/`. È il
  punto in cui questa catena può rompersi in silenzio, perché in sviluppo
  `assets/` c'è comunque.
- Nessuno step di CI costruisce questo pacchetto automaticamente: per ora è
  un comando da lanciare a mano (`npm run dist`).
