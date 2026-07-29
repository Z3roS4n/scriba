/**
 * Cartella di export, formato, e la riga Notion — non disponibile per ora.
 */

import type { Impostazioni } from '../tipi'

const FORMATI = [
  { id: 'markdown', etichetta: 'Markdown' },
  { id: 'testo', etichetta: 'Testo' },
  { id: 'json', etichetta: 'JSON' },
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
            <span>Il markdown contiene anche i minuti delle prove.</span>
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
        <div className="row is-unavailable">
          <div className="row__text">
            <b style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
              Manda le task a Notion <span className="badge-off">NON DISPONIBILE</span>
            </b>
            <span>Le task confermate finirebbero in un database di Notion, con il minuto della prova come collegamento.</span>
          </div>
          <button className="btn" disabled>
            Collega
          </button>
        </div>
      </div>
    </>
  )
}
