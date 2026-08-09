/**
 * Cartella di export e formato. Il collegamento a Notion sta in `Notion.tsx`:
 * ha una sua schermata a passi, e tenerlo qui avrebbe reso questo file una
 * cosa sola con quello.
 */

import type { Impostazioni } from '../tipi'
import { SezioneNotion } from './Notion'
import { useT } from '../lingua'

const FORMATI = [
  { id: 'markdown', etichetta: 'Markdown' },
  { id: 'testo', etichetta: 'Testo' },
  { id: 'json', etichetta: 'JSON' },
  { id: 'contesto', etichetta: "Per l'IA" },
] as const

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
            {FORMATI.map((f) => (
              <button
                key={f.id}
                className={esp.formato === f.id ? 'is-on' : ''}
                onClick={() => onCambia({ export: { ...esp, formato: f.id } })}
              >
                {f.etichetta}
              </button>
            ))}
          </div>
        </div>
        <SezioneNotion />
      </div>
    </>
  )
}
