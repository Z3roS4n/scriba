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

import { giornoBreve, tempo, type Cliente, type Sessione, type StatoSessione } from './tipi'
import { Select } from './Select'
import { useLocale, useT, type Chiave } from './lingua'
// gia importato

/** Le voci del filtro stato. 'analyzing' non c'è: non è mai salvato nel
 *  database — vive solo nello stato del processo — quindi non si può filtrare. */
/** Il valore è quello che il core riceve, la chiave è quello che si legge:
 *  sono due cose diverse e da qui in poi non si toccano più. */
const STATI: Array<{ valore: StatoSessione | ''; chiave: Chiave }> = [
  { valore: '', chiave: 'arch.stato.tutti' },
  { valore: 'analyzed', chiave: 'arch.stato.analyzed' },
  { valore: 'recorded', chiave: 'arch.stato.recorded' },
  { valore: 'failed', chiave: 'arch.stato.failed' },
  { valore: 'recording', chiave: 'arch.stato.recording' },
]

const PERIODI: Array<{ giorni: number | null; chiave: Chiave }> = [
  { giorni: null, chiave: 'arch.periodo.sempre' },
  { giorni: 30, chiave: 'arch.periodo.30' },
  { giorni: 90, chiave: 'arch.periodo.90' },
  { giorni: 365, chiave: 'arch.periodo.365' },
]

const SENZA_CLIENTE = '__senza__'

/** Lo stato di una call, per chi lo legge. `etichettaStato` faceva la stessa
 *  cosa con uno `switch` di stringhe italiane: qui la traduzione arriva dal
 *  catalogo e lo stato resta l'identificatore che il core manda. */
const CHIAVE_STATO: Record<StatoSessione, Chiave> = {
  analyzed: 'arch.stato.analyzed',
  recorded: 'arch.stato.recorded',
  failed: 'arch.stato.failed',
  recording: 'arch.stato.recording',
  analyzing: 'call.in_analisi',
}

/** «12.400 token» invece di «12400 token»: si legge a colpo d'occhio. E il
 *  separatore delle migliaia lo decide la lingua — in inglese è la virgola. */
function conPunti(n: number, locale: string): string {
  return n.toLocaleString(locale)
}

/**
 * Esporta le call filtrate in un documento per un modello.
 *
 * Il peso si mostra **prima**: il contesto di un modello è finito, e scoprire
 * che il documento non ci sta quando è già stato incollato da qualche parte è
 * tardi. Per lo stesso motivo la trascrizione integrale è una spunta e non il
 * comportamento predefinito — su una call di due ore vale da sola più di tutto
 * il resto messo insieme.
 */
function PannelloIa({ call }: { call: Sessione[] }) {
  const t = useT()
  const locale = useLocale()
  const [conTrascrizione, setConTrascrizione] = useState(false)
  const [peso, setPeso] = useState<{ token_stimati: number; call: number } | null>(null)
  const [esito, setEsito] = useState<string | null>(null)
  const [percorso, setPercorso] = useState<string | null>(null)
  const [occupato, setOccupato] = useState(false)

  const ids = useMemo(() => call.map((c) => c.id), [call])

  useEffect(() => {
    setEsito(null)
    setPercorso(null)
    if (ids.length === 0) return
    let vivo = true
    window.scriba
      .post<{ token_stimati: number; call: number }>('/export/contesto/anteprima', {
        session_ids: ids,
        con_trascrizione: conTrascrizione,
      })
      .then((r) => {
        if (vivo && r.ok) setPeso(r.body)
      })
    return () => {
      vivo = false
    }
  }, [ids, conTrascrizione])

  const esporta = async () => {
    setOccupato(true)
    setEsito(null)
    const r = await window.scriba.post<{ percorso: string; token_stimati: number }>(
      '/export/contesto',
      { session_ids: ids, con_trascrizione: conTrascrizione },
    )
    setOccupato(false)
    if (!r.ok) {
      setEsito('Export non riuscito.')
      return
    }
    setPercorso(r.body.percorso)
    setEsito(`Scritto: ${conPunti(r.body.token_stimati, locale)} token stimati.`)
  }

  return (
    <div className="ia">
      <div className="ia__testo">
        <b>
          {call.length} {call.length === 1 ? 'call' : 'call'} in un documento solo
        </b>
        <span>
          {t('arc2.ia_nota')}
        </span>
      </div>

      <button
        className={`checkbox ${conTrascrizione ? 'is-on' : ''}`}
        onClick={() => setConTrascrizione((v) => !v)}
        aria-label="Includi la trascrizione integrale"
      >
        {conTrascrizione ? '✓' : ''}
      </button>
      <span className="ia__voce">{t('arc2.integrale')}</span>

      {peso && <span className="ia__peso">~{conPunti(peso.token_stimati, locale)} token</span>}

      <button className="btn btn--rec" disabled={occupato || ids.length === 0} onClick={esporta}>
        {occupato ? 'Scrivo…' : 'Esporta'}
      </button>

      {esito && <span className="ia__esito">{esito}</span>}
      {percorso && (
        <button className="btn btn--sm" onClick={() => window.scriba.mostraFile(percorso)}>
          {t('arc2.mostra')}
        </button>
      )}
    </div>
  )
}

export function Archivio(props: {
  clienti: Cliente[]
  onApri: (id: number) => void
  onEsci: () => void
  /** Ricarica l'elenco clienti: i conteggi cambiano appena si assegna una call. */
  onClientiCambiati: () => void
}) {
  const t = useT()
  const { clienti, onApri, onEsci, onClientiCambiati } = props

  const [testo, setTesto] = useState('')
  const locale = useLocale()
  const [cliente, setCliente] = useState<string>('')
  const [stato, setStato] = useState<StatoSessione | ''>('')
  const [giorni, setGiorni] = useState<number | null>(null)
  const [raggruppa, setRaggruppa] = useState(false)
  const [call, setCall] = useState<Sessione[]>([])
  const [caricando, setCaricando] = useState(true)
  const [perIa, setPerIa] = useState(false)

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

  /** Il frammento con la parola trovata dentro un <mark>.
   *
   *  Il core marca con \u0002 e \u0003 invece che con dei tag, cosi' qui non
   *  si rende HTML che arriva da fuori: si spezza la stringa e si compone. */
  function conEvidenza(frammento: string): React.ReactNode[] {
    return frammento.split('\u0002').flatMap((pezzo, i) => {
      if (i === 0) return [pezzo]
      const [dentro, ...fuori] = pezzo.split('\u0003')
      return [<mark key={i}>{dentro}</mark>, fuori.join('\u0003')]
    })
  }

  const oreTotali = call.reduce((n, c) => n + (c.durata_ms ?? 0), 0) / 3_600_000

  return (
    <div className="plane">
      <div className="plane__head">
        <span className="thread" />
        <span className="plane__title">{t('arch.titolo')}</span>
        <span className="plane__sub num">
          {t('arch.n_call', { n: call.length })}
          {oreTotali >= 0.1 &&
            ` · ${t('arch.ore', { n: oreTotali.toFixed(1).replace('.', ',') })}`}
        </span>
        <span className="plane__spacer" />
        <button className="esc" onClick={onEsci}>
          <span className="key">{t('arc2.esc')}</span>
          {t('arch.esci')}
        </button>
      </div>

      <div className="arch__tools">
        <div className="search">
          <input
            className="textfield"
            type="search"
            placeholder={t('arch.cerca')}
            value={testo}
            onChange={(e) => setTesto(e.target.value)}
          />
        </div>
        <Select
          opzioni={[
            { id: '', etichetta: t('arch.clienti.tutti') },
            { id: SENZA_CLIENTE, etichetta: t('call.senza_cliente') },
            ...clienti.map((c) => ({ id: String(c.id), etichetta: c.nome })),
          ]}
          selezionato={cliente}
          onScegli={setCliente}
        />
        <Select
          opzioni={STATI.map((s) => ({ id: s.valore, etichetta: t(s.chiave) }))}
          selezionato={stato}
          onScegli={(v) => setStato(v as StatoSessione | '')}
        />
        <Select
          opzioni={PERIODI.map((p) => ({
            id: p.giorni === null ? '' : String(p.giorni),
            etichetta: t(p.chiave),
          }))}
          selezionato={giorni === null ? '' : String(giorni)}
          onScegli={(v) => setGiorni(v === '' ? null : Number(v))}
        />
        <button className={`filter${raggruppa ? ' is-on' : ''}`} onClick={() => setRaggruppa((v) => !v)}>
          <span className="sq" />
          {t('arch.raggruppa')}
        </button>
        <span className="plane__spacer" />
        {/* L'archivio e' il posto in cui una selezione di call esiste gia': i
            filtri l'hanno appena fatta. Rifarla altrove sarebbe rifare i
            filtri. */}
        <button
          className={`btn btn--sm${perIa ? ' is-on' : ''}`}
          disabled={call.length === 0}
          onClick={() => setPerIa((v) => !v)}
        >
          {t('arch.per_ia')}
        </button>
      </div>

      {perIa && <PannelloIa call={call} />}

      <div className="arch__body">
        {caricando && call.length === 0 ? (
          <p className="state__body">{t('arch.cerco')}</p>
        ) : call.length === 0 ? (
          <p className="state__body">
            {filtrato
              ? t('arch.nessun_filtro')
              : t('arch.nessuna')}
          </p>
        ) : (
          gruppi.map((g) => (
            <section key={g.nome ?? '__nessuno__'}>
              {raggruppa && (
                <div className="arch__group">
                  <span className="label">{g.nome ?? t('call.senza_cliente')}</span>
                  <span className="arch__n num">
                    {t('arch.n_call', { n: g.call.length })}
                    {testo.trim() !== '' &&
                      ` · ${t('arch.con_parola', {
                        n: g.call.filter((c) => c.frammento).length,
                        q: testo.trim(),
                      })}`}
                  </span>
                </div>
              )}
              {g.call.map((c) => (
                <div className="arow" key={c.id}>
                  <button className="arow__apri" onClick={() => onApri(c.id)}>
                    <span className="arow__t">{c.titolo || t('call.senza_titolo', { n: c.id })}</span>
                    {/* La frase trovata, non solo il titolo: e' la meta' del
                        motivo per cui l'archivio esiste (regola 48). */}
                    {c.frammento && <span className="arow__hit">{conEvidenza(c.frammento)}</span>}
                  </button>
                  {/* Il cliente si assegna da qui, riga per riga: e' il posto in
                      cui uno ha davanti le call non attribuite tutte insieme, e
                      farlo call per call dalla scheda vuol dire non farlo mai
                      (regola 49). */}
                  <span className="arow__c">
                    <Select
                      opzioni={[
                        { id: '', etichetta: t('call.senza_cliente') },
                        ...clienti.map((cl) => ({ id: String(cl.id), etichetta: cl.nome })),
                      ]}
                      selezionato={c.client_id != null ? String(c.client_id) : ''}
                      onScegli={(v) => assegna(c.id, v)}
                      larghezza={200}
                    />
                  </span>
                  <span className="arow__m num">{giornoBreve(c.started_at, locale, t('data.oggi'))}</span>
                  <span className="arow__m num">{c.durata_ms != null ? tempo(c.durata_ms) : '—'}</span>
                  <span className="arow__s">
                    {c.n_task > 0
                      ? `${t('call.n_task', { n: c.n_task })}${
                          c.n_da_confermare > 0
                            ? ` · ${t('call.n_da_confermare', { n: c.n_da_confermare })}`
                            : ''
                        }`
                      : t(CHIAVE_STATO[c.stato])}
                  </span>
                </div>
              ))}
            </section>
          ))
        )}
      </div>
    </div>
  )
}
