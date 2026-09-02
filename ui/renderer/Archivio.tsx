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

import {
  giornoBreve,
  tempo,
  type Cliente,
  type EventoCore,
  type Sessione,
  type StatoSessione,
} from './tipi'
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

/**
 * I tre modi di interrogare l'archivio.
 *
 * Sono tre domande diverse, non tre livelli di bravura della stessa. «Normale»
 * risponde a «dove ho detto questa parola» ed è la migliore quando la parola la
 * si ricorda. «Semantica» risponde a «dove ho parlato di questo», che è la
 * domanda che si fa dopo qualche mese, quando si ricorda l'argomento e non le
 * parole. «Contestuale» risponde a una domanda vera e per farlo legge.
 *
 * In fila per costo crescente: la prima è istantanea, la seconda dura un
 * decimo di secondo, la terza chiama un modello e — con un abbonamento ad API —
 * si paga. Per questo è anche l'unica che non parte da sola mentre si scrive.
 */
const MODALITA = ['normale', 'semantica', 'contestuale'] as const
type Modalita = (typeof MODALITA)[number]

const CHIAVE_MODO: Record<Modalita, Chiave> = {
  normale: 'ric.modo.normale',
  semantica: 'ric.modo.semantica',
  contestuale: 'ric.modo.contestuale',
}

const CHIAVE_CERCA: Record<Modalita, Chiave> = {
  normale: 'arch.cerca',
  semantica: 'ric.cerca_semantica',
  contestuale: 'ric.cerca_contestuale',
}

type StatoIndice = {
  modello_installato: boolean
  call_con_parlato: number
  call_indicizzate: number
  passaggi: number
  in_corso: boolean
  fatte: number
  totale: number
  errore: string | null
}

type CallCitata = Sessione & {
  perche: string
  passaggi: Array<{ testo: string; quando_ms: number }>
}

type Risposta = {
  risposta: string
  call: CallCitata[]
  /** Le call lette come un discorso solo, dalla più vecchia. Coppie e non due
   *  elenchi affiancati: due elenchi si disallineano, e una catena con i
   *  titoli sfalsati non si distingue da una giusta. */
  catene: Array<{ call: Array<{ id: number; titolo: string | null }> }>
  passaggi_letti: number
}

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

/** Il motivo scritto dal core, che è già nella lingua di chi legge.
 *
 *  Senza, resterebbe «la ricerca non è riuscita» — vero e inutile: le tre cose
 *  che possono andare storte qui (modello non installato, indice da costruire,
 *  motore di analisi spento) si risolvono in tre modi diversi, e sono le
 *  frasi del core a dire quale. */
function messaggio(corpo: unknown): string | null {
  const detail = (corpo as { detail?: unknown } | null)?.detail
  return typeof detail === 'string' ? detail : null
}

/**
 * Cosa la ricerca per significato può vedere, e cosa no.
 *
 * Una call non indicizzata è invisibile alle due modalità nuove, e invisibile
 * in silenzio: chi cerca vedrebbe «nessun risultato» e concluderebbe che
 * nell'archivio non c'è — la cosa peggiore che possa dire una ricerca. Questa
 * barra esiste per rendere quella differenza visibile prima, non dopo.
 */
function BarraIndice({ stato, onIndicizza }: { stato: StatoIndice; onIndicizza: () => void }) {
  const t = useT()
  const locale = useLocale()
  const mancanti = stato.call_con_parlato - stato.call_indicizzate

  if (!stato.modello_installato) {
    return (
      <div className="ia ric__indice">
        <div className="ia__t">
          <b>{t('ric.manca_modello')}</b>
          <span>{t('ric.manca_modello_dove')}</span>
        </div>
      </div>
    )
  }

  if (stato.in_corso) {
    return (
      <div className="ia ric__indice">
        <div className="ia__t">
          <b>{t('ric.indicizzo', { n: stato.fatte, tot: stato.totale })}</b>
          <span>{t('ric.indicizzo_nota')}</span>
        </div>
        <span className="ia__spacer" />
        <button className="btn btn--sm" onClick={() => window.scriba.post('/ricerca/indicizza/ferma', {})}>
          {t('ric.ferma')}
        </button>
      </div>
    )
  }

  if (mancanti <= 0) return null

  return (
    <div className="ia ric__indice">
      <div className="ia__t">
        <b>{t('ric.da_indicizzare', { n: conPunti(mancanti, locale) })}</b>
        <span>{t('ric.da_indicizzare_nota')}</span>
      </div>
      <span className="ia__spacer" />
      <button className="btn btn--rec" onClick={onIndicizza}>
        {t('ric.indicizza')}
      </button>
    </div>
  )
}

/**
 * La risposta del modello, con sopra da dove viene.
 *
 * Le catene si dichiarano prima della risposta, non dopo: se il modello ha
 * letto tre call come un discorso solo, chi legge deve saperlo mentre legge —
 * altrimenti attribuirà alla call citata anche quello che è stato detto nelle
 * altre due, che è esattamente il difetto che unire doveva risolvere.
 */
function PannelloRisposta({ risposta }: { risposta: Risposta }) {
  const t = useT()
  const locale = useLocale()

  return (
    <div className="ric__risposta">
      {risposta.catene.map((c) => (
        <p className="ric__catena" key={c.call.map((x) => x.id).join('-')}>
          {/* Il titolo può mancare — una call registrata al volo non ne ha uno
              — e concatenarli così com'erano lasciava una freccia sospesa nel
              vuoto: la catena sembrava avere un anello in meno di quelli che
              il modello ha davvero letto. */}
          {t('ric.lette_insieme', {
            call: c.call
              .map((x) => x.titolo || t('call.senza_titolo', { n: x.id }))
              .join(' → '),
          })}
        </p>
      ))}
      <p className="ric__testo">
        {risposta.risposta || t('ric.nessuna_risposta')}
      </p>
      <p className="ric__fonte num">
        {t('ric.passaggi_letti', { n: conPunti(risposta.passaggi_letti, locale) })}
      </p>
    </div>
  )
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
      setEsito(t('arc3.export_ko'))
      return
    }
    setPercorso(r.body.percorso)
    setEsito(t('arc3.scritto', { n: conPunti(r.body.token_stimati, locale) }))
  }

  return (
    <div className="ia">
      <div className="ia__t">
        <b>
          {t('arc3.in_un_documento', { n: call.length })}
        </b>
        <span>
          {t('arc2.ia_nota')}
        </span>
      </div>

      <button
        className={`checkbox ${conTrascrizione ? 'is-on' : ''}`}
        onClick={() => setConTrascrizione((v) => !v)}
        aria-label={t('arch.includi_integrale')}
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

  const [modalita, setModalita] = useState<Modalita>('normale')
  const [unisci, setUnisci] = useState(true)
  const [indice, setIndice] = useState<StatoIndice | null>(null)
  const [risposta, setRisposta] = useState<Risposta | null>(null)
  const [chiedendo, setChiedendo] = useState(false)
  const [guasto, setGuasto] = useState<string | null>(null)

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

  /** I filtri, nella forma che vogliono le tre rotte. */
  const filtri = useMemo(
    () => ({
      client_id: cliente && cliente !== SENZA_CLIENTE ? Number(cliente) : null,
      senza_cliente: cliente === SENZA_CLIENTE,
      da_ms: giorni !== null ? Date.now() - giorni * 86_400_000 : null,
      stato: stato || null,
    }),
    [cliente, stato, giorni],
  )

  const carica = useCallback(async () => {
    // La contestuale non parte da sola: costa una chiamata al modello, e su un
    // abbonamento ad API si paga. Si aspetta che qualcuno la chieda.
    if (modalita === 'contestuale') return

    setCaricando(true)
    setGuasto(null)
    if (modalita === 'normale') {
      const q = new URLSearchParams()
      if (testoCercato.trim()) q.set('testo', testoCercato.trim())
      if (filtri.senza_cliente) q.set('senza_cliente', 'true')
      else if (filtri.client_id !== null) q.set('client_id', String(filtri.client_id))
      if (filtri.stato) q.set('stato', filtri.stato)
      if (filtri.da_ms !== null) q.set('da_ms', String(filtri.da_ms))
      const r = await window.scriba.get<Sessione[]>(`/archivio?${q.toString()}`)
      if (r.ok) setCall(r.body)
      setCaricando(false)
      return
    }

    // Semantica. Senza niente da cercare non si cerca: l'elenco completo lo
    // dà già la ricerca normale, e mostrarlo qui direbbe che tutto somiglia
    // a niente.
    if (!testoCercato.trim()) {
      setCall([])
      setCaricando(false)
      return
    }
    const r = await window.scriba.post<{ call: Sessione[]; da_indicizzare: number }>(
      '/ricerca/semantica',
      { ...filtri, testo: testoCercato.trim() },
    )
    if (r.ok) setCall(r.body.call)
    else setGuasto(messaggio(r.body))
    setCaricando(false)
  }, [modalita, testoCercato, filtri])

  useEffect(() => {
    carica()
  }, [carica])

  /** La domanda vera e propria: parte solo quando la si chiede. */
  const chiedi = useCallback(async () => {
    if (!testo.trim() || chiedendo) return
    setChiedendo(true)
    setGuasto(null)
    setRisposta(null)
    const r = await window.scriba.post<Risposta>('/ricerca/contestuale', {
      ...filtri,
      domanda: testo.trim(),
      unisci_catene: unisci,
    })
    if (r.ok) {
      setRisposta(r.body)
      setCall(r.body.call)
    } else {
      setGuasto(messaggio(r.body))
      setCall([])
    }
    setChiedendo(false)
  }, [testo, chiedendo, filtri, unisci])

  // Cambiare modalità azzera quello che apparteneva alla precedente. Vale
  // anche per l'elenco, non solo per la risposta: passando alla contestuale,
  // che non parte da sola, restavano in pagina i risultati della semantica —
  // e si leggevano come la risposta a una domanda che nessuno aveva ancora
  // fatto. Chi ci arriva deve trovare la casella vuota e l'invito a scrivere.
  useEffect(() => {
    setRisposta(null)
    setGuasto(null)
    setCall([])
  }, [modalita])

  // Lo stato dell'indice serve a tutte e due le modalità nuove, e serve
  // *prima* di cercare: «nessun risultato» e «non l'ho ancora letto» sono due
  // cose diverse, e l'unico posto in cui si può distinguerle è qui.
  const leggiIndice = useCallback(async () => {
    const r = await window.scriba.get<StatoIndice>('/ricerca/stato')
    if (r.ok) setIndice(r.body)
  }, [])

  useEffect(() => {
    if (modalita !== 'normale') leggiIndice()
  }, [modalita, leggiIndice])

  useEffect(() => {
    return window.scriba.on('core:event', (ev: EventoCore) => {
      if (ev.type !== 'indice_semantico') return
      const e = ev as Extract<EventoCore, { type: 'indice_semantico' }>
      setIndice((prec) =>
        prec ? { ...prec, in_corso: e.stato === 'in_corso', fatte: e.fatte ?? 0, totale: e.totale ?? 0 } : prec,
      )
      // A fine giro il conto delle call indicizzate è cambiato: si rilegge
      // invece di provare a ricostruirlo dagli eventi.
      if (e.stato !== 'in_corso') leggiIndice()
    })
  }, [leggiIndice])

  const indicizza = useCallback(async () => {
    const r = await window.scriba.post('/ricerca/indicizza', {})
    if (!r.ok) setGuasto(messaggio(r.body))
    else setIndice((prec) => (prec ? { ...prec, in_corso: true } : prec))
  }, [])

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
        <div className="picker">
          {MODALITA.map((m) => (
            <button
              key={m}
              className={modalita === m ? 'is-on' : ''}
              onClick={() => setModalita(m)}
            >
              {t(CHIAVE_MODO[m])}
            </button>
          ))}
        </div>
        <div className="search">
          <input
            className="textfield"
            type="search"
            placeholder={t(CHIAVE_CERCA[modalita])}
            value={testo}
            onChange={(e) => setTesto(e.target.value)}
            onKeyDown={(e) => {
              if (modalita === 'contestuale' && e.key === 'Enter') chiedi()
            }}
          />
        </div>
        {modalita === 'contestuale' && (
          <>
            <button className="btn btn--sm" disabled={chiedendo || !testo.trim()} onClick={chiedi}>
              {chiedendo ? t('ric.chiedendo') : t('ric.chiedi')}
            </button>
            {/* L'interruttore sta qui e non nelle impostazioni: unire due call
                cambia la risposta, e chi legge deve poter vedere in un gesto
                se erano unite. */}
            <button
              className={`filter${unisci ? ' is-on' : ''}`}
              onClick={() => setUnisci((v) => !v)}
            >
              <span className="sq" />
              {t('ric.unisci')}
            </button>
          </>
        )}
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

      {modalita !== 'normale' && indice && <BarraIndice stato={indice} onIndicizza={indicizza} />}
      {guasto && <p className="ric__guasto">{guasto}</p>}
      {risposta && <PannelloRisposta risposta={risposta} />}

      <div className="arch__body">
        {(caricando || chiedendo) && call.length === 0 ? (
          <p className="state__body">{chiedendo ? t('ric.chiedendo') : t('arch.cerco')}</p>
        ) : call.length === 0 ? (
          <p className="state__body">
            {modalita === 'contestuale' && !risposta
              ? t('ric.invito')
              : modalita === 'semantica' && !testoCercato.trim()
                ? t('ric.invito_semantica')
                : filtrato
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
                    {/* Perché questa call risponde: la scrive il modello, e
                        senza sarebbe un elenco di call da riaprire una per una
                        — cioè quello che c'era prima. */}
                    {(c as CallCitata).perche && (
                      <span className="arow__perche">{(c as CallCitata).perche}</span>
                    )}
                    {/* La frase trovata, non solo il titolo: e' la meta' del
                        motivo per cui l'archivio esiste (regola 48). Nella
                        contestuale sono i passaggi che il modello ha indicato
                        come prova, riletti dall'archivio e non riscritti da lui. */}
                    {(c as CallCitata).passaggi?.length
                      ? (c as CallCitata).passaggi.map((p) => (
                          <span className="arow__hit" key={p.quando_ms}>
                            <span className="num">{tempo(p.quando_ms)}</span> {p.testo}
                          </span>
                        ))
                      : c.frammento && <span className="arow__hit">{conEvidenza(c.frammento)}</span>}
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
