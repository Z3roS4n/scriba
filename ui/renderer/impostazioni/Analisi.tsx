/**
 * Quando analizzare, e il rischio delle note incrementali.
 *
 * Due tipi di impostazione, da distinguere visivamente (comportamento.md):
 * la prima è una preferenza qualunque (`.row`), la seconda ha conseguenze —
 * con un motore in rete vuol dire mandare fuori la trascrizione più volte
 * durante la riunione, non una sola alla fine — e per questo porta il
 * filetto rosso (`.row--risk`) con la conseguenza scritta sotto.
 */

import type { Impostazioni } from '../tipi'
import { useT } from '../lingua'

/** Minuti fra una nota e l'altra. Sotto i cinque il modello lavorerebbe quasi
 *  di continuo sulla stessa macchina che sta trascrivendo dal vivo. */
const INTERVALLI = [5, 10, 15] as const

export function SezioneAnalisi({
  impostazioni,
  onCambia,
}: {
  impostazioni: Impostazioni
  onCambia: (patch: Partial<Impostazioni>) => void
}) {
  const t = useT()
  return (
    <>
      <div className="settings__head">{t('ana.titolo')}</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__t">
            <b>{t('ana.quando')}</b>
            <span>{t('ana.quando_nota')}</span>
          </div>
          <div className="picker">
            <button
              className={impostazioni.analisi_automatica ? 'is-on' : ''}
              onClick={() => onCambia({ analisi_automatica: true })}
            >
              {t('ana.fine_call')}
            </button>
            <button
              className={!impostazioni.analisi_automatica ? 'is-on' : ''}
              onClick={() => onCambia({ analisi_automatica: false })}
            >
              {t('ana.richiesta')}
            </button>
          </div>
        </div>
        <div className="row row--risk">
          <div className="row__t">
            <b>{t('ana.note')}</b>
            <span>{t('ana.note_nota')}</span>
            <span className="row__rischio">
              {t('ana.note_rete')}
            </span>
          </div>
          <button
            className={`switch ${impostazioni.note_incrementali ? 'is-on' : ''}`}
            aria-pressed={impostazioni.note_incrementali}
            onClick={() => onCambia({ note_incrementali: !impostazioni.note_incrementali })}
          >
            <span className="sq" />
            {impostazioni.note_incrementali ? 'Attivo' : 'Spento'}
          </button>
        </div>
        {impostazioni.note_incrementali && (
          <div className="row">
            <div className="row__t">
              <b>{t('ana.ogni_quanto')}</b>
              <span>
                {t('ana.ogni_quanto_nota')}
              </span>
            </div>
            <div className="picker">
              {INTERVALLI.map((m) => (
                <button
                  key={m}
                  className={
                    (impostazioni.note_incrementali_intervallo_s ?? 600) === m * 60 ? 'is-on' : ''
                  }
                  onClick={() => onCambia({ note_incrementali_intervallo_s: m * 60 })}
                >
                  {m} min
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
