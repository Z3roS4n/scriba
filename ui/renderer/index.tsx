/**
 * Interfaccia di Scriba.
 *
 * Mostra la trascrizione mentre la call e' in corso e lascia rileggere quelle
 * passate. Non contiene logica: ogni comando passa dal processo principale, che
 * a sua volta parla col core.
 */

import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactElement } from 'react'
import { createRoot } from 'react-dom/client'

declare global {
  interface Window {
    scriba: {
      endpoint(): Promise<{ port: number } | null>
      paths(): Promise<{ dataDir: string; screenshotDir: string }>
      get<T>(path: string): Promise<{ ok: boolean; status: number; body: T }>
      post<T>(path: string, body?: unknown): Promise<{ ok: boolean; status: number; body: T }>
      screenshot(): Promise<void>
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
  const [registrando, setRegistrando] = useState(false)
  const [sessioneCorrente, setSessioneCorrente] = useState<number | null>(null)
  const [sessioneVista, setSessioneVista] = useState<number | null>(null)
  const [sessioni, setSessioni] = useState<Sessione[]>([])
  const [segmenti, setSegmenti] = useState<Segmento[]>([])
  const [scatti, setScatti] = useState<Scatto[]>([])
  const [trascorsi, setTrascorsi] = useState(0)
  const [dialogo, setDialogo] = useState(false)
  const [avviso, setAvviso] = useState<string | null>(null)

  const fine = useRef<HTMLDivElement>(null)
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
        }
      }),

      window.scriba.on('screenshot:ignorato', () =>
        setAvviso('Screenshot non salvato: nessuna registrazione in corso.'),
      ),

      window.scriba.on('hotkey:non-disponibile', (combo: string) =>
        setAvviso(`La scorciatoia ${combo} e' gia' usata da un'altra applicazione.`),
      ),
    ]

    window.scriba.endpoint().then((e) => {
      if (e) {
        setCorePronto(true)
        caricaSessioni()
      }
    })

    return () => off.forEach((f) => f())
  }, [caricaSessioni])

  // Cronometro della registrazione, chiesto al core: e' lui che possiede la
  // timeline, e un contatore locale finirebbe per divergere.
  useEffect(() => {
    if (!registrando) return
    const timer = setInterval(async () => {
      const r = await window.scriba.get<{ now_ms: number }>('/session/state')
      if (r.ok && r.body?.now_ms != null) setTrascorsi(r.body.now_ms)
    }, 1000)
    return () => clearInterval(timer)
  }, [registrando])

  useEffect(() => {
    if (seguiInFondo.current) fine.current?.scrollIntoView({ behavior: 'smooth' })
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

  const apriSessione = async (id: number) => {
    setSessioneVista(id)
    await caricaSegmenti(id)
    setScatti([])
  }

  const righe = useMemo(() => {
    const elementi: Array<{ chiave: string; t: number; nodo: ReactElement }> = []
    for (const s of segmenti) {
      elementi.push({
        chiave: `s${s.id}`,
        t: s.t_start_ms,
        nodo: (
          <div className={`riga ${s.source} ${s.is_final ? '' : 'provvisoria'}`}>
            <span className="tempo">{tempo(s.t_start_ms)}</span>
            <span className="chi">{ETICHETTA[s.source] ?? s.source}</span>
            <span className="testo">{s.testo}</span>
          </div>
        ),
      })
    }
    for (const scatto of scatti) {
      elementi.push({
        chiave: `i${scatto.t_ms}`,
        t: scatto.t_ms,
        nodo: <div className="scatto">Screenshot a {tempo(scatto.t_ms)}</div>,
      })
    }
    return elementi.sort((a, b) => a.t - b.t)
  }, [segmenti, scatti])

  return (
    <div className="app">
      <header className="barra">
        <span className="marchio">Scriba</span>

        {avviso && <div className="avviso">{avviso}</div>}

        <div className="stato">
          <span className={`pallino ${registrando ? 'registra' : corePronto ? 'acceso' : ''}`} />
          {registrando ? 'Registrazione' : corePronto ? 'Pronto' : 'Avvio del core...'}
        </div>

        {registrando && <span className="cronometro">{tempo(trascorsi)}</span>}

        <button onClick={() => window.scriba.screenshot()} disabled={!registrando}>
          Screenshot
        </button>

        {registrando ? (
          <button className="pericolo" onClick={ferma}>
            Ferma
          </button>
        ) : (
          <button className="primario" onClick={() => setDialogo(true)} disabled={!corePronto}>
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
                  <br />
                  Durante la call, <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>S</kbd> cattura uno
                  screenshot e lo aggancia al punto in cui siete.
                </>
              )}
            </div>
          ) : (
            righe.map((r) => <div key={r.chiave}>{r.nodo}</div>)
          )}
          <div ref={fine} />
        </main>
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
