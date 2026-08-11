/**
 * Cartella di export e formato. Il collegamento a Notion sta in `Notion.tsx`:
 * ha una sua schermata a passi, e tenerlo qui avrebbe reso questo file una
 * cosa sola con quello.
 */

import type { Impostazioni } from '../tipi'
import { SezioneNotion } from './Notion'
import { etichettaValore, useT } from '../lingua'

/* Tre nomi su quattro sono nomi propri di formato e non si traducono.
   «Per l'IA» sì, ed è per questo che l'elenco non può più essere una
   costante di modulo: là fuori il traduttore non c'è. */
const FORMATI = ['markdown', 'testo', 'json', 'contesto'] as const

export function SezioneExport({
  impostazioni,
  onCambia,
  onCambiaCartella,
}: {
  impostazioni: Impostazioni
  onCambia: (patch: Partial<Impostazioni>) => void
  onCambiaCartella: () => void
}) {
  const t = useT()
  const esp = impostazioni.export ?? { cartella: null, formato: 'markdown' as const }

  return (
    <>
      <div className="settings__head">{t('exp.titolo')}</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__t">
            <b>{t('exp.cartella')}</b>
            <span style={{ fontFamily: 'var(--font-code)' }}>{esp.cartella ?? t('exp2.non_scelta')}</span>
          </div>
          <button className="btn" onClick={onCambiaCartella}>
            {t('exp.cambia')}
          </button>
        </div>
        <div className="row">
          <div className="row__t">
            <b>{t('exp.formato')}</b>
            <span>
              {t('exp.formato_nota')}
            </span>
          </div>
          <div className="picker">
            {FORMATI.map((id) => (
              <button
                key={id}
                className={esp.formato === id ? 'is-on' : ''}
                onClick={() => onCambia({ export: { ...esp, formato: id } })}
              >
                {etichettaValore(t, 'formato', id)}
              </button>
            ))}
          </div>
        </div>
        <SezioneNotion />
      </div>
    </>
  )
}
