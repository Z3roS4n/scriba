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
import { scorciatoiaLeggibile, type EventoCore, type Scatto, type Segmento, type Sessione, type Task } from './tipi'

interface Avviso {
  testo: string
  azione?: { etichetta: string; onClick: () => void }
}

function App() {
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
  const [esportando, setEsportando] = useState(false)
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

  const [scorciatoiaOverlay, setScorciatoiaOverlay] = useState<string | null>(null)
  const [larghezza, setLarghezza] = useState(window.innerWidth)

  const trascrizioneRef = useRef<TrascrizioneHandle>(null)
  const inizioLocale = useRef(Date.now())

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
          // Si propone, non si avvia: registrare coinvolge altre persone.
          setCallRilevata({ pid: e.pid, nome: e.nome, piattaforma: e.piattaforma })
        } else if (ev.type === 'modello') {
          const e = ev as Extract<EventoCore, { type: 'modello' }>
          setModello(e.stato)
          if (e.stato === 'errore') mostraAvviso(`Modello non caricato: ${e.dettaglio ?? ''}`)
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
      const r = await window.scriba.get<{ modello: StatoModello }>('/health')
      if (r.ok && r.body?.modello) setModello(r.body.modello)
    })

    return () => off.forEach((f) => f())
  }, [caricaSessioni, mostraAvviso])

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
  // mai. Non esiste nel handoff un modo dichiarato per "riraggiungere" il
  // pannello analisi da sotto i 1100px (nessuna classe per quel pulsante e la
  // vista sotto i 900px e' segnata come mancante in comportamento.md): qui si
  // nasconde soltanto, senza inventare un controllo che il design non ha
  // ancora definito.
  const nascondiAnalisi = larghezza < 1100
  const nascondiCalls = larghezza < 900

  return (
    <div className="win">
      {/* display:contents, non un ternario: se si smontasse qui la topbar non
          perderebbe stato che conti, ma tenerla nello stesso schema di visibilita'
          del corpo (sotto) rende esplicito che la rassegna sostituisce tutto. */}
      <div style={{ display: rassegnaIndice === null ? 'contents' : 'none' }}>
        <Topbar
          corePronto={corePronto}
          modello={modello}
          registrando={registrando}
          trascorsi={trascorsi}
          sessioneVista={sessioneVista}
          esportando={esportando}
          onScreenshot={() => window.scriba.screenshot()}
          onEsporta={esporta}
          onRegistra={apriDialogoRegistra}
          onFerma={ferma}
        />
        {avviso && <Barra testo={avviso.testo} azione={avviso.azione} onChiudi={() => setAvviso(null)} />}
      </div>

      {/* Anche qui display:none e non uno smontaggio: e' quello che permette al
          pannello analisi di ritrovare da solo la task su cui si era fermato
          quando si torna dalla rassegna (comportamento.md, "Rassegna task"). */}
      <div className="win__body" style={{ display: rassegnaIndice === null ? 'flex' : 'none' }}>
        {!nascondiCalls && (
          <ElencoCall
            sessioni={sessioni}
            sessioneVista={sessioneVista}
            sessioneCorrente={sessioneCorrente}
            compatta={taskProve !== null}
            onApri={apriSessione}
            onRiapri={() => setTaskProve(null)}
          />
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
        />

        {taskProve && (
          <PannelloProve task={taskProve} onVaiA={vaiA} onChiudi={() => setTaskProve(null)} />
        )}

        {!nascondiAnalisi && (
          <PannelloAnalisi
            sessione={sessioneVistaObj}
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
          />
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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
