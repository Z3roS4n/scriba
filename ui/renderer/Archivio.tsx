/**
 * Archivio: tutte le call, cercabili e raggruppabili per cliente.
 *
 * La colonna a sinistra della finestra principale risponde a "cos'ho fatto
 * oggi". Questa pagina risponde all'altra domanda, quella che dopo qualche mese
 * si fa più spesso: «cosa ci siamo detti con questo cliente». Da qui la ricerca
 * dentro il parlato — l'indice full-text esisteva già e nessuna schermata lo
 * interrogava — e il raggruppamento.
 *
 * A tutta finestra come la Rassegna, e per lo stesso motivo: mentre si cerca
 * nello storico non si sta guardando una call in particolare, quindi tenere in
 * piedi il resto dell'interfaccia sarebbe solo rumore.
 *
 * Il cliente si assegna da qui, riga per riga. È il posto in cui uno ha davanti
 * le call non attribuite tutte insieme, ed è quindi il posto in cui le
 * attribuisce: farlo call per call dalla scheda significherebbe non farlo mai.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { dataBreve, tempo, type Cliente, type Sessione, type StatoSessione } from './tipi'

/** Le voci del filtro stato. 'analyzing' non c'è: non è mai salvato nel
 *  database — vive solo nello stato del processo — quindi non si può filtrare. */
const STATI: Array<{ valore: StatoSessione | ''; etichetta: string }> = [
  { valore: '', etichetta: 'Qualsiasi stato' },
  { valore: 'analyzed', etichetta: 'Analizzate' },
  { valore: 'recorded', etichetta: 'Registrate' },
  { valore: 'failed', etichetta: 'Analisi non riuscita' },
  { valore: 'recording', etichetta: 'In corso' },
]

const PERIODI: Array<{ giorni: number | null; etichetta: string }> = [
  { giorni: null, etichetta: 'Sempre' },
  { giorni: 30, etichetta: 'Ultimi 30 giorni' },
  { giorni: 90, etichetta: 'Ultimi 3 mesi' },
  { giorni: 365, etichetta: "Ultimo anno" },
]

const SENZA_CLIENTE = '__senza__'

function etichettaStato(stato: StatoSessione): string {
  switch (stato) {
    case 'recording':
      return 'in corso'
    case 'analyzed':
      return 'analizzata'
    case 'failed':
      return 'analisi non riuscita'
    case 'analyzing':
      return 'in analisi'
    default:
      return 'registrata'
  }
}

export function Archivio(props: {
  clienti: Cliente[]
  onApri: (id: number) => void
  onEsci: () => void
  /** Ricarica l'elenco clienti: i conteggi cambiano appena si assegna una call. */
  onClientiCambiati: () => void
}) {
  const { clienti, onApri, onEsci, onClientiCambiati } = props

  const [testo, setTesto] = useState('')
  const [cliente, setCliente] = useState<string>('')
  const [stato, setStato] = useState<StatoSessione | ''>('')
  const [giorni, setGiorni] = useState<number | null>(null)
  const [raggruppa, setRaggruppa] = useState(false)
  const [call, setCall] = useState<Sessione[]>([])
  const [caricando, setCaricando] = useState(true)

  // La ricerca parte quando si smette di scrivere, non a ogni tasto: una query
  // full-text per lettera su tutto lo storico e' lavoro buttato, e i risultati
  // che ballano sotto le dita rendono difficile leggerli.
  const [testoCercato, setTestoCercato] = useState('')
  const attesa = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    clearTimeout(attesa.current)
    attesa.current = setTimeout(() => setTestoCercato(testo), 250)
    return () => clearTimeout(attesa.current)
  }, [testo])

  const carica = useCallback(async () => {
    const q = new URLSearchParams()
    if (testoCercato.trim()) q.set('testo', testoCercato.trim())
    if (cliente === SENZA_CLIENTE) q.set('senza_cliente', 'true')
    else if (cliente) q.set('client_id', cliente)
    if (stato) q.set('stato', stato)
    if (giorni !== null) q.set('da_ms', String(Date.now() - giorni * 86_400_000))

    setCaricando(true)
    const r = await window.scriba.get<Sessione[]>(`/archivio?${q.toString()}`)
    if (r.ok) setCall(r.body)
    setCaricando(false)
  }, [testoCercato, cliente, stato, giorni])

  useEffect(() => {
    carica()
  }, [carica])

  const assegna = useCallback(
    async (sessionId: number, valore: string) => {
      const client_id = valore ? Number(valore) : null
      const r = await window.scriba.patch(`/sessions/${sessionId}/cliente`, { client_id })
      if (!r.ok) return
      // Aggiornamento locale invece di ricaricare: se si sta assegnando una
      // dopo l'altra, ricaricare farebbe sparire la riga da sotto il cursore
      // ogni volta che il filtro «senza cliente» e' attivo.
      setCall((prec) =>
        prec.map((c) =>
          c.id === sessionId
            ? { ...c, client_id, cliente: clienti.find((x) => x.id === client_id)?.nome ?? null }
            : c,
        ),
      )
      onClientiCambiati()
    },
    [clienti, onClientiCambiati],
  )

  const gruppi = useMemo(() => {
    if (!raggruppa) return [{ nome: null as string | null, call }]
    const per = new Map<string, Sessione[]>()
    for (const c of call) {
      const chiave = c.cliente ?? ''
      const elenco = per.get(chiave)
      if (elenco) elenco.push(c)
      else per.set(chiave, [c])
    }
    return [...per.entries()]
      // Le call senza cliente in fondo: sono quelle da sistemare, non quelle
      // da leggere per prime.
      .sort(([a], [b]) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)))
      .map(([nome, elenco]) => ({ nome: nome || null, call: elenco }))
  }, [raggruppa, call])

  const filtrato = testoCercato.trim() !== '' || cliente !== '' || stato !== '' || giorni !== null

  return (
    <>
      <div className="review__bar">
        <span className="label">ARCHIVIO</span>
        <input
          className="arch__search"
          type="search"
          placeholder="Cerca nei titoli e in quello che è stato detto…"
          value={testo}
          onChange={(e) => setTesto(e.target.value)}
        />
        <select className="arch__filter" value={cliente} onChange={(e) => setCliente(e.target.value)}>
          <option value="">Tutti i clienti</option>
          <option value={SENZA_CLIENTE}>Senza cliente</option>
          {clienti.map((c) => (
            <option key={c.id} value={String(c.id)}>
              {c.nome}
            </option>
          ))}
        </select>
        <select
          className="arch__filter"
          value={stato}
          onChange={(e) => setStato(e.target.value as StatoSessione | '')}
        >
          {STATI.map((s) => (
            <option key={s.valore} value={s.valore}>
              {s.etichetta}
            </option>
          ))}
        </select>
        <select
          className="arch__filter"
          value={giorni === null ? '' : String(giorni)}
          onChange={(e) => setGiorni(e.target.value === '' ? null : Number(e.target.value))}
        >
          {PERIODI.map((p) => (
            <option key={p.etichetta} value={p.giorni === null ? '' : String(p.giorni)}>
              {p.etichetta}
            </option>
          ))}
        </select>
        <button
          className={`btn btn--sm ${raggruppa ? 'is-on' : ''}`}
          onClick={() => setRaggruppa((v) => !v)}
        >
          Per cliente
        </button>
        <div className="topbar__spacer" />
        <button className="btn" onClick={onEsci}>
          Chiudi
        </button>
      </div>

      <div className="arch">
        {caricando && call.length === 0 ? (
          <p className="arch__empty">Cerco…</p>
        ) : call.length === 0 ? (
          <p className="arch__empty">
            {filtrato
              ? 'Nessuna call corrisponde a questi filtri.'
              : 'Nessuna call registrata: qui compariranno appena ne registri una.'}
          </p>
        ) : (
          gruppi.map((g) => (
            <section key={g.nome ?? '__nessuno__'}>
              {raggruppa && (
                <h2 className="arch__group">
                  {g.nome ?? 'Senza cliente'}
                  <span className="count">
                    {g.call.length} {g.call.length === 1 ? 'call' : 'call'}
                  </span>
                </h2>
              )}
              {g.call.map((c) => (
                <div key={c.id} className="arch__row">
                  <button className="arch__open" onClick={() => onApri(c.id)}>
                    <span className="arch__title">{c.titolo || `Call #${c.id}`}</span>
                    <span className="arch__meta">
                      {dataBreve(c.started_at)}
                      <span>·</span>
                      {c.durata_ms != null ? tempo(c.durata_ms) : '—'}
                      <span>·</span>
                      {etichettaStato(c.stato)}
                      {c.n_task > 0 && (
                        <>
                          <span>·</span>
                          {c.n_task} {c.n_task === 1 ? 'task' : 'task'}
                          {c.n_da_confermare > 0 && ` (${c.n_da_confermare} da confermare)`}
                        </>
                      )}
                    </span>
                  </button>
                  <select
                    className="arch__cliente"
                    value={c.client_id != null ? String(c.client_id) : ''}
                    onChange={(e) => assegna(c.id, e.target.value)}
                    title="Cliente di questa call"
                  >
                    <option value="">— nessun cliente —</option>
                    {clienti.map((cl) => (
                      <option key={cl.id} value={String(cl.id)}>
                        {cl.nome}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </section>
          ))
        )}
      </div>
    </>
  )
}
