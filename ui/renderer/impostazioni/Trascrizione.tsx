/**
 * Lingua, dispositivi audio e filtro dell'eco.
 *
 * I selettori sono `.select` — un <button> più il menù di Select.tsx — mai un
 * <select> nativo: su Windows ignorerebbe il tema scuro (comportamento.md,
 * punto 10).
 */

import type { Dispositivo, Impostazioni } from '../tipi'
import type { OpzioneSelect } from './Select'
import { Select } from './Select'

/** Non c'è una rotta che elenchi le lingue: è un insieme piccolo e fisso, a
 *  differenza dei dispositivi audio che dipendono dalla macchina. */
const LINGUE: OpzioneSelect[] = [
  { id: 'it', etichetta: 'Italiano' },
  { id: 'en', etichetta: 'Inglese' },
  { id: 'fr', etichetta: 'Francese' },
  { id: 'de', etichetta: 'Tedesco' },
  { id: 'es', etichetta: 'Spagnolo' },
  { id: 'pt', etichetta: 'Portoghese' },
]

const FILTRI_ECO = ['basso', 'medio', 'alto'] as const

export function SezioneTrascrizione({
  impostazioni,
  microfoni,
  loopback,
  onCambia,
}: {
  impostazioni: Impostazioni
  microfoni: Dispositivo[]
  loopback: Dispositivo[]
  onCambia: (patch: Partial<Impostazioni>) => void
}) {
  const stt = impostazioni.stt

  return (
    <>
      <div className="settings__head">Trascrizione</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__text">
            <b>Lingua principale</b>
            <span>Le altre lingue vengono riconosciute lo stesso, ma con più errori sui nomi.</span>
          </div>
          <Select opzioni={LINGUE} selezionato={stt.lingua} onScegli={(lingua) => onCambia({ stt: { ...stt, lingua } })} />
        </div>
        <div className="row">
          <div className="row__text">
            <b>Microfono</b>
            <span>Registra la tua voce.</span>
          </div>
          <Select
            opzioni={microfoni.map((d) => ({ id: d.id, etichetta: d.nome }))}
            selezionato={stt.microfono_id ?? microfoni.find((d) => d.predefinito)?.id ?? null}
            onScegli={(microfono_id) => onCambia({ stt: { ...stt, microfono_id } })}
          />
        </div>
        <div className="row">
          <div className="row__text">
            <b>Audio del computer</b>
            <span>Registra la voce degli altri. Senza questo si sente solo te.</span>
          </div>
          <Select
            opzioni={loopback.map((d) => ({ id: d.id, etichetta: d.nome }))}
            selezionato={stt.loopback_id ?? loopback.find((d) => d.predefinito)?.id ?? null}
            onScegli={(loopback_id) => onCambia({ stt: { ...stt, loopback_id } })}
          />
        </div>
        <div className="row">
          <div className="row__text">
            <b>Filtro dell’eco</b>
            <span>Riconosce quando il microfono riprende l’altoparlante. Se alzi troppo, le sovrapposizioni di voce si perdono.</span>
          </div>
          <div className="segment">
            {FILTRI_ECO.map((v) => (
              <button
                key={v}
                className={(stt.filtro_eco ?? 'medio') === v ? 'is-on' : ''}
                onClick={() => onCambia({ stt: { ...stt, filtro_eco: v } })}
              >
                {v[0].toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
