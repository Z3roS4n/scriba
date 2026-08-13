/**
 * Barra in alto: stato del core, cronometro, comandi principali e comandi finestra.
 *
 * Le finestre sono senza cornice — quella di Windows ignora il tema scuro — quindi
 * riduci/ingrandisci/chiudi sono bottoni nostri che parlano con `window.scriba.finestra`.
 * L'ingranaggio apre le Impostazioni: e' l'unico comando qui dentro che non passa da
 * index.tsx, perche' non tocca nessuno stato che la finestra principale debba conoscere.
 */

import { useEffect, useRef, useState } from 'react'

import type { Schermo } from './scriba'
import { useT } from './lingua'
import { tempo } from './tipi'

/** Rispecchia lo stato dell'evento `modello` del core: non serve un tipo condiviso per due file. */
export type StatoModello = 'in_attesa' | 'caricamento' | 'pronto' | 'errore'

/**
 * I minuti di registrazione, con il loro stato e il loro timer.
 *
 * Stava nel componente radice, e da lì due volte al secondo si ridisegnava
 * tutta la finestra: elenco call, trascrizione, pannello analisi. Le righe
 * della trascrizione sono `memo`, quindi il contenuto non si ricalcolava —
 * ma React ricreava comunque un elemento per riga, e su questa macchina una
 * call ne ha duemila (#94).
 *
 * Qui il ridisegno tocca due cifre.
 *
 * Il conteggio è locale e si riallinea al core ogni venti secondi: chiederlo a
 * ogni tick sarebbe un giro IPC + HTTP al secondo per due cifre, e un
 * contatore solo locale andrebbe avanti anche a registrazione sospesa — delle
 * pause sa il core.
 */
function Cronometro() {
  const [ms, setMs] = useState(0)
  const inizio = useRef(Date.now())
  const scarto = useRef(0)

  useEffect(() => {
    let vivo = true
    const allinea = async () => {
      const r = await window.scriba.get<{ now_ms: number }>('/session/state')
      if (vivo && r.ok && r.body?.now_ms != null) {
        scarto.current = r.body.now_ms - (Date.now() - inizio.current)
        setMs(Date.now() - inizio.current + scarto.current)
      }
    }
    allinea()
    const tick = setInterval(() => setMs(Date.now() - inizio.current + scarto.current), 500)
    const risincronizza = setInterval(allinea, 20_000)
    return () => {
      vivo = false
      clearInterval(tick)
      clearInterval(risincronizza)
    }
  }, [])

  return <span className="timer">{tempo(ms)}</span>
}

export function Topbar(props: {
  corePronto: boolean
  modello: StatoModello
  registrando: boolean
  sessioneVista: number | null
  esportando: boolean
  /** Gli schermi collegati. Vuoto finche' il processo principale non risponde. */
  schermi: Schermo[]
  /** Senza id: schermo principale. */
  onScreenshot: (idSchermo?: string) => void
  onArchivio: () => void
  onEsporta: () => void
  onRegistra: () => void
  onFerma: () => void
}) {
  const {
    corePronto,
    modello,
    registrando,
    sessioneVista,
    esportando,
    schermi,
    onScreenshot,
    onArchivio,
    onEsporta,
    onRegistra,
    onFerma,
  } = props

  const t = useT()

  const testoStato = registrando
    ? t('stato.registrazione')
    : !corePronto
      ? t('stato.avvio')
      : modello === 'caricamento' || modello === 'in_attesa'
        ? t('stato.carico')
        : modello === 'errore'
          ? t('stato.modello_assente')
          : t('stato.pronto')

  // "Registra" resta spento finche' non c'e' un modello di trascrizione pronto:
  // avviare una registrazione che nessuno trascrive sarebbe solo silenzio salvato.
  const registraDisabilitato = !corePronto || modello !== 'pronto'
  const esportaDisabilitato = sessioneVista === null || esportando

  return (
    <header className="topbar">
      <span className="brand">{t('top.nome')}</span>

      <div className={`status ${registrando ? 'is-recording' : ''}`}>
        <span className={`sq ${registrando ? 'sq--rec' : 'sq--hollow'}`} />
        {testoStato}
      </div>

      {/* Montato solo mentre si registra: smontandosi azzera il conteggio,
          che è esattamente quello che deve fare a call nuova. */}
      {registrando && <Cronometro />}

      <div className="topbar__spacer" />

      <div className="toolbar">
        {/* Con un solo schermo resta il pulsante di sempre: dividerlo in uno
            per schermo quando lo schermo e' uno aggiungerebbe una scelta che
            non esiste. Con piu' di uno, uno per ciascuno — durante una call
            non c'e' tempo per aprire un menu e cercare quello giusto. */}
        {schermi.length <= 1 ? (
          <button
            className="btn"
            disabled={!registrando}
            onClick={() => onScreenshot()}
          >
            {t('azione.screenshot')}
          </button>
        ) : (
          schermi.map((s, i) => (
            <button
              key={s.id}
              className="btn"
              disabled={!registrando}
              title={`${s.etichetta} — ${s.larghezza}×${s.altezza}${s.principale ? ' (principale)' : ''}`}
              onClick={() => onScreenshot(s.id)}
            >
              {t('azione.schermo_n', { n: i + 1 })}
            </button>
          ))
        )}

        <button className="btn" disabled={esportaDisabilitato} onClick={onEsporta}>
          {esportando ? t('azione.esportando') : t('azione.esporta')}
        </button>

        {/* Non disabilitato quando non c'e' nessuna call: l'archivio spiega da
            solo di essere vuoto, ed e' anche da li' che si gestiscono i
            clienti prima di avere qualcosa da attribuirgli. */}
        <button className="btn" onClick={onArchivio}>
          {t('azione.archivio')}
        </button>

        <button
          className="btn btn--icon"
          aria-label={t('azione.impostazioni')}
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
          {registrando ? t('azione.ferma') : t('azione.registra')}
        </button>
      </div>

      {/* I tre segni sono disegnati dal CSS (`.wc-min`, `.wc-max`,
          `.wc-close`), non sono caratteri. Erano «—», «▢», «✕»: tre glifi presi
          da tre parti diverse della tavola Unicode, che il font rende con pesi
          e altezze sue e che cambiano aspetto se il font cambia. Con i bordi,
          la linea è una linea da 1px in tutti e tre. */}
      <div className="wincontrols">
        <button aria-label={t('finestra.riduci')} onClick={() => window.scriba.finestra.riduci()}>
          <i className="wc-min" />
        </button>
        <button aria-label={t('finestra.ingrandisci')} onClick={() => window.scriba.finestra.ingrandisci()}>
          <i className="wc-max" />
        </button>
        <button aria-label={t('finestra.chiudi')} onClick={() => window.scriba.finestra.chiudi()}>
          <i className="wc-close" />
        </button>
      </div>
    </header>
  )
}
