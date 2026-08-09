/**
 * Rilevamento automatico delle call.
 *
 * Il testo della terza riga ripete che il consenso resta obbligatorio anche
 * avviando da sola: va tenuto così com'è, la registrazione non deve mai
 * partire senza la spunta (istruzioni del task).
 *
 * In fondo c'è il pannello che mostra cosa il rilevamento sta vedendo adesso.
 * Non è una curiosità: «non mi ha proposto di registrare» ha cinque cause
 * possibili — sonda ferma, processo escluso, microfono senza segnale, nessun
 * audio in riproduzione, attesa non ancora scaduta — e dall'esterno sono
 * indistinguibili. Senza questo pannello un difetto si può solo indovinare.
 */

import { useCallback, useEffect, useState } from 'react'

import type { DiagnosticaRilevamento, Impostazioni, ProcessoVisto } from '../tipi'
import { etichettaValore, useT } from '../lingua'

/** Il colore dell'esito. Solo «riunione» è verde: il resto è informazione. */
const CLASSE_ESITO: Record<string, string> = {
  riunione: 'vis__esito vis__esito--ok',
  in_conferma: 'vis__esito vis__esito--attesa',
  gia_proposta: 'vis__esito vis__esito--ok',
}

function Processo({ p }: { p: ProcessoVisto }) {
  const t = useT()
  return (
    <div className="vis__riga">
      <span className="vis__nome">{p.processo}</span>
      <span className="vis__pid">pid {p.pid}</span>
      <span className={CLASSE_ESITO[p.esito ?? ''] ?? 'vis__esito'}>
        {p.esito ? etichettaValore(t, 'ril_esito', p.esito) : t('ril2.in_valutazione')}
        {p.mancano_s != null && t('ril2.ancora_s', { s: p.mancano_s })}
      </span>
      <span className="vis__segnale">
        {p.picco > 0 ? t('ril2.mic_attivo', { picco: p.picco.toFixed(3) }) : t('ril2.mic_muto')}
        {' · '}
        {t(
          p.riproduce
            ? 'ril2.riproduce'
            : p.riproduce_un_figlio
              ? 'ril2.riproduce_figlio'
              : 'ril2.non_riproduce',
        )}
      </span>
      {p.perche && <span className="vis__perche">{etichettaValore(t, 'ril_perche', p.perche)}</span>}
    </div>
  )
}

function Diagnostica() {
  const t = useT()
  const [d, setD] = useState<DiagnosticaRilevamento | null>(null)
  const [aperto, setAperto] = useState(false)

  const leggi = useCallback(async () => {
    const r = await window.scriba.get<DiagnosticaRilevamento>('/rilevamento/diagnostica')
    if (r.ok) setD(r.body)
  }, [])

  // Si interroga solo mentre il pannello è aperto, ogni due secondi: è il
  // ritmo con cui la sonda stessa produce le letture, e chiedere più spesso
  // non mostrerebbe niente di nuovo.
  useEffect(() => {
    if (!aperto) return
    leggi()
    const t = setInterval(leggi, 2000)
    return () => clearInterval(t)
  }, [aperto, leggi])

  if (!aperto) {
    return (
      <div className="row">
        <div className="row__t">
          <b>{t('ril.vede_ora')}</b>
          <span>
            {t('ril.vede_nota')}
          </span>
        </div>
        <button className="btn" onClick={() => setAperto(true)}>
          {t('ril.mostra')}
        </button>
      </div>
    )
  }

  return (
    <>
      <div className="row">
        <div className="row__t">
          <b>{t('ril2.vede')}</b>
          <span>{t('ril.aggiorna')}</span>
        </div>
        <button className="btn" onClick={() => setAperto(false)}>
          {t('ril.nascondi')}
        </button>
      </div>

      {d === null ? (
        <p className="vis__nota">{t('ril.chiedo')}</p>
      ) : d.spento ? (
        <div className="alert alert--inline">
          <p>
            {t('ril.spento')}
          </p>
        </div>
      ) : (
        <div className="vis">
          <div className="vis__stato">
            <span>
              {d.sonda?.viva
                ? t('ril2.sonda_attiva')
                : d.in_ascolto
                  ? t('ril2.sonda_spenta')
                  : t('ril2.non_in_ascolto')}
            </span>
            {d.sonda?.ultima_lettura_fa_s != null && (
              <span>{t('ril2.ultima_lettura', { s: d.sonda.ultima_lettura_fa_s })}</span>
            )}
            {d.conferma_s != null && <span>{t('ril2.conferma_dopo', { s: d.conferma_s })}</span>}
            {d.sonda != null && d.sonda.ripartenze > 0 && (
              <span>{t('ril2.ripartenze', { n: d.sonda.ripartenze })}</span>
            )}
          </div>

          {d.sonda?.rinunciato && (
            <div className="alert alert--inline">
              <p>
                {t('ril2.rinunciato')}
                {d.sonda.ultimo_motivo ? ` ${t('ril2.ultimo_motivo', { m: d.sonda.ultimo_motivo })}` : ''}
              </p>
            </div>
          )}

          {/* Una sonda che non ha ancora riferito e una stanza in cui nessuno usa
              il microfono danno lo stesso elenco vuoto, e sono due situazioni
              opposte: la prima è un guasto, la seconda è tutto a posto.
              Distinguerle è metà del motivo per cui questo pannello esiste. */}
          {d.sonda != null && d.sonda.ultima_lettura_fa_s === null ? (
            <p className="vis__nota">
              {t('ril.sonda_muta')}
            </p>
          ) : d.sonda != null &&
            d.intervallo_s != null &&
            d.sonda.ultima_lettura_fa_s != null &&
            d.sonda.ultima_lettura_fa_s > d.intervallo_s * 3 ? (
            <p className="vis__nota">
              {t('ril2.sonda_zitta', { s: d.sonda.ultima_lettura_fa_s, ogni: d.intervallo_s })}
            </p>
          ) : d.processi.length === 0 ? (
            <p className="vis__nota">
              {t('ril.nessuna_app')}
            </p>
          ) : (
            d.processi.map((p) => <Processo key={p.pid} p={p} />)
          )}

          {d.riproducono.length > 0 && (
            <p className="vis__nota">
              Riproducono audio (per numero di processo): {d.riproducono.join(', ')}
            </p>
          )}
        </div>
      )}
    </>
  )
}

export function SezioneRilevamento({
  impostazioni,
  onCambia,
}: {
  impostazioni: Impostazioni
  onCambia: (patch: Partial<Impostazioni>) => void
}) {
  const t = useT()
  const r = impostazioni.rilevamento
  const cambia = (patch: Partial<Impostazioni['rilevamento']>) => onCambia({ rilevamento: { ...r, ...patch } })

  return (
    <>
      <div className="settings__head">{t('ril.titolo')}</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__t">
            <b>{t('ril.accorgiti')}</b>
            <span>{t('ril.accorgiti_nota')}</span>
          </div>
          <button
            className={`switch ${r.attivo ? 'is-on' : ''}`}
            aria-pressed={r.attivo}
            onClick={() => cambia({ attivo: !r.attivo })}
          >
            <span className="sq" />
            {r.attivo ? 'Attivo' : 'Spento'}
          </button>
        </div>
        <div className="row">
          <div className="row__t">
            <b>{t('ril.aspetta')}</b>
            <span>{t('ril.aspetta_nota')}</span>
          </div>
          <div className="stepper">
            <button onClick={() => cambia({ conferma_s: Math.max(0, r.conferma_s - 5) })}>−</button>
            <span>{r.conferma_s} s</span>
            <button onClick={() => cambia({ conferma_s: r.conferma_s + 5 })}>+</button>
          </div>
        </div>
        <div className="row">
          <div className="row__t">
            <b>{t('ril.cosa_fare')}</b>
            <span>{t('ril.cosa_fare_nota')}</span>
          </div>
          <div className="picker">
            <button className={!r.avvio_automatico ? 'is-on' : ''} onClick={() => cambia({ avvio_automatico: false })}>
              {t('ril.proponi')}
            </button>
            <button className={r.avvio_automatico ? 'is-on' : ''} onClick={() => cambia({ avvio_automatico: true })}>
              {t('ril.avvia')}
            </button>
          </div>
        </div>

        <Diagnostica />
      </div>
    </>
  )
}
