/**
 * Interfaccia di Scriba — composizione della finestra principale.
 *
 * Tiene lo stato e ascolta gli eventi del core; la resa vera e' delegata ai
 * componenti di ogni colonna. Non contiene logica di dominio: ogni comando
 * passa da `window.scriba`, che a sua volta parla col processo principale e
 * col core.
 */

import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'

import { Topbar, type StatoModello } from './Topbar'
import { ElencoCall } from './ElencoCall'
import { Trascrizione, type TrascrizioneHandle } from './Trascrizione'
import { PannelloAnalisi } from './Analisi'
import { PannelloProve } from './Prove'
import { Rassegna } from './Rassegna'
import { AvvisoCall, Barra, ModaleConsenso } from './Dialoghi'
import { Archivio } from './Archivio'
import { useSchermi } from './schermi'
import { useTema } from './tema'
import { scorciatoiaLeggibile, type Cliente, type DbDanneggiato, type EventoCore, type Scatto, type Segmento, type Sessione, type Task } from './tipi'
import { ContestoLingua, useLingua } from './lingua'
import { useT } from './lingua'

interface Avviso {
  testo: string
  azione?: { etichetta: string; onClick: () => void }
}

function App() {
  const t = useT()
  const [corePronto, setCorePronto] = useState(false)
  const [modello, setModello] = useState<StatoModello>('in_attesa')
  const [registrando, setRegistrando] = useState(false)
  const [sessioneCorrente, setSessioneCorrente] = useState<number | null>(null)
  const [sessioneVista, setSessioneVista] = useState<number | null>(null)
  const [sessioni, setSessioni] = useState<Sessione[]>([])
  const [segmenti, setSegmenti] = useState<Segmento[]>([])
  const [scatti, setScatti] = useState<Scatto[]>([])
  const [trascorsi, setTrascorsi] = useState(0)

  const [dialogoConsenso, setDialogoConsenso] = useState(false)
  const [titoloProposto, setTitoloProposto] = useState('')
  const [avviso, setAvviso] = useState<Avviso | null>(null)
  // Stato suo, separato da `avviso`: quello viene azzerato dai flussi normali
  // (fine registrazione, cambio call), e un avviso che dice «il tuo database è
  // stato messo da parte» non deve sparire perché nel frattempo è successo
  // qualcos'altro.
  const [dbDanneggiato, setDbDanneggiato] = useState<DbDanneggiato | null>(null)
  const [esportando, setEsportando] = useState(false)
  const schermi = useSchermi()
  useTema()
  const [callRilevata, setCallRilevata] = useState<{
    pid: number
    nome: string
    piattaforma: string
  } | null>(null)

  // Pannello prove e citazioni: chi le apre e' il pannello analisi (che vive in
  // Analisi.tsx), ma lo stato sta qui perche' tocca anche l'elenco call (si
  // stringe a binario) e la trascrizione (`.is-cited`).
  const [taskProve, setTaskProve] = useState<Task | null>(null)
  const [citazioni, setCitazioni] = useState<number[]>([])

  // Rassegna a tutta finestra: quando e' attiva sostituisce tutto cio' che sta
  // sotto `.win`, topbar compresa (ha la sua, `.review__bar`). Il resto della
  // finestra non si smonta — solo si nasconde — cosi' il pannello analisi
  // ritrova da solo la task su cui si era fermato, senza che questo file debba
  // saperne nulla.
  const [rassegnaIndice, setRassegnaIndice] = useState<number | null>(null)

  // L'archivio sostituisce l'interfaccia con la stessa regola della rassegna:
  // mentre si cerca nello storico non si sta guardando una call in particolare.
  const [archivioAperto, setArchivioAperto] = useState(false)
  const [clienti, setClienti] = useState<Cliente[]>([])

  /** Rassegna e archivio prendono la finestra intera: hanno la loro barra. */
  const aTuttaFinestra = rassegnaIndice !== null || archivioAperto

  const [scorciatoiaOverlay, setScorciatoiaOverlay] = useState<string | null>(null)
  const [larghezza, setLarghezza] = useState(window.innerWidth)

  // Sotto le soglie strette (comportamento.md, 9) i due pannelli si nascondono
  // da soli, ma restano raggiungibili: un clic li forza aperti finche' la
  // finestra resta stretta. Sono scelte manuali, non stato della sessione: non
  // hanno senso finche' non torna a mancare spazio.
  const [callsForzate, setCallsForzate] = useState(false)
  const [analisiForzata, setAnalisiForzata] = useState(false)

  const trascrizioneRef = useRef<TrascrizioneHandle>(null)
  const inizioLocale = useRef(Date.now())
  // L'ascoltatore degli eventi qui sotto si registra una volta sola (dipendenze
  // stabili, come per gli altri eventi): per sapere se un evento diarizzazione
  // riguarda la call aperta ADESSO serve leggerla da un ref, non catturarla
  // nella chiusura, altrimenti resterebbe quella di quando l'ascoltatore si e'
  // agganciato la prima volta.
  const sessioneVistaRef = useRef<number | null>(null)

  const mostraAvviso = useCallback((testo: string, azione?: Avviso['azione']) => {
    setAvviso({ testo, azione })
  }, [])

  /** Porta la trascrizione al minuto indicato. E' l'unico gesto che rende
   * verificabile una task, un punto saliente o una citazione: si legge il
   * campo, si clicca il minuto, si vede da cosa viene davvero. */
  const vaiA = useCallback((t_ms: number) => {
    trascrizioneRef.current?.vaiA(t_ms)
  }, [])

  const caricaSessioni = useCallback(async () => {
    const r = await window.scriba.get<Sessione[]>('/sessions')
    if (r.ok) setSessioni(r.body)
  }, [])

  const caricaClienti = useCallback(async () => {
    const r = await window.scriba.get<Cliente[]>('/clienti')
    if (r.ok) setClienti(r.body)
  }, [])

  /**
   * Chiede al core se sta registrando adesso, invece di dedurlo dagli eventi.
   *
   * Finora questa finestra lo imparava **solo** da `session_started`. Un evento
   * che non arriva — la finestra non c'era ancora, il core stava gia' lavorando,
   * la pagina si e' ricaricata — la lasciava convinta che non stesse succedendo
   * niente, per sempre: il pulsante diceva «Registra» e premerlo era la cosa
   * sbagliata, perche' una registrazione era in corso davvero.
   *
   * Uno stato che si ricostruisce chiedendo non ha quel modo di rompersi.
   */
  const recuperaRegistrazione = useCallback(async () => {
    const r = await window.scriba.get<{
      in_registrazione: boolean
      session_id?: number
      now_ms?: number
    }>('/session/state')
    if (!r.ok || !r.body?.in_registrazione) return

    setRegistrando(true)
    if (r.body.session_id != null) {
      setSessioneCorrente(r.body.session_id)
      setSessioneVista((prec) => prec ?? r.body.session_id!)
    }
    // Il cronometro riparte da dove sta la call, non da zero: e' il core a
    // sapere da quanto va, e a sapere delle pause.
    if (r.body.now_ms != null) {
      inizioLocale.current = Date.now()
      setTrascorsi(r.body.now_ms)
    }
  }, [])

  // I clienti si creano dalla finestra delle impostazioni, che e' un altro
  // processo: quando ne nasce uno, questa finestra non lo sa. Rileggerli
  // all'apertura dell'archivio e' il momento esatto in cui la differenza si
  // vedrebbe — senza, si aggiunge un cliente e nel menu non c'e' finche' non si
  // riavvia l'applicazione, che e' esattamente il difetto gia' visto col
  // modello locale.
  useEffect(() => {
    if (archivioAperto) caricaClienti()
  }, [archivioAperto, caricaClienti])

  const caricaSegmenti = useCallback(async (id: number) => {
    const r = await window.scriba.get<Segmento[]>(`/sessions/${id}/segments`)
    if (r.ok) setSegmenti(r.body)
  }, [])

  const caricaScatti = useCallback(async (id: number) => {
    // Rotta nuova (contratto-api.md): se il core non la serve ancora si resta
    // senza scatti invece di rompere la schermata.
    const r = await window.scriba.get<Scatto[]>(`/sessions/${id}/screenshots`)
    if (r.ok) setScatti(r.body)
  }, [])

  const apriSessione = useCallback(
    (id: number) => {
      setSessioneVista(id)
      // Si svuota subito, non solo dopo la risposta: altrimenti per un istante
      // si vedrebbe la trascrizione della call precedente sotto il titolo di
      // quella nuova.
      setSegmenti([])
      setScatti([])
      setTaskProve(null)
      setCitazioni([])
      caricaSegmenti(id)
      caricaScatti(id)
    },
    [caricaSegmenti, caricaScatti],
  )

  useEffect(() => {
    sessioneVistaRef.current = sessioneVista
  }, [sessioneVista])

  /** Rete di sicurezza della diarizzazione (vedi Analisi.tsx): ricarica i
   * segmenti della call aperta ora, se ce n'e' una aperta. */
  const ricaricaSegmentiVisti = useCallback(() => {
    if (sessioneVista != null) caricaSegmenti(sessioneVista)
  }, [sessioneVista, caricaSegmenti])

  /** Un nome dato a una voce si vede subito nella trascrizione: si aggiornano
   * i segmenti gia' in memoria invece di aspettare un giro di rete in più. */
  const rinominaVoceInSegmenti = useCallback((speakerId: number, nome: string) => {
    setSegmenti((prec) =>
      prec.map((s) => (s.speaker?.id === speakerId ? { ...s, speaker: { ...s.speaker, nome_reale: nome } } : s)),
    )
  }, [])

  const avvia = useCallback(
    async (titolo: string, consenso: boolean) => {
      setDialogoConsenso(false)
      setAvviso(null)
      const r = await window.scriba.post('/session/start', {
        titolo: titolo.trim() || null,
        consenso_confermato: consenso,
      })
      if (!r.ok) mostraAvviso(`Avvio non riuscito (${r.status}).`)
    },
    [mostraAvviso],
  )

  const apriDialogoRegistra = useCallback(() => {
    setTitoloProposto('')
    setDialogoConsenso(true)
  }, [])

  const ferma = useCallback(async () => {
    const r = await window.scriba.post('/session/stop')
    if (!r.ok) mostraAvviso(`Arresto non riuscito (${r.status}).`)
  }, [mostraAvviso])

  const esporta = useCallback(async () => {
    if (sessioneVista === null) return
    setEsportando(true)
    setAvviso(null)
    try {
      // Si apre la cartella invece di limitarsi a dire che e' andata bene: il
      // file serve, e cercarlo a mano e' un passaggio in piu' senza motivo.
      const r = await window.scriba.post<{ percorso: string }>(
        `/sessions/${sessioneVista}/export/markdown`,
      )
      if (r.ok) {
        await window.scriba.mostraFile(r.body.percorso)
        mostraAvviso(`Esportato in ${r.body.percorso}`)
      } else {
        mostraAvviso(`Export non riuscito (${r.status}).`)
      }
    } finally {
      setEsportando(false)
    }
  }, [sessioneVista, mostraAvviso])

  useEffect(() => {
    const off = [
      window.scriba.on('core:pronto', () => {
        setCorePronto(true)
        caricaSessioni()
        caricaClienti()
        recuperaRegistrazione()
      }),

      window.scriba.on('core:event', (ev: EventoCore) => {
        if (ev.type === 'transcript') {
          const e = ev as Extract<EventoCore, { type: 'transcript' }>
          setSegmenti((prec) => {
            // Un parziale e il suo definitivo sono lo stesso pezzo di parlato:
            // si sostituisce la riga invece di accodarne un'altra, altrimenti
            // la stessa frase comparirebbe piu' volte mentre viene rifinita.
            // Riusare lo stesso id e' anche cio' che permette a Trascrizione
            // di NON smontare e rimontare la riga alla chiusura della frase.
            const i = prec.findIndex((s) => !s.is_final && s.source === e.source)
            // Un definitivo senza testo chiude la frase dicendo che non ne e'
            // rimasto niente: la riga provvisoria va tolta, non congelata
            // vuota. Il core ha gia' cancellato il segmento dal database.
            if (e.is_final && !e.text) return i < 0 ? prec : prec.filter((_, k) => k !== i)
            const riga: Segmento = {
              id: i >= 0 ? prec[i].id : -Date.now(),
              source: e.source,
              t_start_ms: e.t_start_ms,
              t_end_ms: e.t_end_ms,
              testo: e.text,
              is_final: e.is_final,
            }
            if (i < 0) return [...prec, riga]
            const copia = [...prec]
            copia[i] = riga
            return copia
          })
        } else if (ev.type === 'session_started') {
          const e = ev as Extract<EventoCore, { type: 'session_started' }>
          // La periferica scelta nelle impostazioni poteva non esserci più
          // (cuffie staccate, scheda cambiata). Il core ripiega sul
          // predefinito e lo dice; qui non lo leggeva nessuno, e chi
          // registrava dal microfono sbagliato lo scopriva a call finita,
          // quando non si rifà (#73).
          if (e.fallback && Object.keys(e.fallback).length > 0) {
            const nome = (s: string) => e.devices?.[s] ?? 'quello predefinito'
            const parti = Object.keys(e.fallback).map((s) =>
              s === 'mic'
                ? `il microfono scelto non c'è più: sto registrando la tua voce con «${nome('mic')}»`
                : `il dispositivo audio scelto non c'è più: sto registrando gli altri con «${nome('loopback')}»`,
            )
            // Maiuscola sulla prima, e il punto alla fine: sono frasi, non voci
            // di elenco, e le legge qualcuno che sta entrando in riunione.
            const testo = parti.join('; ')
            mostraAvviso(`${testo.charAt(0).toUpperCase()}${testo.slice(1)}.`)
          }
          setRegistrando(true)
          setSessioneCorrente(e.session_id)
          setSessioneVista(e.session_id)
          setSegmenti([])
          setScatti([])
          setTrascorsi(0)
          inizioLocale.current = Date.now()
          setTaskProve(null)
          setCitazioni([])
          // Entrata ottimistica nell'elenco: si mostra subito "in corso", la
          // conferma dal server (con titolo e piattaforma veri) arriva a
          // momenti da caricaSessioni().
          setSessioni((prec) => {
            if (prec.some((s) => s.id === e.session_id)) return prec
            const stub: Sessione = {
              id: e.session_id,
              titolo: e.titolo,
              piattaforma: null,
              started_at: Date.now(),
              ended_at: null,
              durata_ms: null,
              stato: 'recording',
              lingua: null,
              n_task: 0,
              n_da_confermare: 0,
            }
            return [stub, ...prec]
          })
          caricaSessioni()
        } else if (ev.type === 'session_stopped') {
          setRegistrando(false)
          setSessioneCorrente(null)
          caricaSessioni()
        } else if (ev.type === 'screenshot') {
          const e = ev as Extract<EventoCore, { type: 'screenshot' }>
          setScatti((prec) => [
            ...prec,
            { id: e.id, t_ms: e.t_ms, path: e.path, width: null, height: null, nota_utente: null },
          ])
        } else if (ev.type === 'call_rilevata') {
          const e = ev as Extract<EventoCore, { type: 'call_rilevata' }>
          setCallRilevata({ pid: e.pid, nome: e.nome, piattaforma: e.piattaforma })
          // «Avvia da sola» apre la finestra del consenso, non la registrazione.
          // È il punto in cui questa impostazione si può fraintendere: quello
          // che diventa automatico è la richiesta, non il permesso. Registrare
          // altre persone resta una cosa che si conferma a mano, sempre.
          if (e.avvio_automatico) {
            setCallRilevata(null)
            setTitoloProposto(e.piattaforma ?? '')
            setDialogoConsenso(true)
          }
        } else if (ev.type === 'modello') {
          const e = ev as Extract<EventoCore, { type: 'modello' }>
          setModello(e.stato)
          if (e.stato === 'errore') mostraAvviso(`Modello non caricato: ${e.dettaglio ?? ''}`)
        } else if (ev.type === 'diarizzazione') {
          const e = ev as Extract<EventoCore, { type: 'diarizzazione' }>
          // Solo "fatto": e' l'unico momento in cui `speaker` sui segmenti
          // cambia davvero. Si ricarica solo se e' proprio la call che si sta
          // guardando ora — sessioneVistaRef, non lo stato: questo ascoltatore
          // si registra una volta sola, catturare sessioneVista lo terrebbe
          // fermo al valore di quando la finestra si e' aperta.
          if (e.stato === 'fatto' && sessioneVistaRef.current === e.session_id) {
            caricaSegmenti(e.session_id)
          }
        }
      }),

      window.scriba.on('screenshot:ignorato', () =>
        mostraAvviso('Screenshot non salvato: nessuna registrazione in corso.'),
      ),
    ]

    // Il core puo' essersi avviato prima che la pagina finisse di caricare: in
    // quel caso l'evento e' gia' passato e va recuperato lo stato corrente.
    window.scriba.endpoint().then(async (e) => {
      if (!e) return
      setCorePronto(true)
      caricaSessioni()
      caricaClienti()
      recuperaRegistrazione()
      const r = await window.scriba.get<{
        modello: StatoModello
        db_danneggiato: DbDanneggiato | null
      }>('/health')
      if (r.ok && r.body?.modello) setModello(r.body.modello)
      // Arriva valorizzato solo quando è successo davvero, e allora va detto:
      // senza, l'elenco delle call risulta tornato indietro e basta.
      if (r.ok && r.body?.db_danneggiato) setDbDanneggiato(r.body.db_danneggiato)
    })

    return () => off.forEach((f) => f())
  }, [caricaSessioni, caricaClienti, recuperaRegistrazione, mostraAvviso])

  // La prima volta che l'elenco arriva senza niente aperto si mostra la call
  // piu' recente — o quella in corso, se la pagina si e' caricata (o
  // ricaricata) mentre una registrazione era gia' partita altrove. In quel
  // caso serve anche recuperarne la trascrizione: gli eventi live persi non
  // tornano indietro.
  useEffect(() => {
    if (sessioneVista != null) return
    if (sessioni.length === 0) return
    const attuale = sessioni.find((s) => s.stato === 'recording')
    const bersaglio = attuale ?? sessioni[0]
    setSessioneVista(bersaglio.id)
    if (attuale) {
      setRegistrando(true)
      setSessioneCorrente(attuale.id)
    }
    caricaSegmenti(bersaglio.id)
    caricaScatti(bersaglio.id)
  }, [sessioni, sessioneVista, caricaSegmenti, caricaScatti])

  // Cronometro contato in locale, riallineato al core ogni 20 secondi.
  //
  // Chiederlo al core a ogni tick significava un giro IPC + HTTP al secondo
  // per aggiornare due cifre. Il riallineamento periodico serve comunque,
  // perche' e' il core a sapere delle pause: un contatore puramente locale
  // andrebbe avanti anche a registrazione sospesa.
  useEffect(() => {
    if (!registrando) return

    let offset = trascorsi - (Date.now() - inizioLocale.current)
    const tick = setInterval(() => {
      setTrascorsi(Date.now() - inizioLocale.current + offset)
    }, 500)

    const risincronizza = setInterval(async () => {
      const r = await window.scriba.get<{ now_ms: number }>('/session/state')
      if (r.ok && r.body?.now_ms != null) {
        offset = r.body.now_ms - (Date.now() - inizioLocale.current)
      }
    }, 20_000)

    return () => {
      clearInterval(tick)
      clearInterval(risincronizza)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registrando])

  // Le scorciatoie si registrano una volta all'avvio: serve comunque sapere
  // com'e' andata, sia per il suggerimento a finestra vuota ("Alt+R per la
  // striscia") sia per segnalare — livello 1, non bloccante — quando quella
  // dell'overlay e' gia' presa da un'altra applicazione.
  useEffect(() => {
    window.scriba.registraScorciatoie().then(({ overlay }) => {
      setScorciatoiaOverlay(overlay)
      if (!overlay) {
        mostraAvviso("La scorciatoia per la striscia non è disponibile: la sta già usando un'altra applicazione.", {
          etichetta: 'Cambia scorciatoia',
          onClick: () => window.scriba.apriImpostazioni(),
        })
      }
    })
  }, [mostraAvviso])

  useEffect(() => {
    const onResize = () => setLarghezza(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const sessioneVistaObj = useMemo(
    () => sessioni.find((s) => s.id === sessioneVista) ?? null,
    [sessioni, sessioneVista],
  )
  // Muta il pannello analisi e ferma la trascrizione sul "in corso" solo per
  // la call che si sta REGISTRANDO ora: sfogliare una call passata mentre
  // un'altra registra altrove (di fatto impossibile qui, ma non si sa mai)
  // non deve congelare il suo pannello.
  const vistaInDiretta = registrando && sessioneVista === sessioneCorrente

  // Punti di rottura (comportamento.md, 9): sotto 1100px il pannello analisi
  // sparisce, sotto 900px anche l'elenco call. La trascrizione non sparisce
  // mai. Il design non ha disegnato i comandi per riraggiungerli (nessuna
  // classe dedicata nel handoff): qui si costruiscono con .btn/.btn--icon/
  // .toolbar, che gia' esistono, invece di aggiungerne di nuove.
  const nascondiAnalisi = larghezza < 1100
  const nascondiCalls = larghezza < 900

  // La riapertura manuale vale solo mentre la soglia resta superata: se la
  // finestra torna larga da sola (l'utente la ridimensiona) il pannello e' di
  // nuovo al suo posto normale, e la scelta forzata non deve sopravvivere fino
  // alla prossima volta che si stringe, altrimenti riapparirebbe senza che
  // nessuno l'abbia chiesto stavolta.
  useEffect(() => {
    if (!nascondiCalls) setCallsForzate(false)
  }, [nascondiCalls])
  useEffect(() => {
    if (!nascondiAnalisi) setAnalisiForzata(false)
  }, [nascondiAnalisi])

  const mostraCalls = !nascondiCalls || callsForzate
  const mostraAnalisi = !nascondiAnalisi || analisiForzata

  const elencoCall = (
    <ElencoCall
      sessioni={sessioni}
      sessioneVista={sessioneVista}
      sessioneCorrente={sessioneCorrente}
      compatta={taskProve !== null}
      onApri={apriSessione}
      onRiapri={() => setTaskProve(null)}
    />
  )

  const pannelloAnalisi = (
    <PannelloAnalisi
      sessione={sessioneVistaObj}
      segmenti={segmenti}
      // Stesso valore in entrambe le prop, di proposito: "registrando" e'
      // cio' che disabilita Analizza (non si analizza una call non ancora
      // finita), "compatto" e' la stessa condizione vista dal CSS
      // (.analysis--muted). Il flag e' della call GUARDATA, non globale:
      // sfogliare una call passata mentre un'altra registra altrove non
      // deve bloccarne l'analisi.
      registrando={vistaInDiretta}
      compatto={vistaInDiretta}
      onVaiA={vaiA}
      onCitazioni={setCitazioni}
      onProve={setTaskProve}
      onRassegna={setRassegnaIndice}
      onRicaricaSegmenti={ricaricaSegmentiVisti}
    />
  )

  return (
    <div className="win">
      {/* La barra in alto resta sempre, anche con rassegna o archivio aperti.
          In una finestra senza cornice questa barra E' la cornice: porta
          riduci, ingrandisci e chiudi (Topbar.tsx, .wincontrols). Nasconderla
          insieme al corpo lasciava senza un modo di chiudere la finestra col
          mouse finche' non si usciva dal piano (#74).

          I piani si aprono sotto: sono fratelli di .win__body dentro la stessa
          colonna flex, e portano gia' la loro barra con il titolo e l'uscita. */}
      <Topbar
        corePronto={corePronto}
        modello={modello}
        registrando={registrando}
        trascorsi={trascorsi}
        sessioneVista={sessioneVista}
        esportando={esportando}
        schermi={schermi}
        onScreenshot={(idSchermo) => window.scriba.screenshot(idSchermo)}
        onArchivio={() => setArchivioAperto(true)}
        onEsporta={esporta}
        onRegistra={apriDialogoRegistra}
        onFerma={ferma}
      />

      {/* Anche gli avvisi restano. Non parlano della call che si sta
          guardando: dicono che il core non e' partito, che il modello non si
          e' caricato, che la scorciatoia della striscia e' occupata. Sparivano
          aprendo l'archivio, e uno che arrivava mentre il piano era aperto non
          lo vedeva nessuno. */}
      <>
        {dbDanneggiato && (
          // Prima dell'avviso normale: se ci sono tutti e due, questo è quello
          // che cambia cosa l'utente sta guardando.
          <div className="notice notice--rosso">
            Il database non si leggeva e Scriba è ripartito
            {dbDanneggiato.ripristinato ? ' da un backup' : ' da vuoto'}: le call registrate dopo
            non compaiono più. I file originali non sono stati cancellati.
            <span className="notice__spacer" />
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => window.scriba.apriCartella(dbDanneggiato.quarantena)}
            >
              {t('idx.apri_cartella')}
            </button>
            <button type="button" className="btn--link" onClick={() => setDbDanneggiato(null)}>
              ✕
            </button>
          </div>
        )}
        {avviso && <Barra testo={avviso.testo} azione={avviso.azione} onChiudi={() => setAvviso(null)} />}
      </>

      {/* Anche qui display:none e non uno smontaggio: e' quello che permette al
          pannello analisi di ritrovare da solo la task su cui si era fermato
          quando si torna dalla rassegna (comportamento.md, "Rassegna task"). */}
      <div className="win__body" style={{ display: aTuttaFinestra ? 'none' : 'flex' }}>
        {mostraCalls ? (
          nascondiCalls ? (
            // Riaperto a mano su una finestra ancora stretta: resta un modo
            // per richiuderlo senza aspettare di allargare la finestra.
            <div style={{ display: 'flex', flexDirection: 'column', flex: 'none' }}>
              <div
                className="toolbar"
                style={{ justifyContent: 'flex-end', padding: 'var(--sp-2)', borderBottom: '1px solid var(--line)' }}
              >
                <button className="btn btn--icon" aria-label={t('idx.nascondi_call')} onClick={() => setCallsForzate(false)}>
                  ‹
                </button>
              </div>
              {elencoCall}
            </div>
          ) : (
            elencoCall
          )
        ) : (
          // Sotto i 900px l'elenco si nasconde (comportamento.md, 9): la
          // trascrizione non sparisce mai, quindi questo binario minimo resta
          // l'unico modo per andarlo a riprendere.
          <div
            className="toolbar"
            style={{ flexDirection: 'column', flex: 'none', padding: 'var(--sp-3) 0', borderRight: '1px solid var(--line)' }}
          >
            <button className="btn btn--icon" aria-label={t('idx.mostra_call')} onClick={() => setCallsForzate(true)}>
              ›
            </button>
          </div>
        )}

        <Trascrizione
          ref={trascrizioneRef}
          sessione={sessioneVistaObj}
          segmenti={segmenti}
          scatti={scatti}
          inDiretta={vistaInDiretta}
          citate={citazioni}
          scorciatoiaStriscia={scorciatoiaOverlay ? scorciatoiaLeggibile(scorciatoiaOverlay) : null}
          onRegistra={apriDialogoRegistra}
          onApriScatto={(percorso) => window.scriba.mostraFile(percorso)}
          onVoceRinominata={rinominaVoceInSegmenti}
        />

        {taskProve && (
          <PannelloProve task={taskProve} onVaiA={vaiA} onChiudi={() => setTaskProve(null)} />
        )}

        {mostraAnalisi ? (
          nascondiAnalisi ? (
            // Stessa idea del binario dell'elenco call: riaperto a mano, resta
            // richiudibile senza dover allargare la finestra.
            <div style={{ display: 'flex', flexDirection: 'column', flex: 'none' }}>
              <div
                className="toolbar"
                style={{ justifyContent: 'flex-start', padding: 'var(--sp-2)', borderBottom: '1px solid var(--line)' }}
              >
                <button className="btn btn--icon" aria-label={t('idx.nascondi_analisi')} onClick={() => setAnalisiForzata(false)}>
                  ›
                </button>
              </div>
              {pannelloAnalisi}
            </div>
          ) : (
            pannelloAnalisi
          )
        ) : (
          // Sotto i 1100px il pannello analisi si nasconde (comportamento.md,
          // 9) ma resta "raggiungibile dalla barra": questo binario e' quella
          // barra, con le stesse classi del resto dell'interfaccia.
          <div
            className="toolbar"
            style={{ flexDirection: 'column', flex: 'none', padding: 'var(--sp-3) 0', borderLeft: '1px solid var(--line)' }}
          >
            <button className="btn btn--icon" aria-label={t('idx.mostra_analisi')} onClick={() => setAnalisiForzata(true)}>
              ‹
            </button>
          </div>
        )}
      </div>

      {rassegnaIndice !== null && sessioneVistaObj && (
        <Rassegna
          sessione={sessioneVistaObj}
          segmenti={segmenti}
          indiceIniziale={rassegnaIndice}
          onEsci={() => setRassegnaIndice(null)}
        />
      )}

      {archivioAperto && (
        <Archivio
          clienti={clienti}
          onApri={(id) => {
            apriSessione(id)
            setArchivioAperto(false)
          }}
          onEsci={() => setArchivioAperto(false)}
          onClientiCambiati={() => {
            caricaClienti()
            // Non solo i conteggi dei clienti: il cliente compare anche
            // nell'elenco laterale, che va rifatto perche' resti d'accordo.
            caricaSessioni()
          }}
        />
      )}

      {callRilevata && !registrando && (
        <AvvisoCall
          nome={callRilevata.piattaforma}
          onRegistra={() => {
            // Si passa dal dialogo normale: la conferma sul consenso non si
            // salta perche' la call e' stata riconosciuta da sola.
            setTitoloProposto(callRilevata.piattaforma)
            setCallRilevata(null)
            setDialogoConsenso(true)
          }}
          onNo={async () => {
            const pid = callRilevata.pid
            setCallRilevata(null)
            // Non si smette di sorvegliare: si dimentica questa proposta,
            // cosi' alla prossima riunione la domanda torna.
            await window.scriba.post(`/rilevamento/ignora/${pid}`)
          }}
          onChiudi={() => setCallRilevata(null)}
        />
      )}

      {dialogoConsenso && (
        <ModaleConsenso titoloIniziale={titoloProposto} onAnnulla={() => setDialogoConsenso(false)} onConferma={avvia} />
      )}
    </div>
  )
}

/**
 * La lingua avvolge tutto l'albero. Un contesto e non una variabile di modulo:
 * i componenti sotto `memo` non si ridisegnerebbero al cambio, perché le loro
 * prop non cambiano — e una schermata che resta nella lingua di prima è il
 * modo in cui una traduzione si dimentica un pezzo senza che nessuno lo veda.
 */
function ConLingua({ children }: { children: React.ReactNode }) {
  const { risolta } = useLingua()
  return <ContestoLingua.Provider value={risolta}>{children}</ContestoLingua.Provider>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConLingua>
      <App />
    </ConLingua>
  </StrictMode>,
)
