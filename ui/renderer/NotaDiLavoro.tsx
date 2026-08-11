/**
 * La nota di lavoro scritta mentre la call è ancora in corso.
 *
 * Esisteva già chi la generava e chi la salvava; mancava chi la mostrasse, ed
 * era tutto il punto — una nota che arriva prima della fine serve **durante**
 * la riunione, altrimenti tanto vale aspettare il riassunto.
 *
 * Si mostra l'ultima. Ogni nota riscrive la precedente incorporandola, quindi
 * l'ultima le contiene tutte: le altre raccontano come è cambiata la
 * comprensione della riunione mentre andava, che è un'altra domanda e sta
 * dietro a un comando invece che davanti a tutti.
 */

import { useCallback, useEffect, useState } from 'react'

import { Markdown } from './markdown'
import { tempo } from './tipi'
import { useT } from './lingua'

interface Nota {
  id: number
  scope_start_ms: number | null
  scope_end_ms: number | null
  content_md: string
  created_at: number
}

interface Risposta {
  session_id: number
  note: Nota[]
  ultima: Nota | null
  /** Se l'impostazione è accesa: distingue «non ancora» da «non le vuoi». */
  attive: boolean
}

/** I nomi dei pezzi che il foglio di stile dà alla nota. */
const CLASSI = {
  gruppo: 'nota__corpo',
  paragrafo: 'nota__par',
  elenco: 'nota__elenco',
  titolo: 'nota__titolo',
}

export function NotaDiLavoro({
  sessionId,
  registrando,
}: {
  sessionId: number | null
  registrando: boolean
}) {
  const t = useT()
  const [dati, setDati] = useState<Risposta | null>(null)
  const [inCorso, setInCorso] = useState(false)
  const [errore, setErrore] = useState<string | null>(null)
  const [tutte, setTutte] = useState(false)

  const carica = useCallback(async () => {
    if (sessionId == null) return setDati(null)
    const r = await window.scriba.get<Risposta>(`/sessions/${sessionId}/note`)
    if (r.ok) setDati(r.body)
  }, [sessionId])

  useEffect(() => {
    setTutte(false)
    carica()
  }, [carica])

  useEffect(() => {
    return window.scriba.on('core:event', (ev: any) => {
      if (ev?.type !== 'nota' || ev.session_id !== sessionId) return
      if (ev.stato === 'in_corso') {
        setInCorso(true)
        setErrore(null)
      } else if (ev.stato === 'fatta') {
        setInCorso(false)
        // Si rilegge invece di fidarsi del testo nell'evento: da lì manca
        // tutto il resto (la finestra coperta, i candidati), e una schermata
        // che si costruisce da due fonti diverse finisce per divergere.
        carica()
      } else if (ev.stato === 'errore') {
        setInCorso(false)
        setErrore(ev.dettaglio || t('not2.no_risposta'))
      }
    })
  }, [sessionId, carica])

  if (sessionId == null || !dati) return null
  const { ultima, note, attive } = dati

  // Spenta e senza note: non c'è niente da dire. L'interruttore sta nelle
  // impostazioni, e ripeterlo qui sarebbe pubblicità di una funzione.
  if (!attive && !ultima) return null

  return (
    <div className="nota">
      <div className="nota__head">
        <span className="label label--quiet">{t('not.titolo')}</span>
        {inCorso && <span className="nota__when">{t('not.aggiorno')}</span>}
        {!inCorso && ultima?.scope_end_ms != null && (
          <span className="nota__when num">{t('not2.fino_a', { t: tempo(ultima.scope_end_ms) })}</span>
        )}
      </div>

      {errore && (
        <div className="alert alert--inline nota__errore">
          <p>{errore}</p>
        </div>
      )}

      {ultima ? (
        <>
          <Markdown
            testo={tutte ? note.map((n) => n.content_md).join('\n\n') : ultima.content_md}
            classi={CLASSI}
          />
          {note.length > 1 && (
            <button className="btn btn--quiet btn--sm" onClick={() => setTutte((v) => !v)}>
              {tutte ? t('not2.solo_ultima') : t('not2.tutte_e', { n: note.length })}
            </button>
          )}
        </>
      ) : (
        <p className="nota__vuota">{registrando ? t('not2.la_prima') : t('not2.finita_prima')}</p>
      )}
    </div>
  )
}
