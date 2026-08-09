/**
 * Colonna a sinistra: l'elenco delle call.
 *
 * Ha due forme. Quella normale, tre righe per call. E quella a binario stretto
 * (`.calls--rail`) quando il pannello prove e' aperto: la trascrizione non si
 * restringe mai, perche' e' li' che si verifica la prova, e a fare spazio e'
 * l'elenco.
 *
 * **La terza riga non dice piu' lo stato.** «Analizzata» ripetuto in colonna
 * sei volte non informa nessuno (comportamento.md, 0-bis): informa il numero
 * di task, informa quante aspettano una conferma, e informa il guasto. Cosi'
 * la riga porta il cliente a sinistra e il conteggio a destra, e la call resta
 * di tre righe invece di quattro.
 */

import { useLocale, useT, type Traduci } from './lingua'
import { giornoBreve, tempo, type Sessione, type StatoSessione } from './tipi'

/**
 * Cosa scrivere a destra sulla terza riga, e con che peso.
 *
 * L'ordine e' una scala di urgenza, non un elenco di casi: quello che blocca
 * viene prima di quello che aspetta, che viene prima di quello che e' fatto.
 * Il rosso resta ai suoi due usi legittimi qui — registrazione in corso e
 * guasto — e non compare per nient'altro (regola 17).
 */
function codaCall(
  s: Sessione,
  stato: StatoSessione,
  t: Traduci,
): { testo: string; classe: string } {
  if (stato === 'recording') return { testo: t('call.in_registrazione'), classe: 'call__todo--err' }
  if (stato === 'failed') return { testo: t('call.non_riuscita'), classe: 'call__todo--err' }
  if (stato === 'analyzing') return { testo: t('call.in_analisi'), classe: '' }
  if (s.n_da_confermare > 0) {
    return {
      testo: t('call.n_da_confermare', { n: s.n_da_confermare }),
      classe: 'call__todo--now num',
    }
  }
  if (s.n_task > 0) return { testo: t('call.n_task', { n: s.n_task }), classe: 'num' }
  // Registrata e non ancora analizzata: qui lo stato **e'** l'informazione,
  // perche' nomina una cosa da fare. Diverso da «analizzata», che nomina una
  // cosa gia' successa e che si legge gia' dal conteggio delle task.
  if (stato === 'recorded') return { testo: t('call.da_analizzare'), classe: '' }
  return { testo: t('call.nessun_impegno'), classe: '' }
}

export function ElencoCall(props: {
  sessioni: Sessione[]
  sessioneVista: number | null
  sessioneCorrente: number | null
  /** true quando il pannello prove e' aperto: si stringe a binario. */
  compatta: boolean
  onApri: (id: number) => void
  /** clic sul `›` del binario: richiude il pannello prove e riapre l'elenco. */
  onRiapri: () => void
}) {
  const t = useT()
  const locale = useLocale()
  const { sessioni, sessioneVista, sessioneCorrente, compatta, onApri, onRiapri } = props

  if (compatta) {
    return (
      <aside className="calls calls--rail">
        <button className="btn btn--icon" aria-label={t('call.sezione')} onClick={onRiapri}>
          ›
        </button>
        {sessioni.map((s) => (
          <button
            key={s.id}
            className={`callmini num ${sessioneVista === s.id ? 'is-selected' : ''}`}
            onClick={() => onApri(s.id)}
          >
            {s.id}
          </button>
        ))}
      </aside>
    )
  }

  if (sessioni.length === 0) {
    return (
      <aside className="calls">
        <div className="calls__head">
          <span className="thread" />
          <span className="label">{t('call.sezione')}</span>
        </div>
        <div className="calls__vuoto">
          <p>{t('call.vuoto')}</p>
          <p className="calls__vuoto-nota">{t('call.vuoto_nota')}</p>
        </div>
      </aside>
    )
  }

  return (
    <aside className="calls">
      <div className="calls__head">
        <span className="thread" />
        <span className="label">{t('call.sezione')}</span>
        <span className="calls__count num">{sessioni.length}</span>
      </div>
      <div className="calls__list">
        {sessioni.map((s) => {
          const { testo, classe } = codaCall(s, s.stato, t)
          return (
            <button
              key={s.id}
              className={`call ${sessioneVista === s.id ? 'is-selected' : ''} ${
                sessioneCorrente === s.id ? 'is-current' : ''
              }`}
              onClick={() => onApri(s.id)}
            >
              <span className="call__title">{s.titolo || t('call.senza_titolo', { n: s.id })}</span>
              <span className="call__meta">
                <span className="num">{giornoBreve(s.started_at, locale, t('data.oggi'))}</span>
                <span className="call__sep">·</span>
                <span className="num">{s.durata_ms != null ? tempo(s.durata_ms) : '—'}</span>
              </span>
              <span className="call__foot">
                <span className={`call__client${s.cliente ? '' : ' is-none'}`}>
                  {s.cliente || t('call.senza_cliente')}
                </span>
                <span className={`call__todo ${classe}`}>{testo}</span>
              </span>
            </button>
          )
        })}
      </div>
    </aside>
  )
}
