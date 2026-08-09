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

/** Righe di Markdown semplice — quello che il prompt chiede: elenchi e paragrafi. */
function Corpo({ testo }: { testo: string }) {
  const righe = testo.split('\n').map((r) => r.trim())
  const blocchi: React.ReactNode[] = []
  let elenco: string[] = []

  const chiudiElenco = () => {
    if (!elenco.length) return
    blocchi.push(
      <ul key={`u${blocchi.length}`} className="nota__elenco">
        {elenco.map((v, i) => (
          <li key={i}>{v}</li>
        ))}
      </ul>,
    )
    elenco = []
  }

  for (const riga of righe) {
    if (!riga) {
      chiudiElenco()
      continue
    }
    if (/^[-*•]\s+/.test(riga)) {
      elenco.push(riga.replace(/^[-*•]\s+/, ''))
      continue
    }
    chiudiElenco()
    if (/^#{1,6}\s+/.test(riga)) {
      blocchi.push(
        <div key={`h${blocchi.length}`} className="nota__titolo">
          {riga.replace(/^#{1,6}\s+/, '')}
        </div>,
      )
    } else {
      blocchi.push(
        <p key={`p${blocchi.length}`} className="nota__par">
          {riga}
        </p>,
      )
    }
  }
  chiudiElenco()
  return <>{blocchi}</>
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
      <div className="nota__testa">
        <span className="label">{t('not.titolo')}</span>
        {inCorso && <span className="nota__stato">{t('not.aggiorno')}</span>}
        {!inCorso && ultima?.scope_end_ms != null && (
          <span className="nota__stato">fino a {tempo(ultima.scope_end_ms)}</span>
        )}
      </div>

      {errore && <p className="nota__errore">{errore}</p>}

      {ultima ? (
        <>
          <Corpo testo={tutte ? note.map((n) => n.content_md).join('\n\n') : ultima.content_md} />
          {note.length > 1 && (
            <button className="btn--link" onClick={() => setTutte((v) => !v)}>
              {tutte ? t('not2.solo_ultima') : t('not2.tutte_e', { n: note.length })}
            </button>
          )}
        </>
      ) : (
        <p className="nota__par nota__attesa">
          {registrando
            ? t('not2.la_prima')
            : t('not2.finita_prima')}
        </p>
      )}
    </div>
  )
}
