/**
 * Dialoghi e momenti dell'interfaccia, riusabili dalla finestra principale.
 *
 * Tre livelli di invadenza, non uno stile a scelta: il consenso è l'unico
 * modale dell'app — senza risposta non si può registrare, quindi blocca — e
 * tutto il resto (proposta di call, errori) non deve mai comportarsi come un
 * modale, nemmeno quando pesa molto (`Riquadro`, livello 3). Il posto in
 * pagina di `Barra`, `Riquadro` e `RiquadroInline` lo decide chi li monta:
 * qui c'è solo il contenuto, perché lo stesso `.alert` serve sia dentro il
 * pannello sia prima di cominciare un'azione.
 */

import { useEffect, useRef, useState } from 'react'
import type * as React from 'react'
import { useT } from './lingua'

/**
 * Il consenso, unico modale dell'app: senza spunta il pulsante resta spento,
 * anche quando la call è stata rilevata da sola e non da un clic dell'utente.
 */
export function ModaleConsenso(props: {
  titoloIniziale?: string
  onAnnulla: () => void
  onConferma: (titolo: string, consenso: boolean) => void
}): React.ReactElement {
  const t = useT()
  const { titoloIniziale = '', onAnnulla, onConferma } = props
  const [titolo, setTitolo] = useState(titoloIniziale)
  const [consenso, setConsenso] = useState(false)
  const campoTitolo = useRef<HTMLInputElement>(null)

  useEffect(() => {
    campoTitolo.current?.focus()
  }, [])

  useEffect(() => {
    // Lo stesso ritmo da tastiera del resto dell'app: Invio conferma solo se
    // la spunta c'è già, Esc annulla com'è lecito aspettarsi da un modale.
    const suTasto = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onAnnulla()
      else if (e.key === 'Enter' && consenso) onConferma(titolo, consenso)
    }
    window.addEventListener('keydown', suTasto)
    return () => window.removeEventListener('keydown', suTasto)
  }, [consenso, titolo, onAnnulla, onConferma])

  return (
    <div
      // Fuori dalle pagine di prova non esiste una classe per il velo a schermo
      // intero: `.scrimwrap*` è dichiaratamente solo da demo (lo esclude apposta
      // scripts/confronta-handoff.mjs). Il consenso però È l'unico modale
      // dell'app e senza un velo che blocchi il clic sotto non lo sarebbe
      // davvero — quindi qui lo stile in linea è l'eccezione voluta, segnalata
      // invece che nascosta in un CSS nuovo. Il colore è comunque il token del
      // handoff, non uno inventato.
      style={{
        position: 'fixed',
        inset: 0,
        background: 'var(--scrim)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={onAnnulla}
    >
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h2>{t('dlg.consenso_titolo')}</h2>
          <p>{t('dlg.consenso_cosa')}</p>
        </div>

        <div className="modal__field">
          <span className="label">{t('dlg2.titolo_facoltativo')}</span>
          <div className="textfield">
            <input
              ref={campoTitolo}
              type="text"
              value={titolo}
              placeholder={t('dlg.esempio_titolo')}
              onChange={(e) => setTitolo(e.target.value)}
              // .textfield disegna già bordo, sfondo e padding: senza azzerare
              // quelli nativi dell'input comparirebbe una seconda cornice
              // dentro la prima. Nessun colore o misura nuova, solo un reset.
              style={{
                width: '100%',
                border: 'none',
                outline: 'none',
                padding: 0,
                background: 'transparent',
                font: 'inherit',
                color: 'inherit',
              }}
            />
          </div>
        </div>

        <div className="consent">
          <button
            type="button"
            className={`checkbox${consenso ? ' is-on' : ''}`}
            aria-pressed={consenso}
            onClick={() => setConsenso((v) => !v)}
          >
            ✓
          </button>
          <div className="consent__text">
            <b>{t('dlg.consenso_spunta')}</b>
            <span>
              {t('dlg.consenso_nota')}
            </span>
          </div>
        </div>

        <div className="modal__foot">
          <span className="modal__hint">
            {consenso ? t('dlg2.invio_per_registrare') : t('dlg2.senza_conferma')}
          </span>
          <button type="button" className="btn" onClick={onAnnulla}>
            {t('dlg.annulla')}
          </button>
          <button type="button" className="btn btn--rec" disabled={!consenso} onClick={() => onConferma(titolo, consenso)}>
            {t('dlg.registra')}
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Proposta di registrare una call rilevata da sola. Non impedisce niente: si
 * può ignorare, e «No grazie» dimentica solo questa proposta, non il
 * rilevamento — motivo per cui c'è la nota sotto ai pulsanti.
 */
export function AvvisoCall(props: {
  nome: string
  onRegistra: () => void
  onNo: () => void
  onChiudi: () => void
}): React.ReactElement {
  const t = useT()
  const { nome, onRegistra, onNo, onChiudi } = props
  return (
    <div className="toast">
      <div className="toast__top">
        <i className="toast__dot" />
        <div className="toast__text">
          <b>{t('dlg2.sembra_call', { app: nome })}</b>
          <span>{t('dlg.rilevata')}</span>
        </div>
        <button type="button" className="btn--link" onClick={onChiudi}>
          ✕
        </button>
      </div>
      <div className="toast__actions">
        <button
          type="button"
          className="btn btn--primary btn--sm"
          style={{ padding: '7px 14px', fontSize: 'var(--fs-md)' }}
          onClick={onRegistra}
        >
          {t('dlg.registra')}
        </button>
        <button type="button" className="btn" style={{ fontSize: 'var(--fs-md)' }} onClick={onNo}>
          {t('dlg.no_grazie')}
        </button>
        <span className="toast__note">{t('dlg.torna')}</span>
      </div>
    </div>
  )
}

/** Livello 1: barra in alto, non impedisce niente. `.notice` */
export function Barra(props: {
  testo: string
  azione?: { etichetta: string; onClick: () => void }
  onChiudi: () => void
}): React.ReactElement {
  const { testo, azione, onChiudi } = props
  return (
    <div className="notice">
      {testo}
      <span className="notice__spacer" />
      {azione && (
        <button type="button" className="btn btn--sm" onClick={azione.onClick}>
          {azione.etichetta}
        </button>
      )}
      <button type="button" className="btn--link" onClick={onChiudi}>
        ✕
      </button>
    </div>
  )
}

/** Livelli 2 e 3: riquadro che blocca una funzione. `.alert` */
export function Riquadro(props: {
  titolo: string
  testo: string
  azioni?: Array<{ etichetta: string; primaria?: boolean; onClick: () => void }>
}): React.ReactElement {
  const { titolo, testo, azioni } = props
  return (
    <div className="alert">
      <h3>{titolo}</h3>
      <p>{testo}</p>
      {/* `.alert__actions` esiste nel foglio di stile e ha `flex-wrap`: qui
          c'era una riga flex scritta a mano, senza, e i tre comandi
          dell'analisi non riuscita uscivano dal pannello da 404px — il terzo
          tagliato a metà (#92).

          Via anche le misure in linea: erano del design vecchio, e la scala
          dei controlli nel sistema è una sola. Tre pulsanti di tre altezze
          diverse dentro lo stesso riquadro sono il difetto che la scala unica
          esiste per non avere. */}
      {azioni && azioni.length > 0 && (
        <div className="alert__actions">
          {azioni.map((a) => (
            <button
              key={a.etichetta}
              type="button"
              className={`btn btn--sm${a.primaria ? ' btn--primary' : ''}`}
              onClick={a.onClick}
            >
              {a.etichetta}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/** Livello 4: nel punto in cui si è premuto. `.alert--inline` */
export function RiquadroInline(props: {
  testo: string
  azioni?: Array<{ etichetta: string; onClick: () => void }>
}): React.ReactElement {
  const { testo, azioni } = props
  return (
    <div className="alert alert--inline">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '7px' }}>
        <p>{testo}</p>
        {azioni && azioni.length > 0 && (
          <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
            {azioni.map((a) => (
              <button key={a.etichetta} type="button" className="btn btn--sm" onClick={a.onClick}>
                {a.etichetta}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
