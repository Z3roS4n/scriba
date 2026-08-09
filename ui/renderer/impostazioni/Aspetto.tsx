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
import { linguaValida, useT, type Lingua } from '../lingua'
import { applica, temaValido, type Tema } from '../tema'
// gia importato

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
  const t = useT()
  const i = impostazioni.interfaccia
  const tema = temaValido(i.tema)
  const lingua = linguaValida(i.lingua)

  /** Le tre scelte, tradotte: l'elenco delle lingue si legge nella lingua in
   *  cui si sta guardando adesso, non in quella che nomina. */
  const LINGUE: Array<{ id: Lingua; etichetta: string }> = [
    { id: 'it', etichetta: t('lingua.it') },
    { id: 'en', etichetta: t('lingua.en') },
    { id: 'sistema', etichetta: t('lingua.sistema') },
  ]

  const scegliLingua = (nuova: Lingua) => {
    // Stessa regola del tema: prima si vede, poi si salva. Il giro fino al
    // core e ritorno non deve stare fra il clic e il testo che cambia.
    window.scriba.annunciaLingua(nuova)
    onCambia({ interfaccia: { ...i, lingua: nuova } })
  }

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
      <div className="settings__head">{t('asp.titolo')}</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__t">
            <b>{t('lingua.etichetta')}</b>
            <span>{t('lingua.nota')}</span>
          </div>
          <div className="picker">
            {LINGUE.map((l) => (
              <button
                key={l.id}
                className={lingua === l.id ? 'is-on' : ''}
                onClick={() => scegliLingua(l.id)}
              >
                {l.etichetta}
              </button>
            ))}
          </div>
        </div>

        <div className="row">
          <div className="row__t">
            <b>{t('asp.tema')}</b>
            <span>
              {t('asp.tema_nota')}
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
