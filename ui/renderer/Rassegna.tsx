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
import { RiquadroInline } from './Dialoghi'
import { etichettaValore, useLocale, useT, type Chiave, type Traduci } from './lingua'
import type { Analisi, CampoProva, Segmento, Sessione, Task } from './tipi'
import { dataBreve, tempo } from './tipi'

/** I soli valori che lo schema accetta per la priorità
 *  (`CHECK (priorita IN (...))`, schema.sql). Si sceglie fra questi invece di
 *  scriverla a mano: erano quattro parole chiuse offerte come campo libero, e
 *  qualunque altra cosa faceva fallire la scrittura in silenzio (#71). */
const PRIORITA = ['bassa', 'media', 'alta', 'critica'] as const

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
const CAMPI: Array<{ chiave: ChiaveCampo; etichetta: Chiave; prova: CampoProva }> = [
  { chiave: 'titolo', etichetta: 'ras.campo.titolo', prova: 'titolo' },
  { chiave: 'assignee_text', etichetta: 'ras.campo.assignee', prova: 'assignee' },
  { chiave: 'due_date', etichetta: 'ras.campo.scadenza', prova: 'due_date' },
  { chiave: 'priorita', etichetta: 'ras.campo.priorita', prova: 'priorita' },
]

/** Il testo mostrato quando non si sta modificando, e se è un vuoto detto
 * apertamente («nessun responsabile») invece che uno spazio bianco. */
function valoreCampo(
  t: Task,
  chiave: ChiaveCampo,
  tr: Traduci,
): { testo: string; mancante: boolean } {
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
      return t.priorita
        ? { testo: etichettaValore(tr, 'priorita', t.priorita), mancante: false }
        : { testo: tr('priorita.nessuna'), mancante: true }
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

  const tr = useT()
  const locale = useLocale()
  const [analisi, setAnalisi] = useState<Analisi | null>(null)
  const [indice, setIndice] = useState(indiceIniziale)
  const [editando, setEditando] = useState<ChiaveCampo | null>(null)
  /** Perché l'ultimo salvataggio non è andato. Livello 4: si mostra nel punto
   *  in cui si è premuto, non su una barra lontana. */
  const [erroreSalva, setErroreSalva] = useState<string | null>(null)
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

  /** Esce dalla modifica buttando via anche l'errore: tenerlo in piedi dopo
   *  un annullamento farebbe credere che ci sia ancora qualcosa in sospeso. */
  const annullaModifica = useCallback(() => {
    setErroreSalva(null)
    setEditando(null)
  }, [])

  const salva = useCallback(
    async (valoreImposto?: string | null) => {
      if (!taskCorrente || !editando) return
      const campo = editando
      const testo = bozza.trim()
      // Il titolo non può restare vuoto: senza non ci sarebbe più una task da
      // mostrare in cima al pannello.
      if (campo === 'titolo' && valoreImposto === undefined && !testo) return
      const valore = valoreImposto !== undefined ? valoreImposto : testo || null

      const r = await window.scriba.post(`/tasks/${taskCorrente.id}`, { [campo]: valore })
      if (!r.ok) {
        // Prima si usciva dalla modifica **prima** di sapere com'era andata, e
        // un salvataggio rifiutato non lasciava traccia: il campo tornava al
        // valore vecchio e sembrava che non fosse successo niente (#71). Ora
        // si resta dentro, col testo scritto ancora lì, e si dice cosa non ha
        // funzionato.
        const dettaglio =
          typeof (r.body as { detail?: unknown } | null)?.detail === 'string'
            ? (r.body as { detail: string }).detail
            : `Il core ha risposto ${r.status}.`
        setErroreSalva(dettaglio)
        return
      }
      setErroreSalva(null)
      setEditando(null)
      setAnalisi((a) =>
        a ? { ...a, tasks: a.tasks.map((t) => (t.id === taskCorrente.id ? applicaCampo(t, campo, valore) : t)) } : a,
      )
    },
    [taskCorrente, editando, bozza],
  )

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
  const daConfermare = tasks.filter((t) => t.needs_review && t.stato === 'proposed').length

  return (
    <div className="plane">
      <div className="plane__head">
        <span className="thread" />
        <span className="plane__title">{tr('ras.titolo')}</span>
        <span className="plane__sub">
          {nomeCall} · {dataBreve(sessione.started_at, locale, tr('data.oggi'))}
        </span>
        <span className="plane__spacer" />
        <span className="rev__count num">
          {tasks.length > 0 ? tr('ras.di', { i: indiceSicuro + 1, n: tasks.length }) : '—'}
          {daConfermare > 0 && ` · ${tr('call.n_da_confermare', { n: daConfermare })}`}
        </span>
        {/* Si esce con Esc, e il tasto è scritto: una scorciatoia esiste solo
            se qualcuno sa che c'è. Il clic fa la stessa cosa. */}
        <button className="esc" onClick={esci}>
          <span className="key">Esc</span>
          {tr('ras.esci')}
        </button>
      </div>

      {/* Traccia e riempimento, senza percentuale scritta: il numero esatto è
          già in testata (comportamento.md, 29). */}
      <div className="progress">
        <i style={{ width: `${percentuale}%` }} />
      </div>

      <div className="plane__body">
        <div className="rev__left">
          <div className="transcript__head">
            <span className="label label--quiet">{tr('ras.trascrizione')}</span>
            <span className="transcript__meta num">{tr('ras.ferma')}</span>
          </div>
          {/* Cambiando task queste righe non si smontano: cambia solo
              `.is-cited` e la posizione. Rimontarle farebbe saltare la lista,
              vanificando la prova sotto gli occhi (regola 28). */}
          <div className="transcript__body" ref={corpoRef}>
            {righeOrdinate.map((s) => (
              <div
                key={s.id}
                data-id={s.id}
                className={`line ${
                  s.eco ? 'line--echo' : s.source === 'mic' ? 'line--me' : 'line--other'
                }${citate.has(s.id) ? ' is-cited' : ''}`}
              >
                <button className="line__t num" onClick={() => andaA(s.t_start_ms, s.id)}>
                  {tempo(s.t_start_ms)}
                </button>
                <span className="line__who">{s.eco ? CHI.loopback : (CHI[s.source] ?? s.source)}</span>
                <p className={`line__text${s.is_final ? '' : ' is-provisional'}`}>
                  {s.eco && <span className="echo__tag">ripresa</span>}
                  {s.testo}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="rev__right">
          {!analisi ? (
            <div className="state">
              <p className="state__title">{tr('ras.carico')}</p>
              <p className="state__body">{tr('ras.carico_nota')}</p>
            </div>
          ) : !taskCorrente ? (
            <div className="state">
              <p className="state__title">{tr('ras.nessuna')}</p>
              <p className="state__body">{tr('ras.nessuna_nota')}</p>
            </div>
          ) : (
            <>
              <div className="rev__body">
                <span className="label label--quiet">
                  {tr('ras.task_n_di', { i: indiceSicuro + 1, n: tasks.length })}
                </span>
                <h2 className="rev__title">{taskCorrente.titolo}</h2>

                <div className="rev__fields">
                  {CAMPI.map(({ chiave, etichetta, prova }) => {
                    const { testo, mancante } = valoreCampo(taskCorrente, chiave, tr)
                    const prove = taskCorrente.evidence.filter((e) => e.supports === prova)
                    const inModifica = editando === chiave

                    return (
                      <div className="rf" key={chiave}>
                        <div className="rf__k">
                          <span className="label label--quiet">{tr(etichetta)}</span>
                          {!inModifica && (
                            <button
                              className="btn btn--quiet btn--sm rf__edit"
                              onClick={() => {
                                setErroreSalva(null)
                                setBozza(valoreGrezzo(taskCorrente, chiave))
                                setEditando(chiave)
                              }}
                            >
                              {tr('ras.modifica')}
                            </button>
                          )}
                        </div>

                        {inModifica ? (
                          chiave === 'priorita' ? (
                            // Quattro valori chiusi, e sono gli unici che lo
                            // schema accetta: si scelgono, non si scrivono (#71).
                            <div className="rf__v rf__edit-row">
                              {PRIORITA.map((pr) => (
                                <button
                                  key={pr}
                                  className={`btn btn--sm${valoreGrezzo(taskCorrente, chiave) === pr ? ' is-on' : ''}`}
                                  onClick={() => salva(pr)}
                                >
                                  {etichettaValore(tr, 'priorita', pr)}
                                </button>
                              ))}
                              <button className="btn btn--sm" onClick={() => salva(null)}>
                                nessuna
                              </button>
                              <button className="btn btn--quiet btn--sm" onClick={annullaModifica}>
                                {tr('ras.annulla')}
                              </button>
                            </div>
                          ) : (
                            <div className="rf__v rf__edit-row">
                              <input
                                className="textfield textfield--sm"
                                autoFocus
                                value={bozza}
                                onChange={(e) => setBozza(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    e.preventDefault()
                                    salva()
                                  } else if (e.key === 'Escape') {
                                    e.preventDefault()
                                    annullaModifica()
                                  }
                                }}
                              />
                              <button className="btn btn--primary btn--sm" onClick={() => salva()}>
                                {tr('ras.salva')}
                              </button>
                              <button className="btn btn--quiet btn--sm" onClick={annullaModifica}>
                                {tr('ras.annulla')}
                              </button>
                            </div>
                          )
                        ) : (
                          <div className={`rf__v${mancante ? ' is-missing' : ''}`}>{testo}</div>
                        )}

                        {/* Nel punto in cui si è premuto, non su una barra
                            lontana: chi ha appena salvato sta guardando qui. */}
                        {inModifica && erroreSalva && (
                          <RiquadroInline
                            testo={`Non sono riuscito a salvare: ${erroreSalva}`}
                            azioni={[{ etichetta: 'Riprova', onClick: () => salva() }]}
                          />
                        )}

                        {prove.length > 0 ? (
                          prove.map((pr, i) => (
                            <div className="rf__ev" key={`${pr.t_ms}-${i}`}>
                              <button className="ev__t num" onClick={() => andaA(pr.t_ms, pr.segment_id)}>
                                {tempo(pr.t_ms)}
                              </button>
                              <p className={`rf__q${pr.quote ? '' : ' is-empty'}`}>
                                {pr.quote ?? 'Dedotta dal contesto, non da una frase precisa.'}
                              </p>
                            </div>
                          ))
                        ) : (
                          // Non si inventa una citazione plausibile, e non si
                          // lascia il campo muto — che si legge come
                          // «verificato» (regola 13).
                          <div className="rf__ev">
                            <span className="ev__t">—</span>
                            <p className="rf__q is-empty">{tr('ras.dedotta')}</p>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Conferma e Scarta avanzano alla successiva: la passata è un
                  ritmo, non una serie di decisioni isolate (regola 27). */}
              <div className="rev__foot">
                <button className="btn btn--primary btn--lg" onClick={confermaEAvanza}>
                  {tr('ras.conferma')}
                </button>
                <button className="btn btn--lg" onClick={scartaEAvanza}>
                  {tr('ras.scarta')}
                </button>
                <div className="rev__keys">
                  <span className="key">C</span>conferma
                  <span className="key">X</span>scarta
                  <span className="key">←</span>
                  <span className="key">→</span>scorri
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
