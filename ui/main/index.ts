/**
 * Processo principale di Scriba.
 *
 * Tiene insieme la finestra, l'icona nell'area di notifica, la scorciatoia per
 * gli screenshot e il processo core. La logica vera — audio, trascrizione,
 * database — sta tutta nel core: qui si apre una finestra e si inoltrano
 * comandi.
 */

import { app, BrowserWindow, desktopCapturer, dialog, globalShortcut, ipcMain, Menu, nativeImage, screen, shell, Tray } from 'electron'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

import { Sidecar } from './sidecar'

const PROJECT_ROOT = resolve(app.getAppPath(), '..')
const DATA_DIR = join(app.getPath('userData'), 'data')
const SCREENSHOT_DIR = join(DATA_DIR, 'screenshots')
/**
 * Candidate per lo screenshot, in ordine di preferenza.
 *
 * Ctrl+Shift+S e' la piu' naturale ma e' spesso gia' presa (Office, strumenti di
 * cattura, launcher): si prova la prima libera invece di rinunciare, perche' una
 * scorciatoia che non fa niente e' peggio di una scomoda.
 */
const SCREENSHOT_HOTKEYS = [
  'CommandOrControl+Shift+S',
  'CommandOrControl+Alt+S',
  'CommandOrControl+Shift+F9',
  'Alt+Shift+S',
]
let hotkeyAttiva: string | null = null

const sidecar = new Sidecar(PROJECT_ROOT, join(DATA_DIR, 'scriba.sqlite'))

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let quitting = false

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 820,
    minHeight: 560,
    show: false,
    backgroundColor: '#0f1115',
    title: 'Scriba',
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
  // Icona minimale disegnata a runtime: evita di trascinarsi dietro un asset
  // binario finche' non c'e' un'identita' visiva decisa.
  const icon = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAWklEQVR42mNkYPhfz0AEYBxVSF' +
      'ChpqbmPxCDaSA0MDAwMDIwMDAwMjAwMDIwMDAyMDAwMTAwMDMwMDCxMDAwsTIwMLEzMDCxMzAwcTAwMHEyMDBxMTAwcTMw' +
      'AABAAP//AwDPzB4hHVAAAAAASUVORK5CYII=',
  )
  tray = new Tray(icon)
  tray.setToolTip('Scriba')
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Apri Scriba', click: showWindow },
      { type: 'separator' },
      {
        label: hotkeyAttiva
          ? `Screenshot (${hotkeyAttiva.replace('CommandOrControl', 'Ctrl')})`
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
      mainWindow?.webContents.send('screenshot:saved', { path, t_ms })
    } else if (response.status === 409) {
      // Nessuna registrazione in corso: lo screenshot non ha un istante a cui
      // agganciarsi, quindi non serve a niente. Meglio dirlo che salvarlo e
      // basta.
      mainWindow?.webContents.send('screenshot:ignorato')
    }
  } catch (error) {
    console.error('[screenshot]', error)
  }
}

/**
 * Resta in ascolto degli eventi del core e li gira alla finestra.
 *
 * La connessione la tiene questo processo, non il renderer: il token non deve
 * mai arrivare alla pagina, altrimenti chiunque riesca a iniettare uno script
 * puo' parlare col core in autonomia.
 */
function connectEvents(): void {
  const endpoint = sidecar.address
  if (!endpoint) return

  const socket = new WebSocket(`ws://127.0.0.1:${endpoint.port}/ws?token=${endpoint.token}`)

  socket.addEventListener('message', (event) => {
    try {
      mainWindow?.webContents.send('core:event', JSON.parse(String(event.data)))
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

function registerIpc(): void {
  // Volutamente senza token: al renderer basta sapere se il core e' su.
  ipcMain.handle('core:endpoint', () => (sidecar.address ? { port: sidecar.address.port } : null))

  ipcMain.handle('core:request', async (_event, path: string, init?: { method?: string; body?: string }) => {
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
    const risolto = resolve(percorso)
    if (!risolto.startsWith(DATA_DIR)) {
      throw new Error('Percorso fuori dalla cartella dati')
    }
    shell.showItemInFolder(risolto)
  })

  ipcMain.handle('app:paths', () => ({ dataDir: DATA_DIR, screenshotDir: SCREENSHOT_DIR }))
}

app.whenReady().then(async () => {
  mkdirSync(DATA_DIR, { recursive: true })
  registerIpc()
  mainWindow = createWindow()

  // Prima della tray: il menu mostra la combinazione effettivamente attiva.
  for (const combo of SCREENSHOT_HOTKEYS) {
    if (globalShortcut.register(combo, captureScreenshot)) {
      hotkeyAttiva = combo
      break
    }
  }
  createTray()

  mainWindow.webContents.once('did-finish-load', () => {
    mainWindow?.webContents.send('hotkey:stato', hotkeyAttiva)
  })
  if (!hotkeyAttiva) {
    console.warn('Nessuna scorciatoia disponibile: sono tutte gia\' in uso.')
  }

  try {
    const endpoint = await sidecar.start()
    connectEvents()
    mainWindow.webContents.send('core:pronto', { port: endpoint.port })
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

app.on('will-quit', () => {
  globalShortcut.unregisterAll()
  sidecar.stop()
})

// Su Windows chiudere tutte le finestre non deve chiudere l'app: resta nell'area
// di notifica.
app.on('window-all-closed', () => {
  if (process.platform === 'darwin') return
})
