/**
 * Cartella di export e formato. Il collegamento a Notion sta in `Notion.tsx`:
 * ha una sua schermata a passi, e tenerlo qui avrebbe reso questo file una
 * cosa sola con quello.
 */

import type { Impostazioni } from '../tipi'
import { SezioneNotion } from './Notion'

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
  const esp = impostazioni.export ?? { cartella: null, formato: 'markdown' as const }

  return (
    <>
      <div className="settings__head">Export</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__text">
            <b>Cartella predefinita</b>
            <span style={{ fontFamily: 'var(--mono)' }}>{esp.cartella ?? 'Non ancora scelta'}</span>
          </div>
          <button className="btn" onClick={onCambiaCartella}>
            Cambia
          </button>
        </div>
        <div className="row">
          <div className="row__text">
            <b>Formato</b>
            <span>
              Il markdown contiene anche i minuti delle prove. Il testo è la trascrizione pulita,
              il JSON porta tutto — comprese le prove — in una forma per un programma. «Per l'IA»
              mette ogni citazione accanto a ciò che sostiene, invece di un riferimento da
              incrociare, e dice quali impegni una fonte non ce l'hanno: è fatto per essere
              incollato in un modello. Per esportarne più di una insieme c'è l'archivio.
            </span>
          </div>
          <div className="segment">
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
