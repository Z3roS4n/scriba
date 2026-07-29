/**
 * Barra in alto: stato del core, cronometro, comandi principali e comandi finestra.
 *
 * Le finestre sono senza cornice — quella di Windows ignora il tema scuro — quindi
 * riduci/ingrandisci/chiudi sono bottoni nostri che parlano con `window.scriba.finestra`.
 * L'ingranaggio apre le Impostazioni: e' l'unico comando qui dentro che non passa da
 * index.tsx, perche' non tocca nessuno stato che la finestra principale debba conoscere.
 */

import { tempo } from './tipi'

/** Rispecchia lo stato dell'evento `modello` del core: non serve un tipo condiviso per due file. */
export type StatoModello = 'in_attesa' | 'caricamento' | 'pronto' | 'errore'

export function Topbar(props: {
  corePronto: boolean
  modello: StatoModello
  registrando: boolean
  trascorsi: number
  sessioneVista: number | null
  esportando: boolean
  onScreenshot: () => void
  onEsporta: () => void
  onRegistra: () => void
  onFerma: () => void
}) {
  const {
    corePronto,
    modello,
    registrando,
    trascorsi,
    sessioneVista,
    esportando,
    onScreenshot,
    onEsporta,
    onRegistra,
    onFerma,
  } = props

  const testoStato = registrando
    ? 'Registrazione'
    : !corePronto
      ? 'Avvio del core...'
      : modello === 'caricamento' || modello === 'in_attesa'
        ? 'Carico il modello...'
        : modello === 'errore'
          ? 'Modello non disponibile'
          : 'Pronto'

  // "Registra" resta spento finche' non c'e' un modello di trascrizione pronto:
  // avviare una registrazione che nessuno trascrive sarebbe solo silenzio salvato.
  const registraDisabilitato = !corePronto || modello !== 'pronto'
  const esportaDisabilitato = sessioneVista === null || esportando

  return (
    <header className="topbar">
      <span className="brand">Scriba</span>

      <div className={`status ${registrando ? 'is-recording' : ''}`}>
        <i className="status__dot" />
        {testoStato}
      </div>

      {registrando && <span className="timer">{tempo(trascorsi)}</span>}

      <div className="topbar__spacer" />

      <div className="toolbar">
        <button
          className={`btn ${!registrando ? 'is-disabled' : ''}`}
          disabled={!registrando}
          onClick={onScreenshot}
        >
          Screenshot
        </button>

        <button className="btn" disabled={esportaDisabilitato} onClick={onEsporta}>
          {esportando ? 'Esporto…' : 'Esporta'}
        </button>

        <button
          className="btn btn--icon"
          aria-label="Impostazioni"
          onClick={() => window.scriba.apriImpostazioni()}
        >
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
            <circle cx="8" cy="8" r="2.4" />
            <circle cx="8" cy="8" r="6" />
          </svg>
        </button>

        <button
          className={`btn btn--rec ${registrando ? 'is-recording' : ''}`}
          disabled={!registrando && registraDisabilitato}
          onClick={registrando ? onFerma : onRegistra}
        >
          {registrando ? 'Ferma' : 'Registra'}
        </button>
      </div>

      <div className="wincontrols">
        <button onClick={() => window.scriba.finestra.riduci()}>—</button>
        <button onClick={() => window.scriba.finestra.ingrandisci()}>▢</button>
        <button onClick={() => window.scriba.finestra.chiudi()}>✕</button>
      </div>
    </header>
  )
}
