/**
 * Processo principale di Scriba.
 *
 * Tiene insieme le finestre (principale, impostazioni, overlay), l'icona
 * nell'area di notifica, le scorciatoie globali e il processo core. La logica
 * vera — audio, trascrizione, database — sta tutta nel core: qui si aprono le
 * finestre e si inoltrano comandi.
 */

import { app, BrowserWindow, desktopCapturer, dialog, globalShortcut, ipcMain, Menu, nativeImage, nativeTheme, screen, shell, Tray } from 'electron'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
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
const impostazioni = new Impostazioni(cartellaRisorse, ICONA, () => coloreDiFondo())

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

/**
 * Il tema salvato, letto dal disco.
 *
 * Da `settings.json` e non dal core: serve prima che una finestra esista, e il
 * core a quel punto non e' ancora partito. E' anche l'unico posto in cui questo
 * processo legge le impostazioni per conto suo — vale la pena, perche' il
 * colore di fondo va deciso al momento della creazione della finestra, non
 * dopo.
 */
function temaSalvato(): string {
  try {
    const dati = JSON.parse(readFileSync(join(DATA_DIR, 'settings.json'), 'utf-8'))
    const tema = dati?.interfaccia?.tema
    return tema === 'chiaro' || tema === 'sistema' ? tema : 'scuro'
  } catch {
    // Prima installazione, o file illeggibile: lo stesso predefinito del core.
    return 'scuro'
  }
}

/** Il colore che Windows dipinge prima che la pagina esista. */
function coloreDiFondo(tema: string = temaSalvato()): string {
  const chiaro =
    tema === 'chiaro' || (tema === 'sistema' && !nativeTheme.shouldUseDarkColors)
  // Gli stessi due valori di `--win` in tokens.css: se divergono, l'apertura
  // di ogni finestra comincia con un lampo del colore sbagliato.
  return chiaro ? '#FFFFFF' : '#141416'
}

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
    backgroundColor: coloreDiFondo(),
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

/**
 * La voce «Screenshot» del menu: una sola con un solo schermo, un sottomenu con
 * piu' di uno.
 *
 * Con un monitor solo un sottomenu da una voce sarebbe un clic in piu' per
 * niente, ed e' il caso di quasi tutti: il menu cambia forma solo quando c'e'
 * davvero qualcosa da scegliere.
 */
function voceScreenshot(): Electron.MenuItemConstructorOptions[] {
  const combo = scorciatoiaScreenshot?.replace('CommandOrControl', 'Ctrl')
  const schermi = elencaSchermi()

  if (schermi.length <= 1) {
    return [{ label: combo ? `Screenshot (${combo})` : 'Screenshot', click: () => captureScreenshot() }]
  }

  return [
    {
      label: 'Screenshot',
      submenu: schermi.map((s) => ({
        // La scorciatoia si scrive solo accanto al principale perche' e' quello
        // che cattura davvero: scriverla su tutti prometterebbe il falso.
        label:
          `${s.etichetta} — ${s.larghezza}×${s.altezza}` +
          (s.principale ? (combo ? ` (principale, ${combo})` : ' (principale)') : ''),
        click: () => captureScreenshot(s.id),
      })),
    },
  ]
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
      ...voceScreenshot(),
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

/** Uno schermo su cui si puo' catturare, come lo vede l'interfaccia. */
type Schermo = {
  /** `Display.id` in forma di stringa: e' cosi' che lo riporta desktopCapturer. */
  id: string
  etichetta: string
  larghezza: number
  altezza: number
  principale: boolean
}

/**
 * Gli schermi collegati adesso, in ordine.
 *
 * L'etichetta la costruiamo noi. Windows riempie `Display.label` in modo
 * inservibile — spesso vuoto, spesso `\\.\DISPLAY1` — e su un pulsante ci serve
 * qualcosa che una persona possa collegare a quello che ha davanti.
 */
function elencaSchermi(): Schermo[] {
  const idPrincipale = screen.getPrimaryDisplay().id
  return screen.getAllDisplays().map((d, i) => ({
    id: String(d.id),
    etichetta: `Schermo ${i + 1}`,
    larghezza: Math.round(d.size.width * d.scaleFactor),
    altezza: Math.round(d.size.height * d.scaleFactor),
    principale: d.id === idPrincipale,
  }))
}

/**
 * Cattura uno schermo e lo aggancia all'istante corrente della call.
 *
 * L'istante non lo calcola questo processo: lo decide il core, che possiede la
 * timeline della trascrizione. Due orologi diversi darebbero uno scarto che non
 * si nota finche' non si prova a saltare all'audio da uno screenshot.
 *
 * Senza `idSchermo` si cattura il principale, che e' anche quello che fa la
 * scorciatoia globale: da tastiera non si puo' scegliere, e cambiare schermo da
 * sotto i piedi a chi preme sempre lo stesso tasto sarebbe peggio del limite.
 */
async function captureScreenshot(idSchermo?: string): Promise<void> {
  try {
    const schermi = screen.getAllDisplays()
    const scelto = schermi.find((d) => String(d.id) === idSchermo) ?? screen.getPrimaryDisplay()

    // Pixel veri, non unita' logiche. Su uno schermo scalato al 150% `size` e'
    // gia' diviso per la scala: chiedere quella misura darebbe una cattura a un
    // terzo di risoluzione in meno, e il testo dentro — che poi passa per l'OCR
    // e finisce nell'analisi — diventa quello che si legge peggio.
    const larghezza = Math.round(scelto.size.width * scelto.scaleFactor)
    const altezza = Math.round(scelto.size.height * scelto.scaleFactor)

    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: { width: larghezza, height: altezza },
    })
    if (sources.length === 0) return

    // `display_id` e' l'unico appiglio affidabile. La posizione nell'elenco non
    // lo e': misurato su due monitor, `getSources()` li restituisce in ordine
    // inverso rispetto a `getAllDisplays()` — chi si fidasse dell'indice
    // catturerebbe l'altro schermo, senza accorgersene.
    //
    // Se `display_id` mancasse (non succede su Windows con Electron 39, ma non
    // e' garantito da contratto) si ripiega sul primo, che e' quello che questa
    // funzione ha sempre catturato: non e' la scelta chiesta, e per questo lo si
    // scrive nel log invece di far finta di niente.
    const perId = sources.find((s) => s.display_id === String(scelto.id))
    if (!perId) {
      console.warn(
        `[screenshot] Nessuna sorgente per lo schermo ${scelto.id}: catturo la prima disponibile.`,
      )
    }
    const sorgente = perId ?? sources[0]

    mkdirSync(SCREENSHOT_DIR, { recursive: true })
    const image = sorgente.thumbnail
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

/**
 * Tiene allineato l'elenco degli schermi a quelli davvero collegati.
 *
 * Un monitor si attacca e si stacca a meta' giornata, e in call succede piu'
 * che altrove: ci si collega alla dock, si aggiunge un proiettore. Senza questo,
 * i pulsanti resterebbero quelli di quando l'app e' partita, e uno di loro
 * catturerebbe uno schermo che non c'e' piu'.
 *
 * Si registra dopo `app.whenReady()`: il modulo `screen` prima non e' pronto.
 */
function sorvegliaSchermi(): void {
  const aggiorna = () => {
    if (tray) createTray()
    trasmettiATutte('schermi:cambiati', elencaSchermi())
  }
  screen.on('display-added', aggiorna)
  screen.on('display-removed', aggiorna)
  // Cambia anche la risoluzione o la scalatura, non solo il numero: la misura
  // finisce sull'etichetta del pulsante e nella richiesta di cattura.
  screen.on('display-metrics-changed', aggiorna)
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

  // Con una funzione passata nuda il primo argomento sarebbe l'evento IPC, non
  // l'id dello schermo: finche' captureScreenshot non prendeva argomenti non si
  // notava, adesso si.
  ipcMain.handle('screenshot:capture', (_event, idSchermo?: string) => captureScreenshot(idSchermo))

  ipcMain.handle('schermi:elenco', () => elencaSchermi())

  // Sincrono: il preload lo chiede prima che la pagina esista, e una promessa
  // li' non servirebbe a niente perche' non c'e' ancora niente da dipingere.
  ipcMain.on('tema:iniziale', (evento) => {
    evento.returnValue = temaSalvato()
  })

  ipcMain.handle('tema:annuncia', (_evento, tema: string) => {
    // Le tre finestre sono tre processi: chi cambia il tema nelle impostazioni
    // non cambia la principale ne' l'overlay. Vederne due di colori diversi
    // sarebbe peggio che non poterlo cambiare affatto.
    trasmettiATutte('tema:cambiato', tema)
    const colore = coloreDiFondo(tema)
    for (const win of BrowserWindow.getAllWindows()) {
      // Vale per la prossima apertura, non per adesso: quello che si vede ora
      // lo dipinge la pagina, che ha gia' ricevuto l'evento qui sopra.
      if (!win.isDestroyed()) win.setBackgroundColor(colore)
    }
  })

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
  sorvegliaSchermi()

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
