/**
 * Rilevamento automatico delle call.
 *
 * Il testo della terza riga ripete che il consenso resta obbligatorio anche
 * avviando da sola: va tenuto così com'è, la registrazione non deve mai
 * partire senza la spunta (istruzioni del task).
 */

import type { Impostazioni } from '../tipi'

export function SezioneRilevamento({
  impostazioni,
  onCambia,
}: {
  impostazioni: Impostazioni
  onCambia: (patch: Partial<Impostazioni>) => void
}) {
  const r = impostazioni.rilevamento
  const cambia = (patch: Partial<Impostazioni['rilevamento']>) => onCambia({ rilevamento: { ...r, ...patch } })

  return (
    <>
      <div className="settings__head">Rilevamento automatico delle call</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__text">
            <b>Accorgiti da solo quando entro in call</b>
            <span>Guarda quali applicazioni stanno usando il microfono. Non legge il contenuto della riunione.</span>
          </div>
          <button className={`switch ${r.attivo ? 'is-on' : ''}`} onClick={() => cambia({ attivo: !r.attivo })}>
            <i />
          </button>
        </div>
        <div className="row">
          <div className="row__text">
            <b>Aspetta prima di propormelo</b>
            <span>Evita la proposta per le chiamate di dieci secondi.</span>
          </div>
          <div className="stepper">
            <button onClick={() => cambia({ conferma_s: Math.max(0, r.conferma_s - 5) })}>−</button>
            <span>{r.conferma_s} s</span>
            <button onClick={() => cambia({ conferma_s: r.conferma_s + 5 })}>+</button>
          </div>
        </div>
        <div className="row">
          <div className="row__text">
            <b>Cosa fare quando la rileva</b>
            <span>Anche avviando da sola, il consenso resta obbligatorio: la registrazione parte solo dopo la spunta.</span>
          </div>
          <div className="segment">
            <button className={!r.avvio_automatico ? 'is-on' : ''} onClick={() => cambia({ avvio_automatico: false })}>
              Proponi
            </button>
            <button className={r.avvio_automatico ? 'is-on' : ''} onClick={() => cambia({ avvio_automatico: true })}>
              Avvia da sola
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
