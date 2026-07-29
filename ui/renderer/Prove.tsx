/**
 * Pannello prove: da dove viene ogni campo di una task.
 *
 * Le prove sono per campo, non per task — è quello che rende ricostruibile
 * una task nominata al minuto 5, con la scadenza al 32 e il responsabile al
 * 48: ogni riga qui sotto è un campo diverso, con il suo minuto e la sua
 * frase, non un riassunto della task intera.
 */

import type { Task } from './tipi'
import { tempo } from './tipi'

/** Come va scritto il campo sopra la citazione: maiuscolo, come sul chip. */
const ETICHETTA_CAMPO: Record<string, string> = {
  titolo: 'TITOLO',
  descrizione: 'DESCRIZIONE',
  assignee: 'CHI',
  due_date: 'SCADENZA',
  priorita: 'PRIORITÀ',
  esistenza: 'ORIGINE',
}

export function PannelloProve({
  task,
  onVaiA,
  onChiudi,
}: {
  task: Task
  onVaiA: (t_ms: number) => void
  onChiudi: () => void
}) {
  return (
    <aside className="evidence">
      <div className="evidence__head">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span className="label">PROVE</span>
          <button className="btn--link" onClick={onChiudi} aria-label="Chiudi le prove">
            ✕
          </button>
        </div>
        <p className="evidence__task">{task.titolo}</p>
      </div>
      <div className="evidence__list">
        {task.evidence.map((e, i) => (
          // L'indice nella chiave copre il caso di due prove sullo stesso campo
          // (es. due frasi diverse che citano la scadenza).
          <div className="ev" key={`${e.supports}-${e.t_ms}-${i}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <button className="ev__t" onClick={() => onVaiA(e.t_ms)}>
                {tempo(e.t_ms)}
              </button>
              <span className="ev__field">{ETICHETTA_CAMPO[e.supports] ?? e.supports.toUpperCase()}</span>
            </div>
            {/* Una prova senza frase non si finge: si dice che è dedotta. */}
            <p className="ev__quote">{e.quote ?? 'Dedotta dal contesto, non da una frase precisa.'}</p>
          </div>
        ))}
        <p className="ev__note">
          Ogni campo della task viene da una di queste frasi. Se una prova non regge, il campo va corretto.
        </p>
      </div>
    </aside>
  )
}
