/**
 * Aspetto dell'interfaccia.
 *
 * Per ora c'è il tema e basta, ma è la casa giusta anche per quello che
 * riguarda l'overlay (righe, opacità) quando lo si esporrà: sono impostazioni
 * su come Scriba si vede, non su cosa fa.
 *
 * Il cambio si applica subito e a tutte le finestre, non al prossimo avvio:
 * scegliere un tema e non vederlo è il modo più veloce per far credere che il
 * comando non funzioni.
 */

import type { Impostazioni } from '../tipi'
import { applica, temaValido, type Tema } from '../tema'

const TEMI: Array<{ id: Tema; etichetta: string }> = [
  { id: 'scuro', etichetta: 'Scuro' },
  { id: 'chiaro', etichetta: 'Chiaro' },
  { id: 'sistema', etichetta: 'Come il sistema' },
]

export function SezioneAspetto({
  impostazioni,
  onCambia,
}: {
  impostazioni: Impostazioni
  onCambia: (patch: Partial<Impostazioni>) => void
}) {
  const i = impostazioni.interfaccia
  const tema = temaValido(i.tema)

  const scegli = (nuovo: Tema) => {
    // Prima si vede, poi si salva. Il salvataggio è un giro fino al core e
    // ritorno: aspettarlo per cambiare colore renderebbe il pulsante lento
    // senza motivo, e se fallisce lo dice la finestra con il suo avviso.
    applica(nuovo)
    window.scriba.annunciaTema(nuovo)
    onCambia({ interfaccia: { ...i, tema: nuovo } })
  }

  return (
    <>
      <div className="settings__head">Aspetto</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__t">
            <b>Tema</b>
            <span>
              «Come il sistema» segue Windows, anche quando cambia da solo al tramonto. Vale
              subito, senza riavviare. La striscia di trascrizione resta scura in ogni caso: sta
              sopra la finestra della riunione, e lì il bianco abbaglia.
            </span>
          </div>
          <div className="picker">
            {TEMI.map((t) => (
              <button
                key={t.id}
                className={tema === t.id ? 'is-on' : ''}
                onClick={() => scegli(t.id)}
              >
                {t.etichetta}
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
