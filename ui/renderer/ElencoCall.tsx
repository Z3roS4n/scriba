/**
 * Colonna a sinistra: l'elenco delle call.
 *
 * Ha due forme. Quella normale, con titolo/data/stato di ogni call. E quella a
 * binario stretto (`.calls--rail`, 46px) quando il pannello prove e' aperto: la
 * trascrizione non si restringe mai, perche' e' li' che si verifica la prova, e
 * a fare spazio e' l'elenco.
 */

import { dataBreve, tempo, type Sessione, type StatoSessione } from './tipi'

/** Testo e modificatore di `.call__status` per ciascuno stato della sessione. */
function statoCall(stato: StatoSessione): { testo: string; classe: string } {
  switch (stato) {
    case 'recording':
      return { testo: 'in corso', classe: 'call__status--rec' }
    case 'analyzed':
      return { testo: 'analizzata', classe: 'call__status--ok' }
    case 'failed':
      return { testo: 'analisi non riuscita', classe: 'call__status--err' }
    // 'analyzing' non e' fra i quattro testi del design: non essendo ne' un
    // esito positivo ne' un errore non prende un colore, solo un testo proprio.
    case 'analyzing':
      return { testo: 'in analisi', classe: '' }
    case 'recorded':
    default:
      return { testo: 'registrata', classe: '' }
  }
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
  const { sessioni, sessioneVista, sessioneCorrente, compatta, onApri, onRiapri } = props

  if (compatta) {
    return (
      <aside className="calls calls--rail">
        <button className="btn btn--icon" aria-label="Riapri elenco call" onClick={onRiapri}>
          ›
        </button>
        {sessioni.map((s) => (
          <div
            key={s.id}
            className={`callmini ${sessioneVista === s.id ? 'is-selected' : ''}`}
            onClick={() => onApri(s.id)}
          >
            {s.id}
          </div>
        ))}
      </aside>
    )
  }

  if (sessioni.length === 0) {
    return (
      <aside className="calls">
        <div className="calls__head">
          <span className="label">CALL</span>
        </div>
        <div className="pad" style={{ paddingTop: 0 }}>
          <p style={{ fontSize: 'var(--fs-md)', color: 'var(--fg4)', lineHeight: 1.5 }}>
            Nessuna call registrata.
          </p>
          <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--fg6)', lineHeight: 1.5 }}>
            Le registrazioni restano su questo computer.
          </p>
        </div>
      </aside>
    )
  }

  return (
    <aside className="calls">
      <div className="calls__head">
        <span className="label">CALL</span>
        <span className="count">
          {sessioni.length} {sessioni.length === 1 ? 'salvata' : 'salvate'}
        </span>
      </div>
      <div className="calls__list">
        {sessioni.map((s) => {
          const { testo, classe } = statoCall(s.stato)
          return (
            <div
              key={s.id}
              className={`call ${sessioneVista === s.id ? 'is-selected' : ''} ${
                sessioneCorrente === s.id ? 'is-current' : ''
              }`}
              onClick={() => onApri(s.id)}
            >
              <span className="call__title">{s.titolo || `Call #${s.id}`}</span>
              <span className="call__meta">
                {dataBreve(s.started_at)}
                <span>·</span>
                {s.durata_ms != null ? tempo(s.durata_ms) : '—'}
              </span>
              <span className={`call__status ${classe}`}>{testo}</span>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
