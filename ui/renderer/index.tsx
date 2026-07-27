/**
 * Interfaccia di Scriba.
 *
 * Mostra la trascrizione mentre la call e' in corso e lascia rileggere quelle
 * passate. Non contiene logica: ogni comando passa dal processo principale, che
 * a sua volta parla col core.
 */

import { memo, StrictMode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'

import { PannelloAnalisi } from './Analisi'

declare global {
  interface Window {
    scriba: {
      endpoint(): Promise<{ port: number } | null>
      paths(): Promise<{ dataDir: string; screenshotDir: string }>
      get<T>(path: string): Promise<{ ok: boolean; status: number; body: T }>
      post<T>(path: string, body?: unknown): Promise<{ ok: boolean; status: number; body: T }>
      screenshot(): Promise<void>
      mostraFile(percorso: string): Promise<void>
      on(canale: string, callback: (payload: any) => void): () => void
    }
  }
}

interface Segmento {
  id: number
  source: 'mic' | 'loopback'
  t_start_ms: number
  t_end_ms: number
  testo: string
  is_final: boolean
}

interface Sessione {
  id: number
  titolo: string | null
  started_at: number
  durata_ms: number | null
  stato: string
}

interface Scatto {
  t_ms: number
  path: string
}

const ETICHETTA: Record<string, string> = { mic: 'Io', loopback: 'Altri' }

function tempo(ms: number): string {
  const totale = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(totale / 60)
  const s = totale % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function dataBreve(epochMs: number): string {
  return new Date(epochMs).toLocaleString('it-IT', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Una riga di trascrizione.
 *
 * Memoizzata perche' durante una call arriva un evento al secondo per traccia e
 * le righe gia' definitive non cambiano piu': senza, una call di un'ora
 * ricostruirebbe centinaia di righe a ogni parola nuova.
 */
const Riga = memo(function Riga({ s }: { s: Segmento }) {
  return (
    // data-t serve a ritrovare la riga quando si clicca il minuto di una task.
    <div className={`riga ${s.source} ${s.is_final ? '' : 'provvisoria'}`} data-t={s.t_start_ms}>
      <span className="tempo">{tempo(s.t_start_ms)}</span>
      <span className="chi">{ETICHETTA[s.source] ?? s.source}</span>
      <span className="testo">{s.testo}</span>
    </div>
  )
})

/** Chiede conferma prima di registrare anche gli altri partecipanti. */
function DialogoAvvio({
  onAnnulla,
  onConferma,
}: {
  onAnnulla: () => void
  onConferma: (titolo: string, consenso: boolean) => void
}) {
  const [titolo, setTitolo] = useState('')
  const [consenso, setConsenso] = useState(false)

  return (
    <div className="velo" onClick={onAnnulla}>
      <div className="dialogo" onClick={(e) => e.stopPropagation()}>
        <h2>Nuova registrazione</h2>
        <p>Verranno registrati il tuo microfono e l'audio che esce dal computer.</p>

        <div className="campo">
          <label htmlFor="titolo">Titolo (facoltativo)</label>
          <input
            id="titolo"
            type="text"
            value={titolo}
            autoFocus
            placeholder="Riunione con il cliente"
            onChange={(e) => setTitolo(e.target.value)}
          />
        </div>

        <label className="checkbox">
          <input type="checkbox" checked={consenso} onChange={(e) => setConsenso(e.target.checked)} />
          <span>
            Ho avvisato i partecipanti che la call viene registrata.
            <br />
            <span style={{ color: 'var(--testo-fioco)', fontSize: 12.5 }}>
              Registrare gli altri significa trattare i loro dati personali. Questa conferma viene
              annotata nella sessione, ma non sostituisce l'averglielo detto.
            </span>
          </span>
        </label>

        <div className="azioni">
          <button onClick={onAnnulla}>Annulla</button>
          <button className="primario" disabled={!consenso} onClick={() => onConferma(titolo, consenso)}>
            Avvia registrazione
          </button>
        </div>
      </div>
    </div>
  )
}

function App() {
  const [corePronto, setCorePronto] = useState(false)
  const [modello, setModello] = useState<'in_attesa' | 'caricamento' | 'pronto' | 'errore'>('in_attesa')
  const [registrando, setRegistrando] = useState(false)
  const [sessioneCorrente, setSessioneCorrente] = useState<number | null>(null)
  const [sessioneVista, setSessioneVista] = useState<number | null>(null)
  const [sessioni, setSessioni] = useState<Sessione[]>([])
  const [segmenti, setSegmenti] = useState<Segmento[]>([])
  const [scatti, setScatti] = useState<Scatto[]>([])
  const [trascorsi, setTrascorsi] = useState(0)
  const [dialogo, setDialogo] = useState(false)
  const [avviso, setAvviso] = useState<string | null>(null)
  const [esportando, setEsportando] = useState(false)
  const [hotkey, setHotkey] = useState<string | null>(null)

  const fine = useRef<HTMLDivElement>(null)
  const contenitore = useRef<HTMLElement>(null)
  const inizioLocale = useRef(Date.now())

  /**
   * Porta la trascrizione al minuto indicato, e lo evidenzia.
   *
   * E' il gesto che rende verificabile una task: si legge il campo, si clicca
   * il minuto, si vede da cosa il modello l'ha ricavato.
   */
  const vaiA = useCallback((t_ms: number) => {
    const el = contenitore.current
    if (!el) return
    // Si smette di seguire il parlato: l'utente e' andato a leggere altrove.
    seguiInFondo.current = false
    const righe = Array.from(el.querySelectorAll<HTMLElement>('[data-t]'))
    const bersaglio =
      righe.find((r) => Number(r.dataset.t) >= t_ms) ?? righe[righe.length - 1]
    if (!bersaglio) return
    bersaglio.scrollIntoView({ block: 'center', behavior: 'smooth' })
    bersaglio.classList.add('evidenziata')
    setTimeout(() => bersaglio.classList.remove('evidenziata'), 2200)
  }, [])
  // La trascrizione segue automaticamente il parlato, ma solo finche' l'utente
  // non scorre indietro a rileggere: strappargli via la vista mentre legge e'
  // il modo piu' rapido di rendere inutile la funzione.
  const seguiInFondo = useRef(true)

  const caricaSessioni = useCallback(async () => {
    const r = await window.scriba.get<Sessione[]>('/sessions')
    if (r.ok) setSessioni(r.body)
  }, [])

  const caricaSegmenti = useCallback(async (id: number) => {
    const r = await window.scriba.get<Segmento[]>(`/sessions/${id}/segments`)
    if (r.ok) setSegmenti(r.body)
  }, [])

  useEffect(() => {
    const off = [
      window.scriba.on('core:pronto', () => {
        setCorePronto(true)
        caricaSessioni()
      }),

      window.scriba.on('core:event', (ev: any) => {
        if (ev.type === 'transcript') {
          setSegmenti((prec) => {
            // Un parziale e il suo definitivo sono lo stesso pezzo di parlato:
            // si sostituisce la riga invece di accodarne un'altra, altrimenti
            // la stessa frase comparirebbe piu' volte mentre viene rifinita.
            const i = prec.findIndex((s) => !s.is_final && s.source === ev.source)
            const riga: Segmento = {
              id: i >= 0 ? prec[i].id : -Date.now(),
              source: ev.source,
              t_start_ms: ev.t_start_ms,
              t_end_ms: ev.t_end_ms,
              testo: ev.text,
              is_final: ev.is_final,
            }
            if (i < 0) return [...prec, riga]
            const copia = [...prec]
            copia[i] = riga
            return copia
          })
        } else if (ev.type === 'session_started') {
          setRegistrando(true)
          setSessioneCorrente(ev.session_id)
          setSessioneVista(ev.session_id)
          setSegmenti([])
          setScatti([])
        } else if (ev.type === 'session_stopped') {
          setRegistrando(false)
          setSessioneCorrente(null)
          caricaSessioni()
        } else if (ev.type === 'screenshot') {
          setScatti((prec) => [...prec, { t_ms: ev.t_ms, path: ev.path }])
        } else if (ev.type === 'modello') {
          setModello(ev.stato)
          if (ev.stato === 'errore') setAvviso(`Modello non caricato: ${ev.dettaglio ?? ''}`)
        }
      }),

      window.scriba.on('screenshot:ignorato', () =>
        setAvviso('Screenshot non salvato: nessuna registrazione in corso.'),
      ),

      window.scriba.on('hotkey:stato', (combo: string | null) => {
        setHotkey(combo)
        if (!combo) setAvviso('Nessuna scorciatoia disponibile per gli screenshot: usa il pulsante.')
      }),
    ]

    // Il core puo' essersi avviato prima che la pagina finisse di caricare: in
    // quel caso l'evento e' gia' passato e va recuperato lo stato corrente.
    window.scriba.endpoint().then(async (e) => {
      if (!e) return
      setCorePronto(true)
      caricaSessioni()
      const r = await window.scriba.get<{ modello: typeof modello }>('/health')
      if (r.ok && r.body?.modello) setModello(r.body.modello)
    })

    return () => off.forEach((f) => f())
  }, [caricaSessioni])

  // Cronometro contato in locale, riallineato al core ogni 20 secondi.
  //
  // Chiederlo al core a ogni tick significava un giro IPC + HTTP al secondo per
  // aggiornare due cifre. Il riallineamento periodico serve comunque, perche' e'
  // il core a sapere delle pause: un contatore puramente locale andrebbe avanti
  // anche a registrazione sospesa.
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
  }, [registrando])

  useEffect(() => {
    // Scorrimento istantaneo, non animato: durante una call arriva un evento al
    // secondo per traccia e le animazioni si accavallerebbero, dando la
    // sensazione che l'interfaccia arranchi.
    if (seguiInFondo.current) fine.current?.scrollIntoView({ block: 'end' })
  }, [segmenti, scatti])

  const avvia = async (titolo: string, consenso: boolean) => {
    setDialogo(false)
    setAvviso(null)
    const r = await window.scriba.post('/session/start', {
      titolo: titolo.trim() || null,
      consenso_confermato: consenso,
    })
    if (!r.ok) setAvviso(`Avvio non riuscito (${r.status}).`)
  }

  const ferma = async () => {
    const r = await window.scriba.post('/session/stop')
    if (!r.ok) setAvviso(`Arresto non riuscito (${r.status}).`)
  }

  const esporta = async () => {
    if (sessioneVista === null) return
    setEsportando(true)
    setAvviso(null)
    try {
      const r = await window.scriba.post<{ percorso: string }>(
        `/sessions/${sessioneVista}/export/markdown`,
      )
      if (r.ok) {
        // Si apre la cartella invece di limitarsi a dire che è andata bene: il
        // file serve, e cercarlo a mano è un passaggio in più senza motivo.
        await window.scriba.mostraFile(r.body.percorso)
        setAvviso(`Esportato in ${r.body.percorso}`)
      } else {
        setAvviso(`Export non riuscito (${r.status}).`)
      }
    } finally {
      setEsportando(false)
    }
  }

  const apriSessione = async (id: number) => {
    setSessioneVista(id)
    await caricaSegmenti(id)
    setScatti([])
  }

  // Si costruisce solo la sequenza, non gli elementi: renderizzare tocca alle
  // righe memoizzate, che cosi' saltano il lavoro quando non sono cambiate.
  const righe = useMemo(() => {
    const elementi: Array<{ chiave: string; t: number; seg?: Segmento; scatto?: Scatto }> = [
      ...segmenti.map((s) => ({ chiave: `s${s.id}`, t: s.t_start_ms, seg: s })),
      ...scatti.map((i) => ({ chiave: `i${i.t_ms}`, t: i.t_ms, scatto: i })),
    ]
    return elementi.sort((a, b) => a.t - b.t)
  }, [segmenti, scatti])

  return (
    <div className="app">
      <header className="barra">
        <span className="marchio">Scriba</span>

        {avviso && <div className="avviso">{avviso}</div>}

        <div className="stato">
          <span
            className={`pallino ${
              registrando ? 'registra' : modello === 'pronto' ? 'acceso' : ''
            }`}
          />
          {registrando
            ? 'Registrazione'
            : !corePronto
              ? 'Avvio del core...'
              : modello === 'caricamento' || modello === 'in_attesa'
                ? 'Carico il modello...'
                : modello === 'errore'
                  ? 'Modello non disponibile'
                  : 'Pronto'}
        </div>

        {registrando && <span className="cronometro">{tempo(trascorsi)}</span>}

        <button onClick={() => window.scriba.screenshot()} disabled={!registrando}>
          Screenshot
        </button>

        <button onClick={esporta} disabled={sessioneVista === null || esportando}>
          {esportando ? 'Esporto…' : 'Esporta'}
        </button>

        {registrando ? (
          <button className="pericolo" onClick={ferma}>
            Ferma
          </button>
        ) : (
          <button
            className="primario"
            onClick={() => setDialogo(true)}
            disabled={modello !== 'pronto'}
          >
            Registra
          </button>
        )}
      </header>

      <div className="corpo">
        <aside className="laterale">
          <h2>Call registrate</h2>
          {sessioni.length === 0 && <p style={{ color: 'var(--testo-fioco)' }}>Nessuna, per ora.</p>}
          {sessioni.map((s) => (
            <div
              key={s.id}
              className={`voce-sessione ${sessioneVista === s.id ? 'attiva' : ''}`}
              onClick={() => apriSessione(s.id)}
            >
              <div className="titolo">{s.titolo || `Call #${s.id}`}</div>
              <div className="meta">
                {dataBreve(s.started_at)}
                {s.durata_ms ? ` · ${tempo(s.durata_ms)}` : ''}
                {s.id === sessioneCorrente ? ' · in corso' : ''}
              </div>
            </div>
          ))}
        </aside>

        <main
          className="trascrizione"
          ref={contenitore}
          onScroll={(e) => {
            const el = e.currentTarget
            seguiInFondo.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
          }}
        >
          {righe.length === 0 ? (
            <div className="vuoto">
              {registrando ? (
                <>In ascolto. Il testo comparira' qui mentre parlate.</>
              ) : (
                <>
                  Premi <b>Registra</b> per iniziare.
                  {hotkey && (
                    <>
                      <br />
                      Durante la call,{' '}
                      {hotkey
                        .replace('CommandOrControl', 'Ctrl')
                        .split('+')
                        .map((tasto, i) => (
                          <span key={tasto}>
                            {i > 0 && ' + '}
                            <kbd>{tasto}</kbd>
                          </span>
                        ))}{' '}
                      cattura uno screenshot e lo aggancia al punto in cui siete.
                    </>
                  )}
                </>
              )}
            </div>
          ) : (
            righe.map((r) =>
              r.seg ? (
                <Riga key={r.chiave} s={r.seg} />
              ) : (
                <div key={r.chiave} className="scatto">
                  Screenshot a {tempo(r.t)}
                </div>
              ),
            )
          )}
          <div ref={fine} />
        </main>

        <section className="analisi">
          <PannelloAnalisi
            sessionId={sessioneVista}
            registrando={registrando && sessioneVista === sessioneCorrente}
            onVaiA={vaiA}
          />
        </section>
      </div>

      {dialogo && <DialogoAvvio onAnnulla={() => setDialogo(false)} onConferma={avvia} />}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
