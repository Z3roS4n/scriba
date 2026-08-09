/**
 * Lingua, dispositivi audio e filtro dell'eco.
 *
 * I selettori sono `.select` — un <button> più il menù di Select.tsx — mai un
 * <select> nativo: su Windows ignorerebbe il tema scuro (comportamento.md,
 * punto 10).
 */

import { useEffect, useState } from 'react'

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
const LIVELLI_GLOSSARIO = [
  { id: 'prudente', etichetta: 'Prudente', nota: 'Solo una lettera di scarto. Non sbaglia quasi mai, e non prende le storpiature grosse.' },
  { id: 'medio', etichetta: 'Medio', nota: 'Prende anche i nomi mangiati all’inizio o alla fine («Tilde» per «Clotilde»).' },
  { id: 'aggressivo', etichetta: 'Aggressivo', nota: 'Prende anche «Protile». Può correggere un nome simile in quello sbagliato.' },
] as const

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
  const stt = impostazioni.stt

  return (
    <>
      <div className="settings__head">Trascrizione</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__t">
            <b>Lingua delle call</b>
            {/* Diceva solo cosa succede alla trascrizione. Ma da questa scelta
                dipende anche in che lingua vengono scritti riassunto, punti
                salienti e task: chi la cambia deve saperlo prima, non
                scoprirlo leggendo un riassunto nella lingua sbagliata. */}
            <span>
              Vale per la trascrizione e per quello che ne viene ricavato: riassunto, punti
              salienti e task escono in questa lingua. Le altre vengono riconosciute lo stesso,
              ma con più errori sui nomi.
            </span>
          </div>
          <Select opzioni={LINGUE} selezionato={stt.lingua} onScegli={(lingua) => onCambia({ stt: { ...stt, lingua } })} />
        </div>
        <div className="row">
          <div className="row__t">
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
          <div className="row__t">
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
          <div className="row__t">
            <b>Filtro dell’eco</b>
            <span>Riconosce quando il microfono riprende l’altoparlante. Se alzi troppo, le sovrapposizioni di voce si perdono.</span>
          </div>
          <div className="picker">
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

        <div className="settings__sub">Dopo la call</div>

        <div className="row">
          <div className="row__t">
            <b>Rifai la trascrizione da sola</b>
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

        <div className="settings__sub">Nomi propri</div>

        <div className="row row--stack">
          <div className="row__t">
            <b>Glossario</b>
            <span>
              I nomi che il modello non conosce li indovina da capo a ogni frase, e ogni volta in
              modo diverso: nella stessa call «Clotilde» diventa Tilde, Cotilde e Protile. Scrivili
              qui, uno per riga, e vengono rimessi a posto a frase finita. Il testo di partenza
              resta salvato.
            </span>
          </div>
          <Elenco
            termini={stt.glossario ?? []}
            onSalva={(glossario) => onCambia({ stt: { ...stt, glossario } })}
          />
        </div>

        <div className="row">
          <div className="row__t">
            <b>Anche i clienti</b>
            <span>I nomi dell’anagrafica entrano nel glossario da soli, senza riscriverli qui.</span>
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
            <b>Quanto insistere</b>
            <span>
              {LIVELLI_GLOSSARIO.find((l) => l.id === (stt.glossario_livello ?? 'prudente'))?.nota}
            </span>
          </div>
          <div className="picker">
            {LIVELLI_GLOSSARIO.map((l) => (
              <button
                key={l.id}
                className={(stt.glossario_livello ?? 'prudente') === l.id ? 'is-on' : ''}
                onClick={() => onCambia({ stt: { ...stt, glossario_livello: l.id } })}
              >
                {l.etichetta}
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
