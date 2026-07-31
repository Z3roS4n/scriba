/**
 * Processo principale di Scriba.
 *
 * Tiene insieme le finestre (principale, impostazioni, overlay), l'icona
 * nell'area di notifica, le scorciatoie globali e il processo core. La logica
 * vera — audio, trascrizione, database — sta tutta nel core: qui si aprono le
 * finestre e si inoltrano comandi.
 */

import { app, BrowserWindow, desktopCapturer, dialog, globalShortcut, ipcMain, Menu, nativeImage, screen, shell, Tray } from 'electron'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve, sep } from 'node:path'

import { Impostazioni } from './impostazioni'
import { Overlay } from './overlay'
import { Sidecar } from './sidecar'

const PROJECT_ROOT = resolve(app.getAppPath(), '..')
const DATA_DIR = join(app.getPath('userData'), 'data')
const SCREENSHOT_DIR = join(DATA_DIR, 'screenshots')
/**
 * L'icona dell'applicazione, dove sta sia in sviluppo che pacchettizzata.
 *
 * Lo stesso percorso relativo funziona in entrambi i casi perche' `PROJECT_ROOT`
 * risale di uno da `app.getAppPath()`: in sviluppo finisce sulla radice del
 * repository, pacchettizzato su `resources/`, dove electron-builder copia la
 * cartella `assets` (vedi extraResources in electron-builder.yml).
 *
 * L'eseguibile ha la sua icona incisa dentro da electron-builder; questa serve
 * alle finestre e all'area di notifica, che la caricano da file a runtime.
 */
const ICONA = join(PROJECT_ROOT, 'assets', 'scriba.ico')
/** Quadrato 16x16 disegnato a runtime: ripiego se `ICONA` non si carica. */
const ICONA_RIPIEGO =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAWklEQVR42mNkYPhfz0AEYBxVSF' +
  'ChpqbmPxCDaSA0MDAwMDIwMDAwMjAwMDIwMDAyMDAwMTAwMDMwMDCxMDAwsTIwMLEzMDCxMzAwcTAwMHEyMDBxMTAwcTMw' +
  'AABAAP//AwDPzB4hHVAAAAAASUVORK5CYII='
/**
 * Candidate per lo screenshot, in ordine di preferenza.
 *
 * Ripiego per quando le impostazioni non ne indicano una valida: Ctrl+Shift+S
 * e' la piu' naturale ma e' spesso gia' presa (Office, strumenti di cattura,
 * launcher), quindi si prova la prima libera invece di lasciare l'utente senza
 * scorciatoia.
 */
const SCREENSHOT_HOTKEYS = [
  'CommandOrControl+Shift+S',
  'CommandOrControl+Alt+S',
  'CommandOrControl+Shift+F9',
  'Alt+Shift+S',
]

const sidecar = new Sidecar(PROJECT_ROOT, join(DATA_DIR, 'scriba.sqlite'))

const cartellaRisorse = __dirname.replace(/[\\/]main$/, '')
const overlay = new Overlay(cartellaRisorse, join(DATA_DIR, 'overlay.json'))
const impostazioni = new Impostazioni(cartellaRisorse, ICONA)

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let quitting = false
let scorciatoiaOverlay: string | null = null
let scorciatoiaScreenshot: string | null = null
/**
 * Cartella di export scelta dall'utente con `scegliCartella`.
 *
 * E' l'unica eccezione al confine dei dati dell'app: sta fuori per
 * definizione, ma solo quella — non un percorso qualsiasi che il renderer
 * decida di mandare.
 */
let cartellaExportScelta: string | null = null

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 820,
    minHeight: 560,
    show: false,
    // Senza cornice: la barra del titolo la disegna il renderer, perche'
    // quella di Windows ignora il tema scuro.
    frame: false,
    backgroundColor: '#141416',
    title: 'Scriba',
    icon: ICONA,
    webPreferences: {
      preload: join(__dirname, 'preload.js'),
      // Il renderer non deve poter toccare il filesystem ne' avviare processi:
      // tutto quello che gli serve passa dal preload, che espone una superficie
      // ristretta e controllata.
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  win.loadFile(join(__dirname, '..', 'renderer', 'index.html'))
  win.once('ready-to-show', () => win.show())

  // Chiudere la finestra non chiude l'app: Scriba deve restare disponibile
  // nell'area di notifica per accorgersi delle call.
  win.on('close', (event) => {
    if (!quitting) {
      event.preventDefault()
      win.hide()
    }
  })

  // I link esterni non devono aprirsi dentro l'app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  return win
}

function showWindow(): void {
  if (!mainWindow) mainWindow = createWindow()
  mainWindow.show()
  mainWindow.focus()
}

function createTray(): void {
  // Il .ico contiene gia' un'immagine da 16 pixel disegnata a quella misura
  // (scripts/genera-icona.ps1): Windows sceglie quella invece di rimpicciolire
  // la grande, ed e' la differenza fra un'icona pulita e una sfocata proprio
  // nel posto dove Scriba passa la maggior parte del suo tempo.
  //
  // Se il file mancasse si ripiega sul quadrato disegnato a runtime che c'era
  // prima. Non e' eleganza: un'icona vuota nell'area di notifica e' invisibile,
  // e con la finestra che si nasconde invece di chiudersi quella e' l'unica
  // strada per riaprire Scriba. Meglio brutta che irraggiungibile.
  const daFile = nativeImage.createFromPath(ICONA)
  const icon = daFile.isEmpty() ? nativeImage.createFromDataURL(ICONA_RIPIEGO) : daFile
  tray = new Tray(icon)
  tray.setToolTip('Scriba')
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Apri Scriba', click: showWindow },
      {
        label: `Trascrizione sovrapposta (${(scorciatoiaOverlay ?? 'Alt+R').replace('CommandOrControl', 'Ctrl')})`,
        click: () => overlay.alterna(),
      },
      { type: 'separator' },
      {
        label: scorciatoiaScreenshot
          ? `Screenshot (${scorciatoiaScreenshot.replace('CommandOrControl', 'Ctrl')})`
          : 'Screenshot',
        click: captureScreenshot,
      },
      { type: 'separator' },
      {
        label: 'Esci',
        click: () => {
          quitting = true
          app.quit()
        },
      },
    ]),
  )
  tray.on('double-click', showWindow)
}

/** Chiamata al core, con il token che solo questo processo conosce. */
async function coreFetch(path: string, init?: RequestInit): Promise<Response> {
  const endpoint = sidecar.address
  if (!endpoint) throw new Error('Il core non e\' pronto')
  const separator = path.includes('?') ? '&' : '?'
  return fetch(`${sidecar.baseUrl}${path}${separator}token=${endpoint.token}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
}

/** Le impostazioni correnti del core, o null se non sono leggibili. */
async function leggiImpostazioni(): Promise<Record<string, any> | null> {
  try {
    const risposta = await coreFetch('/settings')
    return risposta.ok ? await risposta.json() : null
  } catch {
    return null
  }
}

/** Manda un evento a tutte le finestre aperte: principale, impostazioni, overlay. */
function trasmettiATutte(canale: string, payload: unknown): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send(canale, payload)
  }
}

/** Il renderer resta dentro i dati dell'app, tranne l'unica cartella di export scelta. */
function dentroCartella(percorso: string, base: string): boolean {
  const risolto = resolve(percorso)
  const baseRisolta = resolve(base)
  return risolto === baseRisolta || risolto.startsWith(baseRisolta + sep)
}

/**
 * Cattura lo schermo e lo aggancia all'istante corrente della call.
 *
 * L'istante non lo calcola questo processo: lo decide il core, che possiede la
 * timeline della trascrizione. Due orologi diversi darebbero uno scarto che non
 * si nota finche' non si prova a saltare all'audio da uno screenshot.
 */
async function captureScreenshot(): Promise<void> {
  try {
    const { width, height } = screen.getPrimaryDisplay().size
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: { width, height },
    })
    if (sources.length === 0) return

    mkdirSync(SCREENSHOT_DIR, { recursive: true })
    const image = sources[0].thumbnail
    const filename = `shot-${Date.now()}.png`
    const path = join(SCREENSHOT_DIR, filename)
    writeFileSync(path, image.toPNG())

    const response = await coreFetch('/session/screenshot', {
      method: 'POST',
      body: JSON.stringify({ path, width: image.getSize().width, height: image.getSize().height }),
    })

    if (response.ok) {
      const { t_ms } = await response.json()
      // Anche all'overlay: e' li' che si vede il lampo "Salvato nella
      // trascrizione" mentre si e' ancora in call.
      trasmettiATutte('screenshot:saved', { path, t_ms })
    } else if (response.status === 409) {
      // Nessuna registrazione in corso: lo screenshot non ha un istante a cui
      // agganciarsi, quindi non serve a niente. Meglio dirlo che salvarlo e
      // basta.
      trasmettiATutte('screenshot:ignorato', undefined)
    }
  } catch (error) {
    console.error('[screenshot]', error)
  }
}

/**
 * Resta in ascolto degli eventi del core e li gira a tutte le finestre.
 *
 * La connessione la tiene questo processo, non il renderer: il token non deve
 * mai arrivare alla pagina, altrimenti chiunque riesca a iniettare uno script
 * puo' parlare col core in autonomia. Anche le impostazioni ascoltano questo
 * canale: e' da li' che arriva l'avanzamento dei download dei modelli.
 */
function connectEvents(): void {
  const endpoint = sidecar.address
  if (!endpoint) return

  const socket = new WebSocket(`ws://127.0.0.1:${endpoint.port}/ws?token=${endpoint.token}`)

  socket.addEventListener('message', (event) => {
    try {
      const evento = JSON.parse(String(event.data))
      trasmettiATutte('core:event', evento)
    } catch (error) {
      console.error('[core] evento illeggibile', error)
    }
  })

  socket.addEventListener('close', () => {
    // Se il core e' ancora vivo la connessione va ristabilita, altrimenti si
    // smette di vedere la trascrizione senza che nulla lo segnali.
    if (sidecar.address && !quitting) setTimeout(connectEvents, 1_000)
  })

  socket.addEventListener('error', () => socket.close())
}

/**
 * Rilegge scorciatoia dell'overlay e dello screenshot dalle impostazioni e le
 * registra, disiscrivendo prima quelle attive.
 *
 * Restituisce le combinazioni effettivamente attive (null se il sistema le ha
 * rifiutate): e' quello che il campo delle impostazioni deve mostrare, non
 * quello che si e' provato a registrare.
 */
async function registraScorciatoie(): Promise<{ overlay: string | null; screenshot: string | null }> {
  if (scorciatoiaOverlay) {
    globalShortcut.unregister(scorciatoiaOverlay)
    scorciatoiaOverlay = null
  }
  if (scorciatoiaScreenshot) {
    globalShortcut.unregister(scorciatoiaScreenshot)
    scorciatoiaScreenshot = null
  }

  const impostazioniLette = await leggiImpostazioni()
  const comboOverlay: string = impostazioniLette?.interfaccia?.scorciatoia_overlay || 'Alt+R'
  const comboScreenshot: string = impostazioniLette?.interfaccia?.scorciatoia_screenshot || ''

  if (globalShortcut.register(comboOverlay, () => overlay.alterna())) {
    scorciatoiaOverlay = comboOverlay
  } else {
    console.warn(`Scorciatoia ${comboOverlay} gia' in uso: overlay non richiamabile da tastiera.`)
  }

  if (comboScreenshot && globalShortcut.register(comboScreenshot, captureScreenshot)) {
    scorciatoiaScreenshot = comboScreenshot
  } else {
    // Le impostazioni non indicano una combinazione valida: si prova la lista
    // di ripiego invece di lasciare lo screenshot senza scorciatoia.
    for (const combo of SCREENSHOT_HOTKEYS) {
      if (globalShortcut.register(combo, captureScreenshot)) {
        scorciatoiaScreenshot = combo
        break
      }
    }
    if (!scorciatoiaScreenshot) {
      console.warn('Nessuna scorciatoia disponibile per lo screenshot: sono tutte gia\' in uso.')
    }
  }

  const stato = { overlay: scorciatoiaOverlay, screenshot: scorciatoiaScreenshot }
  // Il testo che le mostra (menu della tray, campo nelle impostazioni) deve
  // restare vero.
  trasmettiATutte('scorciatoie:stato', stato)
  if (tray) createTray()
  return stato
}

/**
 * Prova a registrare una combinazione senza salvarla, poi rimette le cose
 * com'erano.
 *
 * Se la combinazione e' gia' una di quelle che teniamo noi (l'utente sta
 * testando un valore uguale a quello gia' attivo su un altro campo, o non lo
 * sta cambiando affatto) non si tocca la registrazione reale: disiscriverla
 * dopo il test la toglierebbe per davvero, lasciando quella scorciatoia senza
 * effetto finche' non si rilancia l'app.
 */
async function provaScorciatoia(combinazione: string): Promise<boolean> {
  if (combinazione === scorciatoiaOverlay || combinazione === scorciatoiaScreenshot) return true

  const riuscita = globalShortcut.register(combinazione, () => {})
  if (riuscita) globalShortcut.unregister(combinazione)
  return riuscita
}

function registerIpc(): void {
  // Volutamente senza token: al renderer basta sapere se il core e' su.
  ipcMain.handle('core:endpoint', () => (sidecar.address ? { port: sidecar.address.port } : null))

  ipcMain.handle('core:request', async (_event, path: string, init?: { method?: string; body?: string }) => {
    // L'interfaccia puo' interrogare il core prima che sia partito (la finestra
    // si apre subito, il sidecar no): coreFetch lancia in quel caso, ma il
    // ponte promette sempre {ok, status, body}, mai una promessa rifiutata.
    // 503 e' lo stato che dice "non ancora disponibile", non un errore del core.
    if (!sidecar.address) {
      return { ok: false, status: 503, body: null }
    }
    const response = await coreFetch(path, init)
    const text = await response.text()
    return {
      ok: response.ok,
      status: response.status,
      body: text ? JSON.parse(text) : null,
    }
  })

  ipcMain.handle('screenshot:capture', captureScreenshot)

  ipcMain.handle('file:mostra', (_event, percorso: string) => {
    // Solo dentro la cartella dati dell'app: il renderer non deve poter far
    // aprire un percorso qualsiasi del disco.
    if (!dentroCartella(percorso, DATA_DIR)) {
      throw new Error('Percorso fuori dalla cartella dati')
    }
    shell.showItemInFolder(resolve(percorso))
  })

  ipcMain.handle('cartella:apri', async (_event, percorso: string) => {
    // Come file:mostra, ma per cartelle: dentro i dati dell'app, o l'unica
    // cartella di export che l'utente ha appena scelto.
    const consentito =
      dentroCartella(percorso, DATA_DIR) ||
      (cartellaExportScelta !== null && dentroCartella(percorso, cartellaExportScelta))
    if (!consentito) {
      throw new Error('Percorso non consentito')
    }
    await shell.openPath(resolve(percorso))
  })

  ipcMain.handle('cartella:scegli', async (event) => {
    const finestraChiamante = BrowserWindow.fromWebContents(event.sender) ?? mainWindow ?? undefined
    const risultato = await dialog.showOpenDialog(finestraChiamante!, { properties: ['openDirectory'] })
    if (risultato.canceled || risultato.filePaths.length === 0) return null
    // Si memorizza: e' l'unico percorso fuori dai dati dell'app che
    // cartella:apri accettera' in seguito.
    cartellaExportScelta = risultato.filePaths[0]
    return cartellaExportScelta
  })

  ipcMain.handle('app:paths', () => ({ dataDir: DATA_DIR, screenshotDir: SCREENSHOT_DIR }))

  // Comandi della barra del titolo: le finestre sono senza cornice, quindi
  // ridurre, ingrandire e chiudere vanno rifatti a mano. Agiscono sulla
  // finestra che ha mandato il messaggio, non su una variabile globale: le
  // finestre sono piu' di una.
  ipcMain.handle('finestra:riduci', (event) => {
    BrowserWindow.fromWebContents(event.sender)?.minimize()
  })

  ipcMain.handle('finestra:ingrandisci', (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return
    if (win.isMaximized()) win.unmaximize()
    else win.maximize()
  })

  ipcMain.handle('finestra:chiudi', (event) => {
    // Sulla finestra principale questo richiama lo stesso 'close' che gia'
    // nasconde invece di uscire: e' lo stesso evento nativo, solo innescato a
    // mano invece che dal sistema.
    BrowserWindow.fromWebContents(event.sender)?.close()
  })

  ipcMain.handle('impostazioni:apri', () => {
    impostazioni.apri()
  })

  ipcMain.handle('overlay:nascondi', () => overlay.nascondi())

  ipcMain.handle('overlay:apri-principale', () => {
    showWindow()
  })

  ipcMain.handle('overlay:alterna-ridotto', async () => {
    const nuovo = overlay.alternaRidotto()
    try {
      // E' una preferenza, non uno stato di sessione: va ricordata anche dopo
      // aver chiuso l'applicazione.
      await coreFetch('/settings', {
        method: 'POST',
        body: JSON.stringify({ interfaccia: { overlay_ridotto: nuovo } }),
      })
    } catch {
      // La preferenza non si e' salvata, ma la finestra ha comunque cambiato
      // variante: non vale la pena bloccare l'utente per questo.
    }
    return nuovo
  })

  ipcMain.handle('scorciatoie:registra', registraScorciatoie)

  ipcMain.handle('scorciatoie:prova', (_event, combinazione: string) => provaScorciatoia(combinazione))
}

// Due copie dell'app aperte insieme sono due core sullo stesso database, ed e'
// uno dei modi in cui si perde una call: il WAL di uno viene azzerato mentre
// l'altro lo sta ancora usando. La seconda istanza porta davanti la prima e si
// chiude, invece di aprire una finestra che sembra innocua.
const solaIstanza = app.requestSingleInstanceLock()
if (!solaIstanza) app.quit()

app.on('second-instance', () => showWindow())

app.whenReady().then(async () => {
  if (!solaIstanza) return
  mkdirSync(DATA_DIR, { recursive: true })
  registerIpc()
  mainWindow = createWindow()
  createTray()

  try {
    const endpoint = await sidecar.start()
    connectEvents()
    trasmettiATutte('core:pronto', { port: endpoint.port })

    // La scorciatoie si leggono dalle impostazioni, che stanno nel core: si
    // registrano solo dopo che e' partito.
    await registraScorciatoie()

    // Idem per la variante dell'overlay: va applicata prima che la finestra si
    // apra la prima volta, altrimenti si vedrebbe un lampo alla dimensione
    // sbagliata.
    const impostazioniLette = await leggiImpostazioni()
    overlay.impostaVariante(Boolean(impostazioniLette?.interfaccia?.overlay_ridotto))
  } catch (error) {
    dialog.showErrorBox(
      'Scriba non riesce ad avviare il core',
      error instanceof Error ? error.message : String(error),
    )
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) showWindow()
})

app.on('before-quit', () => {
  quitting = true
})

let spegnendo = false

app.on('will-quit', (evento) => {
  globalShortcut.unregisterAll()
  overlay.chiudi()
  if (spegnendo) return

  // Si trattiene la chiusura per il tempo che serve al core a consolidare il
  // database: ucciderlo a meta' lascia l'ultima call nel solo WAL, che e'
  // esattamente come la si perde.
  spegnendo = true
  evento.preventDefault()
  sidecar.stop().finally(() => app.exit(0))
})

// Su Windows chiudere tutte le finestre non deve chiudere l'app: resta nell'area
// di notifica.
app.on('window-all-closed', () => {
  if (process.platform === 'darwin') return
})
