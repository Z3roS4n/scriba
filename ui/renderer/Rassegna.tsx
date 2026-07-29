/**
 * Rassegna task: una task alla volta, con la prova sotto gli occhi.
 *
 * Le task le propone un modello, e un modello sbaglia con sicurezza: ogni
 * campo mostra da quale frase viene, o dice chiaramente che non ne ha una
 * invece di fingerla. Confermare è un ritmo (C / X / ← / →), non una serie
 * di scelte isolate, e si esce tornando alla task da cui si è entrati — per
 * questo l'indice corrente torna al chiamante invece di perdersi qui.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Analisi, CampoProva, Segmento, Sessione, Task } from './tipi'
import { dataBreve, tempo } from './tipi'

const CHI: Record<Segmento['source'], string> = { mic: 'Io', loopback: 'Altri' }

/** «14 ago 2026»: solo per la scadenza risolta, mai per i minuti della call. */
function dataEstesa(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' }).replace('.', '')
}

/** Stessa logica del chip scadenza in Analisi.tsx: data risolta, detta a voce
 * ma non risolta, o assente. Duplicata invece che importata perché lì è
 * privata del modulo — vedi la nota nel rapporto finale. */
function testoScadenza(t: Pick<Task, 'due_date' | 'due_raw'>): string | null {
  if (t.due_date) return `${dataEstesa(t.due_date)}${t.due_raw ? ` · «${t.due_raw}»` : ''}`
  if (t.due_raw) return `solo a voce: «${t.due_raw}»`
  return null
}

/** Solo questi quattro campi si modificano da qui: sono quelli del handoff,
 * e sono anche gli unici che il core accetta in POST /tasks/{id}. */
type ChiaveCampo = 'titolo' | 'assignee_text' | 'due_date' | 'priorita'

/** I quattro campi mostrati, nell'ordine del handoff. La chiave della task e
 * quella della prova non coincidono per il responsabile: la task la chiama
 * `assignee_text`, la prova la sostiene come `assignee`. */
const CAMPI: Array<{ chiave: ChiaveCampo; etichetta: string; prova: CampoProva }> = [
  { chiave: 'titolo', etichetta: 'Titolo', prova: 'titolo' },
  { chiave: 'assignee_text', etichetta: 'Responsabile', prova: 'assignee' },
  { chiave: 'due_date', etichetta: 'Scadenza', prova: 'due_date' },
  { chiave: 'priorita', etichetta: 'Priorità', prova: 'priorita' },
]

/** Il testo mostrato quando non si sta modificando, e se è un vuoto detto
 * apertamente («nessun responsabile») invece che uno spazio bianco. */
function valoreCampo(t: Task, chiave: ChiaveCampo): { testo: string; mancante: boolean } {
  switch (chiave) {
    case 'titolo':
      return { testo: t.titolo, mancante: false }
    case 'assignee_text':
      return t.assignee_text
        ? { testo: t.assignee_text, mancante: false }
        : { testo: 'nessun responsabile', mancante: true }
    case 'due_date': {
      const s = testoScadenza(t)
      return s ? { testo: s, mancante: false } : { testo: 'nessuna scadenza', mancante: true }
    }
    case 'priorita':
      return t.priorita ? { testo: t.priorita, mancante: false } : { testo: 'nessuna priorità', mancante: true }
  }
}

/** Il valore grezzo con cui si apre il campo di modifica: senza formattazioni
 * («14 ago 2026 · «...»»), altrimenti si andrebbe a salvare la formattazione
 * stessa come se fosse il dato. */
function valoreGrezzo(t: Task, chiave: ChiaveCampo): string {
  switch (chiave) {
    case 'titolo':
      return t.titolo
    case 'assignee_text':
      return t.assignee_text ?? ''
    case 'due_date':
      return t.due_date ?? ''
    case 'priorita':
      return t.priorita ?? ''
  }
}

/** Applica il campo modificato alla copia locale della task, in attesa (o a
 * conferma) della risposta del core. Il titolo non può restare vuoto: senza,
 * `salva` non arriva nemmeno a chiamare questa funzione con null. */
function applicaCampo(t: Task, chiave: ChiaveCampo, valore: string | null): Task {
  switch (chiave) {
    case 'titolo':
      return { ...t, titolo: valore ?? t.titolo, needs_review: 0 }
    case 'assignee_text':
      return { ...t, assignee_text: valore, needs_review: 0 }
    case 'due_date':
      return { ...t, due_date: valore, needs_review: 0 }
    case 'priorita':
      return { ...t, priorita: valore, needs_review: 0 }
  }
}

export function Rassegna(props: {
  sessione: Sessione
  segmenti: Segmento[]
  indiceIniziale: number
  onEsci: (indiceCorrente: number) => void
}): React.ReactElement {
  const { sessione, segmenti, indiceIniziale, onEsci } = props

  const [analisi, setAnalisi] = useState<Analisi | null>(null)
  const [indice, setIndice] = useState(indiceIniziale)
  const [editando, setEditando] = useState<ChiaveCampo | null>(null)
  const [bozza, setBozza] = useState('')

  const corpoRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let attiva = true
    window.scriba.get<Analisi>(`/sessions/${sessione.id}/analysis`).then((r) => {
      if (attiva && r.ok) setAnalisi(r.body)
    })
    return () => {
      attiva = false
    }
  }, [sessione.id])

  const tasks = useMemo(() => analisi?.tasks ?? [], [analisi])
  // L'indice arriva da fuori e resta dentro i confini anche se la lista è
  // più corta di quanto si aspettasse chi l'ha passato.
  const indiceSicuro = tasks.length > 0 ? Math.min(indice, tasks.length - 1) : 0
  const taskCorrente: Task | undefined = tasks[indiceSicuro]

  // Cambiando task si azzera un'eventuale modifica a metà: appartiene alla
  // task precedente, non a questa.
  useEffect(() => {
    setEditando(null)
  }, [indiceSicuro])

  const righeOrdinate = useMemo(() => [...segmenti].sort((a, b) => a.t_start_ms - b.t_start_ms), [segmenti])

  // Le righe citate dalla task in vista. Si preferisce segment_id, quando il
  // core lo manda, perché punta a una riga precisa; senza, si cerca quella
  // che copre il minuto della prova.
  const citate = useMemo(() => {
    const set = new Set<number>()
    if (!taskCorrente) return set
    for (const e of taskCorrente.evidence) {
      if (e.segment_id != null) {
        set.add(e.segment_id)
        continue
      }
      const riga =
        righeOrdinate.find((r) => e.t_ms >= r.t_start_ms && e.t_ms < r.t_end_ms) ??
        [...righeOrdinate].reverse().find((r) => r.t_start_ms <= e.t_ms)
      if (riga) set.add(riga.id)
    }
    return set
  }, [taskCorrente, righeOrdinate])

  // La trascrizione non si ricarica cambiando task: resta montata, cambiano
  // solo le righe segnate e la vista scorre sulla prima citata. Smontare e
  // rimontare la lista la farebbe saltare, vanificando la prova sotto gli occhi.
  useEffect(() => {
    if (!taskCorrente) return
    const primaId = righeOrdinate.find((r) => citate.has(r.id))?.id
    if (primaId == null) return
    corpoRef.current?.querySelector<HTMLElement>(`[data-id="${primaId}"]`)?.scrollIntoView({ block: 'center' })
    // Deliberatamente solo sul cambio di task: citate/righeOrdinate cambiano
    // riferimento più spesso di quanto la vista debba saltare da sola.
  }, [taskCorrente?.id])

  /** Il minuto è sempre un salto: scroll alla riga più uno sfarfallio, una
   * volta sola — la classe va tolta a fine animazione, altrimenti un secondo
   * clic sulla stessa riga non lampeggia. */
  const andaA = useCallback(
    (t_ms: number, segmentId: number | null) => {
      let id = segmentId
      if (id == null) {
        const riga =
          righeOrdinate.find((r) => t_ms >= r.t_start_ms && t_ms < r.t_end_ms) ??
          [...righeOrdinate].reverse().find((r) => r.t_start_ms <= t_ms) ??
          righeOrdinate[0]
        id = riga?.id ?? null
      }
      if (id == null) return
      const nodo = corpoRef.current?.querySelector<HTMLElement>(`[data-id="${id}"]`)
      if (!nodo) return
      nodo.scrollIntoView({ block: 'center', behavior: 'smooth' })
      nodo.classList.add('is-flashing')
      setTimeout(() => nodo.classList.remove('is-flashing'), 1100)
    },
    [righeOrdinate],
  )

  const impostaStato = useCallback(async (task: Task, stato: Task['stato']) => {
    const precedente = task.stato
    setAnalisi((a) => (a ? { ...a, tasks: a.tasks.map((t) => (t.id === task.id ? { ...t, stato } : t)) } : a))
    const r = await window.scriba.post(`/tasks/${task.id}`, { stato })
    if (!r.ok) {
      // Il ripristino tiene la riga coerente con quel che il core ha davvero
      // salvato, invece di lasciar credere un esito che non c'è stato.
      setAnalisi((a) =>
        a ? { ...a, tasks: a.tasks.map((t) => (t.id === task.id ? { ...t, stato: precedente } : t)) } : a,
      )
    }
  }, [])

  const salva = useCallback(async () => {
    if (!taskCorrente || !editando) return
    const campo = editando
    const testo = bozza.trim()
    // Il titolo non può restare vuoto: senza non ci sarebbe più una task da
    // mostrare in cima al pannello.
    if (campo === 'titolo' && !testo) return
    const valore = testo || null
    setEditando(null)
    const r = await window.scriba.post(`/tasks/${taskCorrente.id}`, { [campo]: valore })
    if (r.ok) {
      setAnalisi((a) =>
        a ? { ...a, tasks: a.tasks.map((t) => (t.id === taskCorrente.id ? applicaCampo(t, campo, valore) : t)) } : a,
      )
    }
  }, [taskCorrente, editando, bozza])

  // Naviga senza decidere la sorte della task: è '‹' / 'Salta ›' e le
  // frecce, non C/X.
  const naviga = useCallback(
    (delta: number) => {
      if (tasks.length === 0) return
      setIndice((i) => Math.min(tasks.length - 1, Math.max(0, i + delta)))
    },
    [tasks.length],
  )

  const confermaEAvanza = useCallback(() => {
    if (!taskCorrente) return
    impostaStato(taskCorrente, 'confirmed')
    naviga(1)
  }, [taskCorrente, impostaStato, naviga])

  const scartaEAvanza = useCallback(() => {
    if (!taskCorrente) return
    impostaStato(taskCorrente, 'rejected')
    naviga(1)
  }, [taskCorrente, impostaStato, naviga])

  const esci = useCallback(() => onEsci(indiceSicuro), [onEsci, indiceSicuro])

  // Confermare è un ritmo: gli stessi comandi esistono come pulsanti, ma da
  // tastiera valgono solo quando il fuoco non è dentro il campo di modifica.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const fuoco = document.activeElement
      if (fuoco instanceof HTMLElement && (/INPUT|TEXTAREA/.test(fuoco.tagName) || fuoco.isContentEditable)) return
      if (e.key === 'Escape') {
        e.preventDefault()
        esci()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        naviga(-1)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        naviga(1)
      } else if (e.key.toLowerCase() === 'c') {
        e.preventDefault()
        confermaEAvanza()
      } else if (e.key.toLowerCase() === 'x') {
        e.preventDefault()
        scartaEAvanza()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [esci, naviga, confermaEAvanza, scartaEAvanza])

  const nomeCall = sessione.titolo || `Call #${sessione.id}`
  const percentuale = tasks.length > 0 ? ((indiceSicuro + 1) / tasks.length) * 100 : 0

  return (
    <>
      <div className="review__bar">
        <span style={{ fontSize: 'var(--fs-base)', fontWeight: 600 }}>Rassegna task</span>
        <span className="review__count">{tasks.length > 0 ? `${indiceSicuro + 1} di ${tasks.length}` : '—'}</span>
        <div className="review__progress">
          <i style={{ width: `${percentuale}%` }} />
        </div>
        <span
          style={{ marginLeft: 'auto', fontFamily: 'var(--mono)', fontSize: 'var(--fs-mono)', color: 'var(--fg5)' }}
        >
          {nomeCall} · {dataBreve(sessione.started_at)}
        </span>
        <button className="btn" onClick={esci}>
          Esci dalla rassegna
        </button>
      </div>

      <div className="review">
        <main className="transcript">
          <div className="transcript__head">
            <span className="transcript__meta">Trascrizione, ferma sulle righe citate</span>
            <span className="legend">
              <i className="me" />
              Io
              <i className="other" />
              Altri
            </span>
          </div>
          <div className="transcript__body" ref={corpoRef}>
            {righeOrdinate.map((s) => (
              <div
                key={s.id}
                data-id={s.id}
                className={`line ${s.source === 'mic' ? 'line--me' : 'line--other'}${citate.has(s.id) ? ' is-cited' : ''}`}
              >
                {/* Uno span, non un pulsante: .line__t nel handoff non ha una
                    veste da bottone (niente bordo/sfondo), solo testo mono
                    cliccabile — un <button> qui mostrerebbe il cromo nativo. */}
                <span
                  className="line__t"
                  role="button"
                  tabIndex={0}
                  onClick={() => andaA(s.t_start_ms, s.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      andaA(s.t_start_ms, s.id)
                    }
                  }}
                >
                  {tempo(s.t_start_ms)}
                </span>
                <span className="line__who">{CHI[s.source] ?? s.source}</span>
                <span className={`line__text${s.is_final ? '' : ' is-provisional'}`}>{s.testo}</span>
              </div>
            ))}
          </div>
        </main>

        <aside className="review__side">
          {!analisi ? (
            <div className="state">
              <p className="state__title">Carico…</p>
              <p className="state__body">Sto leggendo le task di questa call.</p>
            </div>
          ) : !taskCorrente ? (
            <div className="state">
              <p className="state__title">Nessuna task da rivedere</p>
              <p className="state__body">Questa call non ha task in sospeso.</p>
            </div>
          ) : (
            <>
              <div className="review__head">
                <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                  {taskCorrente.needs_review && taskCorrente.stato === 'proposed' ? (
                    <span className="task__flag">DA CONFERMARE</span>
                  ) : null}
                  {taskCorrente.confidence != null && (
                    <span
                      style={{
                        marginLeft: 'auto',
                        fontFamily: 'var(--mono)',
                        fontSize: 'var(--fs-mono)',
                        color: 'var(--fg5)',
                      }}
                    >
                      conf. {taskCorrente.confidence.toFixed(2).replace('.', ',')}
                    </span>
                  )}
                </div>
                <h2 className="review__title">{taskCorrente.titolo}</h2>
              </div>

              <div className="review__fields">
                {CAMPI.map(({ chiave, etichetta, prova }) => {
                  const { testo, mancante } = valoreCampo(taskCorrente, chiave)
                  const prove = taskCorrente.evidence.filter((e) => e.supports === prova)
                  const inModifica = editando === chiave

                  return (
                    <div className="field" key={chiave}>
                      <div className="field__top">
                        <span className="field__label">{etichetta}</span>
                        {inModifica ? (
                          <>
                            <input
                              className="textfield"
                              autoFocus
                              value={bozza}
                              onChange={(e) => setBozza(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault()
                                  salva()
                                } else if (e.key === 'Escape') {
                                  e.preventDefault()
                                  setEditando(null)
                                }
                              }}
                            />
                            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                              <button className="btn btn--sm btn--confirm" onClick={salva}>
                                Salva
                              </button>
                              <button className="btn btn--sm" onClick={() => setEditando(null)}>
                                Annulla
                              </button>
                            </div>
                          </>
                        ) : (
                          <>
                            <span className={`field__value${mancante ? ' is-missing' : ''}`}>{testo}</span>
                            <button
                              className="btn btn--sm"
                              onClick={() => {
                                setBozza(valoreGrezzo(taskCorrente, chiave))
                                setEditando(chiave)
                              }}
                            >
                              Modifica
                            </button>
                          </>
                        )}
                      </div>
                      <div className="field__proof">
                        {prove.length > 0 ? (
                          prove.map((p, i) => (
                            <div className="field__quote" key={`${p.t_ms}-${i}`}>
                              <button className="ev__t" onClick={() => andaA(p.t_ms, p.segment_id)}>
                                {tempo(p.t_ms)}
                              </button>
                              <span>{p.quote ?? 'Dedotta dal contesto, non da una frase precisa.'}</span>
                            </div>
                          ))
                        ) : (
                          // Non si inventa una citazione plausibile: è l'unica
                          // difesa contro un modello che sbaglia con sicurezza.
                          <div className="field__quote is-empty">
                            <span>Dedotta dal tono della discussione, non da una frase.</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="review__actions">
                <div style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
                  <button className="btn btn--confirm" style={{ fontWeight: 600 }} onClick={confermaEAvanza}>
                    Conferma
                  </button>
                  <button className="btn" onClick={scartaEAvanza}>
                    Scarta
                  </button>
                  <button
                    className="btn"
                    style={{ marginLeft: 'auto' }}
                    disabled={indiceSicuro === 0}
                    onClick={() => naviga(-1)}
                  >
                    ‹
                  </button>
                  <button className="btn" disabled={indiceSicuro >= tasks.length - 1} onClick={() => naviga(1)}>
                    Salta ›
                  </button>
                </div>
                <span className="review__keys">
                  C conferma e avanza · X scarta e avanza · ← → naviga · Esc torna alla lista
                </span>
              </div>
            </>
          )}
        </aside>
      </div>
    </>
  )
}
