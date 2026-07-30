/**
 * Avvia e sorveglia il processo core.
 *
 * Il core e' un processo Python separato: apre i device audio e tiene il
 * modello di trascrizione in memoria. Due cose vanno fatte bene, o si finisce
 * con processi orfani che tengono occupato il microfono e device che alla
 * registrazione successiva risultano gia' in uso:
 *
 * 1. il core viene ucciso quando l'interfaccia si chiude;
 * 2. il core si spegne da solo se l'interfaccia sparisce senza avvisare — se ne
 *    accorge perche' il sistema gli chiude lo standard input.
 */

import { ChildProcess, spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { createInterface } from 'node:readline'

export interface CoreEndpoint {
  port: number
  token: string
}

export class Sidecar {
  private child: ChildProcess | null = null
  private endpoint: CoreEndpoint | null = null

  constructor(
    private readonly projectRoot: string,
    private readonly dbPath: string,
  ) {}

  get address(): CoreEndpoint | null {
    return this.endpoint
  }

  get baseUrl(): string {
    if (!this.endpoint) throw new Error('Core non ancora avviato')
    return `http://127.0.0.1:${this.endpoint.port}`
  }

  /**
   * Trova come avviare il core, in sviluppo o pacchettizzato, senza che nessuno
   * debba ricordarsi di cambiare una riga passando dall'uno all'altro.
   *
   * In sviluppo `projectRoot` e' la cartella `scriba/` (electron parte dalla
   * cartella `ui/`, e chi costruisce questo oggetto risale di uno). Una volta
   * pacchettizzato con electron-builder, `app.getAppPath()` punta dentro
   * `resources/` (l'app e' in `resources/app.asar`), quindi risalendo di uno
   * `projectRoot` diventa proprio `resources/` — la cartella in cui
   * `electron-builder.yml` copia l'eseguibile PyInstaller come extraResource.
   * Bastano due percorsi noti da controllare, nell'ordine in cui ha senso
   * cercarli: prima l'ambiente di sviluppo, poi quello installato.
   */
  private resolveCommand(): { comando: string; argv: string[]; cwd: string } {
    const devPython = join(this.projectRoot, 'core', '.venv', 'Scripts', 'python.exe')
    if (existsSync(devPython)) {
      // `-m` e non lo script diretto: e' lo stesso modo in cui gira sotto
      // pytest e in tutta la documentazione del core, e mantiene gli import
      // relativi del pacchetto `scriba_core` validi.
      return { comando: devPython, argv: ['-m', 'scriba_core.server'], cwd: join(this.projectRoot, 'core') }
    }

    const eseguibilePacchettizzato = join(this.projectRoot, 'core-dist', 'scriba_core', 'scriba_core.exe')
    if (existsSync(eseguibilePacchettizzato)) {
      // Nessun `-m`: l'eseguibile prodotto da PyInstaller (vedi
      // scripts/pyinstaller/entry_point.py) accetta direttamente il percorso
      // del database e `--watch-parent`, replicando lo stesso comando.
      return { comando: eseguibilePacchettizzato, argv: [], cwd: dirname(eseguibilePacchettizzato) }
    }

    throw new Error(
      `Core non trovato ne' in ${devPython} ne' in ${eseguibilePacchettizzato}.\n` +
        'In sviluppo: crea l\'ambiente con  uv venv core/.venv --python 3.12\n' +
        'In un pacchetto installato questo e\' un problema della build, non della macchina ' +
        'dell\'utente: manca l\'eseguibile del core sotto core-dist/.',
    )
  }

  /** Avvia il core e aspetta che annunci dove trovarlo. */
  async start(timeoutMs = 30_000): Promise<CoreEndpoint> {
    if (this.endpoint) return this.endpoint

    const { comando, argv, cwd } = this.resolveCommand()
    this.child = spawn(comando, [...argv, this.dbPath, '--watch-parent'], {
      cwd,
      // stdin resta aperto di proposito: e' il guinzaglio con cui il core
      // capisce che siamo ancora vivi.
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    })

    this.child.stderr?.on('data', (chunk: Buffer) => {
      console.error('[core]', chunk.toString().trimEnd())
    })

    this.child.on('exit', (code) => {
      console.error(`[core] terminato con codice ${code}`)
      this.endpoint = null
      this.child = null
    })

    const endpoint = await this.readAnnouncement(timeoutMs)
    await this.waitUntilReady(endpoint, timeoutMs)
    this.endpoint = endpoint
    return endpoint
  }

  /**
   * Aspetta che il core risponda davvero.
   *
   * L'annuncio della porta arriva prima che il server sia in piedi: dire
   * "pronto" a quel punto significa lasciare che le prime richieste falliscano
   * senza motivo apparente.
   */
  private async waitUntilReady(endpoint: CoreEndpoint, timeoutMs: number): Promise<void> {
    const scadenza = Date.now() + timeoutMs
    while (Date.now() < scadenza) {
      try {
        const response = await fetch(`http://127.0.0.1:${endpoint.port}/health`)
        if (response.ok) return
      } catch {
        // Non ancora in ascolto: si riprova.
      }
      await new Promise((r) => setTimeout(r, 200))
    }
    throw new Error('Il core si e\' avviato ma non risponde')
  }

  /**
   * La prima riga che il core stampa e' un JSON con porta e token.
   * La porta la sceglie il sistema, quindi non e' indovinabile: l'unico modo di
   * conoscerla e' leggerla da qui.
   */
  private readAnnouncement(timeoutMs: number): Promise<CoreEndpoint> {
    return new Promise((resolve, reject) => {
      if (!this.child?.stdout) {
        reject(new Error('Il core non ha uno standard output'))
        return
      }

      const timer = setTimeout(() => {
        cleanup()
        reject(new Error(`Il core non ha risposto entro ${timeoutMs / 1000}s`))
      }, timeoutMs)

      const rl = createInterface({ input: this.child.stdout })
      const cleanup = () => {
        clearTimeout(timer)
        rl.close()
      }

      rl.on('line', (line) => {
        try {
          const parsed = JSON.parse(line)
          if (typeof parsed.port === 'number' && typeof parsed.token === 'string') {
            cleanup()
            resolve({ port: parsed.port, token: parsed.token })
          }
        } catch {
          // Righe non JSON sono log del core: si lasciano passare.
          console.log('[core]', line)
        }
      })

      this.child.on('exit', (code) => {
        cleanup()
        reject(new Error(`Il core e' uscito prima di avviarsi (codice ${code})`))
      })
    })
  }

  /**
   * Ferma il core, e si assicura che sia fermo davvero.
   *
   * Due trappole, entrambe costate dati:
   *
   * 1. **Il core non e' sempre il processo figlio.** In sviluppo il
   *    `python.exe` dentro `core/.venv` creato con uv e' uno stub che
   *    ri-esegue l'interprete di base: il server vero e' un nipote. `kill()`
   *    su Windows termina un processo solo, quindi uccideva lo stub e lasciava
   *    il core vivo, col database aperto. Al build successivo ne partiva un
   *    altro sullo stesso file. Da qui `taskkill /T`, che prende l'albero.
   * 2. **Ucciderlo subito gli impedisce di chiudere il database.** Il core
   *    consolida il WAL durante lo spegnimento (Store.consolida): prima si
   *    chiude lo stdin, che e' il segnale concordato, e gli si lascia il tempo
   *    di uscire da solo. La forza e' la rete di sicurezza, non il primo passo.
   */
  async stop(attesaMs = 6_000): Promise<void> {
    const child = this.child
    this.child = null
    this.endpoint = null
    if (!child) return

    const uscito = new Promise<void>((resolve) => {
      child.once('exit', () => resolve())
    })
    child.stdin?.end()

    const scaduto = await Promise.race([
      uscito.then(() => false),
      new Promise<boolean>((r) => setTimeout(() => r(true), attesaMs)),
    ])
    if (!scaduto) return

    console.error('[core] non si e\' fermato da solo: termino l\'albero')
    if (child.pid !== undefined) {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true })
      } else {
        child.kill('SIGKILL')
      }
    }
  }
}
