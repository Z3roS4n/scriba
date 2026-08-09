/**
 * Lingua, dispositivi audio e filtro dell'eco.
 *
 * I selettori sono `.select` — un <button> più il menù di Select.tsx — mai un
 * <select> nativo: su Windows ignorerebbe il tema scuro (comportamento.md,
 * punto 10).
 */

import { useEffect, useState } from 'react'

import { etichettaValore, useT } from '../lingua'
import type { Dispositivo, Impostazioni } from '../tipi'
import type { OpzioneSelect } from '../Select'
import { Select } from '../Select'

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

/** Quanto storpiata può essere una parola perché venga comunque riconosciuta.
 *  Le descrizioni dicono cosa si perde alzando, non solo cosa si guadagna:
 *  allargare la rete significa anche correggere nomi che erano già giusti, e
 *  quello — a differenza del nome sbagliato — rileggendo non si nota. */
const LIVELLI_GLOSSARIO = ['prudente', 'medio', 'aggressivo'] as const

/**
 * L'elenco dei nomi, uno per riga.
 *
 * Si salva quando il campo perde il fuoco, non a ogni tasto: qui si scrive un
 * elenco, e salvare a metà di un nome lo manderebbe nel glossario storpiato —
 * esattamente il problema che questa schermata esiste per risolvere.
 */
function Elenco({ termini, onSalva }: { termini: string[]; onSalva: (t: string[]) => void }) {
  const [testo, setTesto] = useState(termini.join('\n'))

  // Se le impostazioni cambiano da fuori (un altro salvataggio, una rilettura)
  // il campo si riallinea — ma non mentre ci si sta scrivendo dentro.
  useEffect(() => {
    setTesto((prec) => (prec.trim() === termini.join('\n').trim() ? prec : termini.join('\n')))
  }, [termini])

  return (
    <textarea
      className="textfield textfield--area"
      value={testo}
      rows={5}
      spellCheck={false}
      placeholder={'Clotilde\nBanca Sella\nGiulia'}
      onChange={(e) => setTesto(e.target.value)}
      onBlur={() => onSalva(testo.split('\n').map((r) => r.trim()).filter(Boolean))}
    />
  )
}

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
  const t = useT()
  const stt = impostazioni.stt

  return (
    <>
      <div className="settings__head">{t('tra2.titolo')}</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__t">
            <b>{t('tra2.lingua')}</b>
            {/* Diceva solo cosa succede alla trascrizione. Ma da questa scelta
                dipende anche in che lingua vengono scritti riassunto, punti
                salienti e task: chi la cambia deve saperlo prima, non
                scoprirlo leggendo un riassunto nella lingua sbagliata. */}
            <span>
              {t('tra2.lingua_nota')}
            </span>
          </div>
          <Select opzioni={LINGUE} selezionato={stt.lingua} onScegli={(lingua) => onCambia({ stt: { ...stt, lingua } })} />
        </div>
        <div className="row">
          <div className="row__t">
            <b>{t('tra2.microfono')}</b>
            <span>{t('tra2.microfono_nota')}</span>
          </div>
          <Select
            opzioni={microfoni.map((d) => ({ id: d.id, etichetta: d.nome }))}
            selezionato={stt.microfono_id ?? microfoni.find((d) => d.predefinito)?.id ?? null}
            onScegli={(microfono_id) => onCambia({ stt: { ...stt, microfono_id } })}
          />
        </div>
        <div className="row">
          <div className="row__t">
            <b>{t('tra2.loopback')}</b>
            <span>{t('tra2.loopback_nota')}</span>
          </div>
          <Select
            opzioni={loopback.map((d) => ({ id: d.id, etichetta: d.nome }))}
            selezionato={stt.loopback_id ?? loopback.find((d) => d.predefinito)?.id ?? null}
            onScegli={(loopback_id) => onCambia({ stt: { ...stt, loopback_id } })}
          />
        </div>
        <div className="row">
          <div className="row__t">
            <b>{t('tra2.filtro')}</b>
            <span>{t('tra2.filtro_nota')}</span>
          </div>
          <div className="picker">
            {FILTRI_ECO.map((v) => (
              <button
                key={v}
                className={(stt.filtro_eco ?? 'medio') === v ? 'is-on' : ''}
                onClick={() => onCambia({ stt: { ...stt, filtro_eco: v } })}
              >
                {etichettaValore(t, 'filtro', v)}
              </button>
            ))}
          </div>
        </div>

        <div className="settings__sub">{t('tra2.dopo')}</div>

        <div className="row">
          <div className="row__t">
            <b>{t('tra2.rifai')}</b>
            <span>
              A registrazione finita ripassa ogni riga con un modello più preciso, a cui la lingua si
              può imporre davvero — è la correzione per le frasi che finiscono in un’altra lingua.
              Costa qualche minuto di calcolo e un modello da scaricare (Modelli locali → Canary).
              Il comando resta comunque su ogni singola call.
            </span>
          </div>
          <button
            className={`switch ${stt.rifinitura_automatica ? 'is-on' : ''}`}
            aria-pressed={stt.rifinitura_automatica}
            onClick={() =>
              onCambia({ stt: { ...stt, rifinitura_automatica: !stt.rifinitura_automatica } })
            }
          >
            <span className="sq" />
            {stt.rifinitura_automatica ? 'Attivo' : 'Spento'}
          </button>
        </div>

        <div className="settings__sub">{t('tra2.nomi')}</div>

        <div className="row row--stack">
          <div className="row__t">
            <b>{t('tra2.glossario')}</b>
            <span>
              {t('tra2.glossario_nota')}
            </span>
          </div>
          <Elenco
            termini={stt.glossario ?? []}
            onSalva={(glossario) => onCambia({ stt: { ...stt, glossario } })}
          />
        </div>

        <div className="row">
          <div className="row__t">
            <b>{t('tra2.anche_clienti')}</b>
            <span>{t('tra2.anche_clienti_nota')}</span>
          </div>
          <button
            className={`switch ${stt.glossario_clienti !== false ? 'is-on' : ''}`}
            aria-pressed={stt.glossario_clienti !== false}
            onClick={() =>
              onCambia({ stt: { ...stt, glossario_clienti: stt.glossario_clienti === false } })
            }
          >
            <span className="sq" />
            {stt.glossario_clienti !== false ? 'Attivo' : 'Spento'}
          </button>
        </div>

        <div className="row row--stack">
          <div className="row__t">
            <b>{t('tra2.quanto')}</b>
            <span>
              {etichettaValore(t, 'gloss_nota', stt.glossario_livello ?? 'prudente')}
            </span>
          </div>
          <div className="picker">
            {LIVELLI_GLOSSARIO.map((id) => (
              <button
                key={id}
                className={(stt.glossario_livello ?? 'prudente') === id ? 'is-on' : ''}
                onClick={() => onCambia({ stt: { ...stt, glossario_livello: id } })}
              >
                {etichettaValore(t, 'gloss', id)}
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
