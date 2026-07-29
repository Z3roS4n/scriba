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
 *
 * Due varianti, striscia intera e ridotta: la seconda serve quando anche 260px
 * di altezza sono troppi. Il passaggio fra le due e' una preferenza, non uno
 * stato di sessione — e ciascuna ricorda la propria posizione e dimensione,
 * altrimenti allargare la striscia intera farebbe ritrovare la ridotta grande
 * uguale al riavvio.
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

interface StatoSalvato {
  normale?: Posizione
  ridotta?: Posizione
}

const LARGHEZZA_NORMALE = 460
const ALTEZZA_NORMALE = 260
const LARGHEZZA_RIDOTTA = 420
const ALTEZZA_RIDOTTA = 92

const MINIMI_NORMALE = { width: 320, height: 120 }
const MINIMI_RIDOTTA = { width: 280, height: 72 }

export class Overlay {
  private finestra: BrowserWindow | null = null
  private ridotto = false

  constructor(
    private readonly cartellaRisorse: string,
    private readonly fileStato: string,
  ) {}

  get visibile(): boolean {
    return this.finestra !== null && !this.finestra.isDestroyed() && this.finestra.isVisible()
  }

  /**
   * Applica la preferenza salvata nelle impostazioni.
   *
   * Va chiamato prima della prima `mostra()`, cosi' la finestra nasce gia'
   * della dimensione giusta invece di aprirsi intera e saltare alla ridotta un
   * istante dopo.
   */
  impostaVariante(ridotto: boolean): void {
    this.ridotto = ridotto
    if (this.finestra && !this.finestra.isDestroyed()) this.ridimensiona()
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
      this.salvaStato()
      this.finestra.hide()
    }
  }

  /**
   * Passa fra striscia intera e variante ridotta. Restituisce lo stato nuovo.
   *
   * Chi la richiama (il processo principale) si occupa di salvare la
   * preferenza nelle impostazioni del core: qui si sa solo come ridisegnare la
   * finestra.
   */
  alternaRidotto(): boolean {
    this.ridotto = !this.ridotto
    this.ridimensiona()
    return this.ridotto
  }

  chiudi(): void {
    if (this.finestra && !this.finestra.isDestroyed()) {
      this.salvaStato()
      this.finestra.destroy()
    }
    this.finestra = null
  }

  private crea(): void {
    const posizione = this.posizioneVariante(this.ridotto)
    const minimi = this.ridotto ? MINIMI_RIDOTTA : MINIMI_NORMALE

    this.finestra = new BrowserWindow({
      ...posizione,
      frame: false,
      transparent: true,
      resizable: true,
      minWidth: minimi.width,
      minHeight: minimi.height,
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

    this.finestra.on('moved', () => this.salvaStato())
    this.finestra.on('resized', () => this.salvaStato())
    this.finestra.on('closed', () => (this.finestra = null))
  }

  /** Ridisegna la finestra gia' aperta sulla dimensione della variante corrente. */
  private ridimensiona(): void {
    if (!this.finestra || this.finestra.isDestroyed()) return
    const posizione = this.posizioneVariante(this.ridotto)
    const minimi = this.ridotto ? MINIMI_RIDOTTA : MINIMI_NORMALE
    this.finestra.setMinimumSize(minimi.width, minimi.height)
    this.finestra.setBounds(posizione)
  }

  private posizioneVariante(ridotto: boolean): Posizione {
    const salvata = this.leggiStatoGrezzo()[ridotto ? 'ridotta' : 'normale']
    const predefinita = this.posizionePredefinita(
      ridotto ? LARGHEZZA_RIDOTTA : LARGHEZZA_NORMALE,
      ridotto ? ALTEZZA_RIDOTTA : ALTEZZA_NORMALE,
    )
    if (!salvata) return predefinita

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
    return dentro ? salvata : predefinita
  }

  private posizionePredefinita(width: number, height: number): Posizione {
    const area = screen.getPrimaryDisplay().workArea
    return {
      x: area.x + area.width - width - 24,
      y: area.y + 24,
      width,
      height,
    }
  }

  private leggiStatoGrezzo(): StatoSalvato {
    try {
      if (existsSync(this.fileStato)) {
        return JSON.parse(readFileSync(this.fileStato, 'utf-8')) as StatoSalvato
      }
    } catch {
      // Stato illeggibile: si riparte dalle posizioni predefinite.
    }
    return {}
  }

  private salvaStato(): void {
    if (!this.finestra || this.finestra.isDestroyed()) return
    try {
      const [x, y] = this.finestra.getPosition()
      const [width, height] = this.finestra.getSize()
      const stato = this.leggiStatoGrezzo()
      if (this.ridotto) stato.ridotta = { x, y, width, height }
      else stato.normale = { x, y, width, height }
      mkdirSync(dirname(this.fileStato), { recursive: true })
      writeFileSync(this.fileStato, JSON.stringify(stato))
    } catch {
      // Non poter ricordare la posizione non e' un motivo per fallire.
    }
  }
}
