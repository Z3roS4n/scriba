/**
 * Finestra delle impostazioni.
 *
 * Una finestra a se', non un dialogo dentro la principale: si può lasciare
 * aperta mentre si lavora altrove, e chiuderla non deve fermare
 * l'applicazione ne' interrompere un download in corso, che vive nel core.
 */

import { BrowserWindow } from 'electron'
import { join } from 'node:path'

const LARGHEZZA = 980
const ALTEZZA = 720

export class Impostazioni {
  private finestra: BrowserWindow | null = null

  constructor(
    private readonly cartellaRisorse: string,
    /** Percorso del .ico: senza, Windows le darebbe quella di Electron. */
    private readonly icona: string,
  ) {}

  /** Apre la finestra, o la porta davanti se e' gia' aperta. */
  apri(): void {
    if (this.finestra && !this.finestra.isDestroyed()) {
      this.finestra.show()
      this.finestra.focus()
      return
    }

    this.finestra = new BrowserWindow({
      width: LARGHEZZA,
      height: ALTEZZA,
      // Dimensione fissa: il design non le disegna un pulsante di
      // massimizzazione, quindi ridimensionarla non porterebbe a niente di
      // buono da mostrare.
      resizable: false,
      show: false,
      frame: false,
      backgroundColor: '#141416',
      title: 'Impostazioni',
      icon: this.icona,
      webPreferences: {
        preload: join(this.cartellaRisorse, 'main', 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: false,
      },
    })

    this.finestra.loadFile(join(this.cartellaRisorse, 'renderer', 'impostazioni.html'))
    this.finestra.once('ready-to-show', () => this.finestra?.show())
    this.finestra.on('closed', () => (this.finestra = null))
  }

  /** Chiude la finestra senza toccare il resto dell'applicazione. */
  chiudi(): void {
    if (this.finestra && !this.finestra.isDestroyed()) this.finestra.close()
  }
}
