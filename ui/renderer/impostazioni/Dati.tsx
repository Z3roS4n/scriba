/**
 * Dati e privacy: dove stanno i file, e le due cancellazioni.
 *
 * «Elimina tutto di una call» deve chiedere quale call e poi una conferma
 * scritta (istruzioni del task): due passaggi, non un clic solo, perché non
 * si torna indietro. «Elimina l'audio» è irreversibile ma più contenuto —
 * qui basta un secondo clic che cambia l'etichetta del pulsante, senza un
 * intero modale.
 */

import { useEffect, useState } from 'react'

import type { Sessione, VoceDati } from '../tipi'
import { dimensione } from '../tipi'
import { Modal } from './Modal'
import { useLocale, useT } from '../lingua'


type Passo = 'chiusa' | 'elenco' | 'conferma'

/**
 * Che build si sta usando.
 *
 * Sta qui e non in un «Informazioni» a parte perché è la stessa domanda di
 * «dove stanno i miei dati»: la si fa quando qualcosa non torna. Il commit
 * accanto al numero non è pignoleria — durante lo sviluppo si fanno molte
 * build con lo stesso numero, ed è l'unica cosa che le distingue.
 */
function Versione() {
  const t = useT()
  const [v, setV] = useState<{
    versione: string
    commit: string | null
    pulito: boolean | null
    costruito_il: string | null
  } | null>(null)

  useEffect(() => {
    window.scriba.versione().then(setV)
  }, [])

  if (!v) return null
  const locale = useLocale()
  const quando = v.costruito_il ? new Date(v.costruito_il) : null
  return (
    <div className="row">
      <div className="row__t">
        <b>{t('dat.versione')}</b>
        <span>
          {quando && !Number.isNaN(quando.getTime())
            ? t('dat2.compilata', {
                data: quando.toLocaleDateString(locale, { day: 'numeric', month: 'long', year: 'numeric' }),
              })
            : t('dat2.senza_data')}
          {v.pulito === false && ` ${t('dat2.sporco')}`}
        </span>
      </div>
      <span className="pathrow__size">
        {v.versione}
        {v.commit ? ` · ${v.commit}${v.pulito === false ? '+' : ''}` : ''}
      </span>
    </div>
  )
}

export function SezioneDati({
  voci,
  onApri,
  onEliminaAudio,
  onEliminaCall,
  caricaSessioni,
}: {
  voci: VoceDati[]
  onApri: (path: string) => void
  onEliminaAudio: () => Promise<boolean>
  onEliminaCall: (id: number) => Promise<boolean>
  caricaSessioni: () => Promise<Sessione[]>
}) {
  const t = useT()
  const locale = useLocale()
  const [confermaAudio, setConfermaAudio] = useState(false)
  const [passo, setPasso] = useState<Passo>('chiusa')
  const [sessioni, setSessioni] = useState<Sessione[]>([])
  const [sessioneScelta, setSessioneScelta] = useState<Sessione | null>(null)
  const [testoConferma, setTestoConferma] = useState('')
  const [eliminando, setEliminando] = useState(false)

  const apriScelta = async () => {
    setPasso('elenco')
    setSessioni(await caricaSessioni())
  }

  const chiudi = () => {
    setPasso('chiusa')
    setSessioneScelta(null)
    setTestoConferma('')
  }

  const confermaEliminazione = async () => {
    if (!sessioneScelta) return
    setEliminando(true)
    const ok = await onEliminaCall(sessioneScelta.id)
    setEliminando(false)
    if (ok) chiudi()
  }

  return (
    <>
      <div className="settings__head">{t('dat.titolo')}</div>
      <div className="settings__body">
        <Versione />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)', margin: 'var(--sp-4) 0 18px' }}>
          {voci.map((v) => (
            <div className="pathrow" key={v.chiave}>
              <div className="pathrow__text">
                <b>{v.etichetta}</b>
                <span>{v.path}</span>
              </div>
              <span className="pathrow__size">{dimensione(v.bytes)}</span>
              <button className="btn btn--sm" onClick={() => onApri(v.path)}>
                {t('dat.apri')}
              </button>
            </div>
          ))}
        </div>

        <div className="danger">
          <span className="label">{t('dat.cancellazioni')}</span>
          <div className="row">
            <div className="row__t">
              <b>{t('dat.elimina_audio')}</b>
              <span>
                {t('dat.elimina_audio_nota')}
              </span>
            </div>
            {confermaAudio ? (
              <button
                className="btn btn--danger"
                onClick={async () => {
                  if (await onEliminaAudio()) setConfermaAudio(false)
                }}
              >
                {t('dat.conferma_elimina')}
              </button>
            ) : (
              <button className="btn btn--danger" onClick={() => setConfermaAudio(true)}>
                {t('dat.elimina_audio_btn')}
              </button>
            )}
          </div>
          <div className="row">
            <div className="row__t">
              <b>{t('dat.elimina_tutto')}</b>
              <span>{t('dat.elimina_tutto_nota')}</span>
            </div>
            <button className="btn btn--danger" onClick={apriScelta}>
              {t('dat.scegli_call')}
            </button>
          </div>
        </div>
      </div>

      {passo === 'elenco' && (
        <Modal onChiudi={chiudi}>
          <div className="modal__head">
            <h2>{t('dat.quale_call')}</h2>
            <p>{t('dat.verra_cancellato')}</p>
          </div>
          <div
            style={{
              padding: '0 20px 16px',
              display: 'flex',
              flexDirection: 'column',
              gap: 1,
              maxHeight: 320,
              overflowY: 'auto',
            }}
          >
            {sessioni.length === 0 ? (
              <p style={{ color: 'var(--fg-3)', fontSize: 'var(--fs-sm)' }}>{t('dat.nessuna_call')}</p>
            ) : (
              sessioni.map((s) => (
                <button
                  key={s.id}
                  className="btn btn--block"
                  onClick={() => {
                    setSessioneScelta(s)
                    setPasso('conferma')
                  }}
                >
                  {s.titolo ?? t('dat2.call_del', { data: new Date(s.started_at).toLocaleDateString(locale) })}
                </button>
              ))
            )}
          </div>
          <div className="modal__foot">
            <button className="btn" onClick={chiudi}>
              {t('dat.annulla')}
            </button>
          </div>
        </Modal>
      )}

      {passo === 'conferma' && sessioneScelta && (
        <Modal onChiudi={chiudi}>
          <div className="modal__head">
            <h2>{t('dat2.eliminare', { titolo: sessioneScelta.titolo ?? t('dat2.questa_call') })}</h2>
            <p>{t('dat2.scrivi_per_confermare', { parola: t('dat2.parola') })}</p>
          </div>
          <div className="modal__field">
            <input
              className="textfield textfield--md"
              value={testoConferma}
              autoFocus
              placeholder={t('dat2.parola')}
              onChange={(e) => setTestoConferma(e.target.value)}
            />
          </div>
          <div className="modal__foot">
            <button className="btn" onClick={() => setPasso('elenco')}>
              {t('dat.indietro')}
            </button>
            <button
              className="btn btn--danger"
              disabled={testoConferma.trim() !== t('dat2.parola') || eliminando}
              onClick={confermaEliminazione}
            >
              {t('dat.elimina_def')}
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
