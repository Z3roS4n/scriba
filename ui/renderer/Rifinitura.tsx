/**
 * Comando per rifare la trascrizione di una call con più cura.
 *
 * Sta accanto a «Rianalizza» e alla diarizzazione, che è il posto dove vive già
 * il vocabolario di «avvia un lavoro lungo su questa call»: passo di conferma
 * con la stima scritta, barra mentre gira, esito quando finisce.
 *
 * L'esito non è decorativo. La passata può **rifiutarsi** di lavorare su una
 * traccia — succede su «gli altri» quando durante la call ci sono stati lunghi
 * tratti in cui nessuno riproduceva audio, perché quei silenzi nel file salvato
 * non ci sono e i minuti scritti nella trascrizione non corrispondono più a
 * dove si trova il parlato. Quel rifiuto va mostrato: è la differenza fra «ho
 * finito» e «ho finito metà lavoro».
 */

import { useCallback, useEffect, useState } from 'react'

import type { Sessione } from './tipi'
import { etichettaOppure, etichettaValore, useT } from './lingua'

export interface StatoRifinitura {
  in_corso: boolean
  session_id: number | null
  fatte: number
  totale: number
  traccia: string | null
  modello_pronto?: boolean
  errore?: string | null
  esito?: {
    riscritte: number
    nomi_corretti: number
    tracce: Record<
      string,
      {
        stato: string
        esaminate: number
        riscritte: number
        somiglianza: number | null
        /** La frase italiana: ripiego, se il gettone non si conosce. */
        motivo: string | null
        motivo_chiave?: string | null
        motivo_valori?: Record<string, string | number> | null
      }
    >
  } | null
}

/** Da 6,1x realtime misurati, sulla frazione di call in cui qualcuno parla. */
function stima(durata_ms: number | null): { min: number; max: number } {
  const minuti = (durata_ms ?? 0) / 60_000
  const min = Math.max(1, Math.round((minuti * 0.4) / 6.1))
  const max = Math.max(min + 1, Math.round((minuti * 0.8) / 6.1))
  return { min, max }
}

export function useRifinitura() {
  const [stato, setStato] = useState<StatoRifinitura | null>(null)

  const leggi = useCallback(async () => {
    const r = await window.scriba.get<StatoRifinitura>('/rifinitura/stato')
    if (r.ok) setStato(r.body)
  }, [])

  useEffect(() => {
    leggi()
    // Lo stato si rilegge anche agli eventi, ma non solo: chi apre la finestra
    // a lavoro già iniziato non ha ricevuto nessun evento, e senza la lettura
    // iniziale vedrebbe un comando invece di una barra.
    return window.scriba.on('core:event', (ev: any) => {
      if (ev?.type !== 'rifinitura') return
      if (ev.stato === 'in_corso') {
        setStato((prec) => ({
          ...(prec ?? { fatte: 0, totale: 0, traccia: null, session_id: null, in_corso: false }),
          in_corso: true,
          session_id: ev.session_id,
          fatte: ev.fatte,
          totale: ev.totale,
          traccia: ev.traccia,
        }))
      } else {
        leggi()
      }
    })
  }, [leggi])

  return { stato, ricarica: leggi }
}

export function ControlloRifinitura({
  sessione,
  stato,
  onFinita,
}: {
  sessione: Sessione
  stato: StatoRifinitura | null
  /** Chiamata quando la passata finisce: la trascrizione a video è vecchia. */
  onFinita?: () => void
}) {
  const t = useT()
  const [conferma, setConferma] = useState(false)
  const [errore, setErrore] = useState<string | null>(null)

  const inCorsoQui = Boolean(stato?.in_corso && stato.session_id === sessione.id)
  const inCorsoAltrove = Boolean(stato?.in_corso && stato.session_id !== sessione.id)
  const esito = stato && !stato.in_corso && stato.session_id === sessione.id ? stato.esito : null

  useEffect(() => {
    if (esito && onFinita) onFinita()
    // Solo quando l'esito compare: rileggere a ogni render rifarebbe la
    // richiesta in continuazione.
  }, [esito]) // eslint-disable-line react-hooks/exhaustive-deps

  const avvia = async () => {
    setErrore(null)
    setConferma(false)
    const r = await window.scriba.post(`/sessions/${sessione.id}/rifinisci`)
    if (!r.ok) setErrore((r.body as any)?.detail ?? t('rif2.non_partita', { n: r.status }))
  }

  if (stato?.modello_pronto === false) {
    // Detto, non nascosto: manca un modello da scaricare, e il rimedio è a due
    // clic. Un comando che sparisce non si può cercare.
    return (
      <p className="refine__n">
        {t('rif2.serve_canary')}
      </p>
    )
  }

  if (inCorsoQui) {
    const quota = stato && stato.totale > 0 ? Math.round((stato.fatte / stato.totale) * 100) : 0
    return (
      <div className="refine">
        <div className="progress progress--thin" style={{ width: 90 }}>
          <i style={{ width: `${quota}%` }}></i>
        </div>
        <span className="refine__n">
          {t('rif2.rifaccio', {
            cosa: etichettaValore(t, 'traccia', stato?.traccia ?? ''),
            fatte: stato?.fatte ?? 0,
            totale: stato?.totale ?? 0,
          })}
        </span>
        <button className="btn btn--sm" onClick={() => window.scriba.post('/rifinitura/interrompi')}>
          {t('rif.interrompi')}
        </button>
      </div>
    )
  }

  if (inCorsoAltrove) {
    return <span className="refine__n">{t('rif.gia_in_corso')}</span>
  }

  if (esito) {
    // Il motivo viene dal core e descrive una situazione della CALL, non della
    // traccia: con due tracce rifiutate era la stessa frase due volte, otto
    // righe tutte rosse per dire una cosa sola (#95). Si raggruppa per motivo
    // identico; se un giorno i motivi sono diversi, i gruppi diventano due.
    const perMotivo = new Map<string, string[]>()
    for (const [nome, tr] of Object.entries(esito.tracce)) {
      if (tr.stato !== 'non_allineata') continue
      // Il core manda un gettone e la frase italiana: la frase è il ripiego
      // se il gettone non si conosce, e se non c'è nemmeno quella la traccia
      // si dice lo stesso, senza inventare una spiegazione.
      const motivo = etichettaOppure(
        t,
        'rif_motivo',
        tr.motivo_chiave,
        tr.motivo ?? '',
        tr.motivo_valori ?? undefined,
      )
      perMotivo.set(motivo, [...(perMotivo.get(motivo) ?? []), nome])
    }

    return (
      <div className="refine refine--esito">
        <div className="refine__riga">
          <span className="chip chip--quiet">
            {esito.riscritte === 0
              ? t('rif2.nessuna_riga')
              : t('rif2.righe_rifatte', { n: esito.riscritte })}
          </span>
          <button className="btn btn--sm" onClick={() => setConferma(true)}>
            {t('rif.rifai')}
          </button>
        </div>
        {[...perMotivo].map(([motivo, nomi]) => (
          <p key={motivo} className="refine__perche">
            <b>{nomi.map((n) => etichettaValore(t, 'traccia', n)).join(', ')}</b>
            {t(nomi.length === 1 ? 'rif2.non_rifatta' : 'rif2.non_rifatte')} {motivo}
          </p>
        ))}
      </div>
    )
  }

  if (conferma) {
    const { min, max } = stima(sessione.durata_ms)
    return (
      <div className="refine refine--conferma">
        <div className="kv">
          <div className="kv__row">
            <span>{t('rif.durata')}</span>
            <b>
              {min}-{max} min
            </b>
          </div>
        </div>
        <p className="refine__n">
          {t('rif.conferma_nota')}
        </p>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <button className="btn btn--primary btn--sm" onClick={avvia}>
            {t('rif.avvia')}
          </button>
          <button className="btn btn--sm" onClick={() => setConferma(false)}>
            {t('rif.annulla')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="refine">
      <button className="btn btn--sm" onClick={() => setConferma(true)}>
        {t('rif.rifai_trascrizione')}
      </button>
      {errore && <p className="refine__perche">{errore}</p>}
    </div>
  )
}
