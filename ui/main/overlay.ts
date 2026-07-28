/**
 * Finestra sovrapposta: la trascrizione mentre parli, senza occupare lo schermo.
 *
 * Durante una call lo schermo e' gia' pieno — la finestra della riunione, quello
 * che si sta condividendo, gli appunti. Aprire Scriba a schermo intero per
 * leggere due righe non ha senso: serve una striscia che sta sopra tutto, si
 * sposta dove non da' fastidio e si toglie di mezzo con un tasto.
 *
 * Senza cornice e sempre in primo piano, ma non trasparente ai clic: va
 * trascinata e ha dei comandi, quindi deve ricevere il mouse.
 */

import { BrowserWindow, screen } from 'electron'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'

interface Posizione {
  x: number
  y: number
  width: number
  height: number
}

const LARGHEZZA = 460
const ALTEZZA = 260

export class Overlay {
  private finestra: BrowserWindow | null = null

  constructor(
    private readonly cartellaRisorse: string,
    private readonly fileStato: string,
  ) {}

  get visibile(): boolean {
    return this.finestra !== null && !this.finestra.isDestroyed() && this.finestra.isVisible()
  }

  /** Mostra o nasconde. È quello che fa la scorciatoia. */
  alterna(): void {
    if (this.visibile) this.nascondi()
    else this.mostra()
  }

  mostra(): void {
    if (this.finestra === null || this.finestra.isDestroyed()) this.crea()
    this.finestra!.showInactive() // non ruba il fuoco alla call
  }

  nascondi(): void {
    if (this.finestra && !this.finestra.isDestroyed()) {
      this.salvaPosizione()
      this.finestra.hide()
    }
  }

  invia(canale: string, payload: unknown): void {
    if (this.finestra && !this.finestra.isDestroyed()) {
      this.finestra.webContents.send(canale, payload)
    }
  }

  chiudi(): void {
    if (this.finestra && !this.finestra.isDestroyed()) {
      this.salvaPosizione()
      this.finestra.destroy()
    }
    this.finestra = null
  }

  private crea(): void {
    const posizione = this.leggiPosizione()

    this.finestra = new BrowserWindow({
      ...posizione,
      frame: false,
      transparent: true,
      resizable: true,
      minWidth: 320,
      minHeight: 120,
      alwaysOnTop: true,
      skipTaskbar: true,
      // Non compare nel selettore di finestre della condivisione schermo: se
      // condividi lo schermo, la trascrizione non e' roba che vuoi mostrare.
      focusable: true,
      hasShadow: false,
      webPreferences: {
        preload: join(this.cartellaRisorse, 'main', 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
      },
    })

    this.finestra.loadFile(join(this.cartellaRisorse, 'renderer', 'overlay.html'))

    // Sopra anche le applicazioni a schermo intero, che e' il caso di una call
    // condivisa: con il livello normale sparirebbe proprio quando serve.
    this.finestra.setAlwaysOnTop(true, 'screen-saver')
    this.finestra.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })

    this.finestra.on('moved', () => this.salvaPosizione())
    this.finestra.on('resized', () => this.salvaPosizione())
    this.finestra.on('closed', () => (this.finestra = null))
  }

  private leggiPosizione(): Posizione {
    try {
      if (existsSync(this.fileStato)) {
        const salvata = JSON.parse(readFileSync(this.fileStato, 'utf-8')) as Posizione
        // Se il monitor su cui stava non c'e' piu', la finestra finirebbe fuori
        // schermo e sembrerebbe non aprirsi affatto.
        const dentro = screen.getAllDisplays().some((d) => {
          const b = d.workArea
          return (
            salvata.x >= b.x - 100 &&
            salvata.y >= b.y - 50 &&
            salvata.x < b.x + b.width &&
            salvata.y < b.y + b.height
          )
        })
        if (dentro) return salvata
      }
    } catch {
      // Posizione illeggibile: si riparte da quella predefinita.
    }

    const area = screen.getPrimaryDisplay().workArea
    return {
      x: area.x + area.width - LARGHEZZA - 24,
      y: area.y + 24,
      width: LARGHEZZA,
      height: ALTEZZA,
    }
  }

  private salvaPosizione(): void {
    if (!this.finestra || this.finestra.isDestroyed()) return
    try {
      const [x, y] = this.finestra.getPosition()
      const [width, height] = this.finestra.getSize()
      mkdirSync(dirname(this.fileStato), { recursive: true })
      writeFileSync(this.fileStato, JSON.stringify({ x, y, width, height }))
    } catch {
      // Non poter ricordare la posizione non e' un motivo per fallire.
    }
  }
}
