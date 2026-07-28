/**
 * Pannello di analisi: riassunto, punti salienti e revisione delle task.
 *
 * La parte che conta e' la revisione. Le task le propone un modello, e un
 * modello sbaglia: ogni campo mostra accanto il minuto della call da cui
 * proviene, cliccabile per andare a leggere il punto esatto. Serve a poter
 * controllare invece di doversi fidare.
 */

import { memo, useCallback, useEffect, useState } from 'react'

export interface Evidence {
  supports: string
  t_ms: number
  quote: string | null
  segment_id: number | null
}

export interface Task {
  id: number
  titolo: string
  descrizione: string | null
  assignee_text: string | null
  due_date: string | null
  due_raw: string | null
  priorita: string | null
  stato: string
  confidence: number | null
  needs_review: number
  review_reason: string | null
  evidence: Evidence[]
}

export interface Analisi {
  riassunto: string | null
  punti_salienti: string | null
  tasks: Task[]
}

const ETICHETTA_CAMPO: Record<string, string> = {
  titolo: 'Titolo',
  descrizione: 'Descrizione',
  assignee: 'Responsabile',
  due_date: 'Scadenza',
  priorita: 'Priorità',
  esistenza: 'Origine',
}

function tempo(ms: number): string {
  const t = Math.max(0, Math.floor(ms / 1000))
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
}

/**
 * Rende il Markdown prodotto dal modello.
 *
 * Volutamente minimale e senza librerie: si gestiscono intestazioni, elenchi e
 * grassetto, e tutto il resto resta testo. Il contenuto arriva da un modello di
 * linguaggio, quindi non gli si concede di produrre HTML arbitrario.
 */
const Markdown = memo(function Markdown({ testo }: { testo: string }) {
  const blocchi: React.ReactNode[] = []
  let elenco: string[] = []

  const chiudiElenco = () => {
    if (elenco.length) {
      blocchi.push(
        <ul key={`ul${blocchi.length}`}>
          {elenco.map((v, i) => (
            <li key={i}>{grassetto(v)}</li>
          ))}
        </ul>,
      )
      elenco = []
    }
  }

  for (const riga of testo.split('\n')) {
    const pulita = riga.trim()
    if (pulita.startsWith('## ')) {
      chiudiElenco()
      blocchi.push(<h2 key={blocchi.length}>{pulita.slice(3)}</h2>)
    } else if (pulita.startsWith('- ') || pulita.startsWith('* ')) {
      elenco.push(pulita.slice(2))
    } else if (pulita) {
      chiudiElenco()
      blocchi.push(<p key={blocchi.length}>{grassetto(pulita)}</p>)
    } else {
      chiudiElenco()
    }
  }
  chiudiElenco()

  return <div className="markdown">{blocchi}</div>
})

function grassetto(testo: string): React.ReactNode {
  const pezzi = testo.split(/(\*\*[^*]+\*\*)/g)
  return pezzi.map((p, i) =>
    p.startsWith('**') && p.endsWith('**') ? <b key={i}>{p.slice(2, -2)}</b> : p,
  )
}

function SchedaTask({
  task,
  onVaiA,
  onAggiorna,
}: {
  task: Task
  onVaiA: (t_ms: number) => void
  onAggiorna: (id: number, modifiche: Record<string, unknown>) => void
}) {
  // Le evidence sono per campo: qui si indicizzano per poter mostrare accanto a
  // ogni valore il punto della call che lo giustifica.
  const fonti = new Map<string, Evidence>()
  for (const e of task.evidence) if (!fonti.has(e.supports)) fonti.set(e.supports, e)

  const campo = (chiave: string, valore: string | null) => {
    if (!valore) return null
    const fonte = fonti.get(chiave)
    return (
      <span className="campo-con-fonte">
        <span className="etichetta">{ETICHETTA_CAMPO[chiave]}:</span>
        <span>{valore}</span>
        {fonte && (
          <button
            className="fonte"
            title="Vai al punto della call"
            onClick={() => onVaiA(fonte.t_ms)}
          >
            {tempo(fonte.t_ms)}
          </button>
        )}
      </span>
    )
  }

  const origine = fonti.get('titolo') ?? task.evidence[0]

  return (
    <div className={`task ${task.needs_review ? 'da-rivedere' : ''}`}>
      <div className="task-testa">
        <div className="task-titolo">{task.titolo}</div>
        {task.stato === 'confirmed' ? (
          <span className="badge confermata">Confermata</span>
        ) : task.needs_review ? (
          <span className="badge attenzione" title={task.review_reason ?? undefined}>
            Da rivedere
          </span>
        ) : null}
      </div>

      {task.descrizione && <p className="task-descrizione">{task.descrizione}</p>}

      <div className="task-campi">
        {campo('assignee', task.assignee_text)}
        {campo('due_date', task.due_date ?? task.due_raw)}
        {campo('priorita', task.priorita)}
      </div>

      {task.review_reason && (
        <p className="task-descrizione" style={{ fontSize: 12.5 }}>
          {task.review_reason}
        </p>
      )}

      {origine?.quote && (
        <p className="citazione">
          «{origine.quote}»
          <button className="fonte" onClick={() => onVaiA(origine.t_ms)}>
            {tempo(origine.t_ms)}
          </button>
        </p>
      )}

      {task.stato !== 'confirmed' && (
        <div className="task-azioni">
          <button className="primario" onClick={() => onAggiorna(task.id, { stato: 'confirmed' })}>
            Conferma
          </button>
          <button onClick={() => onAggiorna(task.id, { stato: 'rejected' })}>Scarta</button>
        </div>
      )}
    </div>
  )
}

export function PannelloAnalisi({
  sessionId,
  registrando,
  onVaiA,
}: {
  sessionId: number | null
  registrando: boolean
  onVaiA: (t_ms: number) => void
}) {
  const [analisi, setAnalisi] = useState<Analisi | null>(null)
  const [scheda, setScheda] = useState<'riassunto' | 'salienti' | 'task'>('riassunto')
  const [inCorso, setInCorso] = useState(false)
  const [errore, setErrore] = useState<string | null>(null)

  const carica = useCallback(async (id: number) => {
    const r = await window.scriba.get<Analisi>(`/sessions/${id}/analysis`)
    if (r.ok) setAnalisi(r.body)
  }, [])

  useEffect(() => {
    if (sessionId != null) carica(sessionId)
    else setAnalisi(null)
  }, [sessionId, carica])

  // La fine dell'analisi arriva da un evento.
  useEffect(() => {
    return window.scriba.on('core:event', (ev: { type?: string; stato?: string; session_id?: number; dettaglio?: string }) => {
      if (ev.type !== 'analisi') return
      if (ev.stato === 'in_corso') {
        setInCorso(true)
      } else {
        setInCorso(false)
        if (ev.stato === 'errore') setErrore(ev.dettaglio ?? 'Analisi non riuscita.')
        else if (ev.session_id != null) carica(ev.session_id)
      }
    })
  }, [carica])

  // Rete di sicurezza. Fidarsi solo degli eventi significa restare fermi per
  // sempre quando se ne perde uno, ed è successo davvero: due ore a mostrare
  // "analisi in corso" per un lavoro concluso da un pezzo. Finché la spia è
  // accesa si chiede al core come stanno le cose.
  useEffect(() => {
    if (!inCorso) return
    const timer = setInterval(async () => {
      const r = await window.scriba.get<{ in_corso: boolean }>('/analisi/stato')
      if (r.ok && !r.body.in_corso) {
        setInCorso(false)
        if (sessionId != null) carica(sessionId)
      }
    }, 5000)
    return () => clearInterval(timer)
  }, [inCorso, sessionId, carica])

  const analizza = async () => {
    if (sessionId == null) return
    setErrore(null)
    setInCorso(true)
    try {
      // La risposta dice solo che il lavoro è partito: dura minuti, e la fine
      // arriva da un evento. Aspettarla qui non funzionava — la richiesta
      // scadeva molto prima.
      const r = await window.scriba.post<{ detail?: string }>(`/sessions/${sessionId}/analyze`)
      if (!r.ok) {
        setInCorso(false)
        setErrore(r.body?.detail ?? `Analisi non riuscita (${r.status}).`)
      }
    } catch (e) {
      // Senza questo, un errore lasciava la spia accesa per sempre.
      setInCorso(false)
      setErrore(e instanceof Error ? e.message : String(e))
    }
  }

  const aggiorna = async (id: number, modifiche: Record<string, unknown>) => {
    await window.scriba.post(`/tasks/${id}`, modifiche)
    if (sessionId != null) carica(sessionId)
  }

  if (sessionId == null) {
    return <div className="vuoto">Seleziona una call per vederne l'analisi.</div>
  }

  const tasks = analisi?.tasks ?? []
  const daRivedere = tasks.filter((t) => t.needs_review && t.stato !== 'confirmed').length
  const nulla = !analisi?.riassunto && !analisi?.punti_salienti && tasks.length === 0

  return (
    <>
      <div className="schede">
        <button
          className={`scheda ${scheda === 'riassunto' ? 'attiva' : ''}`}
          onClick={() => setScheda('riassunto')}
        >
          Riassunto
        </button>
        <button
          className={`scheda ${scheda === 'salienti' ? 'attiva' : ''}`}
          onClick={() => setScheda('salienti')}
        >
          Punti salienti
        </button>
        <button
          className={`scheda ${scheda === 'task' ? 'attiva' : ''}`}
          onClick={() => setScheda('task')}
        >
          Task{tasks.length ? ` (${tasks.length})` : ''}
          {daRivedere > 0 && ' •'}
        </button>
      </div>

      <div className="pannello">
        <div className="barra-analisi">
          <button className="primario" onClick={analizza} disabled={inCorso || registrando}>
            {inCorso ? 'Analisi in corso...' : nulla ? 'Analizza la call' : 'Rianalizza'}
          </button>
          {registrando && (
            <span style={{ color: 'var(--testo-fioco)', fontSize: 13 }}>
              L'analisi si fa a call finita.
            </span>
          )}
          {errore && <div className="avviso">{errore}</div>}
        </div>

        {nulla && !inCorso && (
          <p style={{ color: 'var(--testo-fioco)' }}>
            Questa call non è ancora stata analizzata.
          </p>
        )}

        {scheda === 'riassunto' && analisi?.riassunto && <Markdown testo={analisi.riassunto} />}
        {scheda === 'salienti' && analisi?.punti_salienti && (
          <Markdown testo={analisi.punti_salienti} />
        )}
        {scheda === 'task' &&
          (tasks.length === 0 ? (
            !nulla && <p style={{ color: 'var(--testo-fioco)' }}>Nessun impegno individuato.</p>
          ) : (
            <>
              {daRivedere > 0 && (
                <p style={{ color: 'var(--testo-tenue)', marginTop: 0 }}>
                  {daRivedere} {daRivedere === 1 ? 'task richiede' : 'task richiedono'} una
                  verifica: il modello non era sicuro, o mancava un dato.
                </p>
              )}
              {tasks.map((t) => (
                <SchedaTask key={t.id} task={t} onVaiA={onVaiA} onAggiorna={aggiorna} />
              ))}
            </>
          ))}
      </div>
    </>
  )
}
