/**
 * Contenuto dell'overlay: le ultime righe di trascrizione e i comandi minimi.
 *
 * Tiene poche righe di proposito. Sta sopra la finestra della call, e una
 * finestra che cresce copre quello che si sta guardando: serve a cogliere con
 * la coda dell'occhio cosa e' appena stato detto, non a rileggere la riunione.
 */

import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'

interface Riga {
  chiave: string
  source: 'mic' | 'loopback'
  testo: string
  provvisoria: boolean
}

const ETICHETTA: Record<string, string> = { mic: 'Io', loopback: 'Altri' }
const MAX_RIGHE = 6

function tempo(ms: number): string {
  const t = Math.max(0, Math.floor(ms / 1000))
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
}

function App() {
  const [righe, setRighe] = useState<Riga[]>([])
  const [registrando, setRegistrando] = useState(false)
  const [pronto, setPronto] = useState(false)
  const [trascorsi, setTrascorsi] = useState(0)
  const contatore = useRef(0)

  useEffect(() => {
    const off = window.scriba.on('core:event', (ev: any) => {
      if (ev.type === 'transcript') {
        setRighe((prec) => {
          // Un parziale e il suo definitivo sono lo stesso pezzo di parlato: si
          // sostituisce la riga invece di accodarne un'altra.
          const i = prec.findIndex((r) => r.provvisoria && r.source === ev.source)
          const riga: Riga = {
            chiave: i >= 0 ? prec[i].chiave : `r${contatore.current++}`,
            source: ev.source,
            testo: ev.text,
            provvisoria: !ev.is_final,
          }
          const aggiornate = i >= 0 ? prec.map((r, k) => (k === i ? riga : r)) : [...prec, riga]
          return aggiornate.slice(-MAX_RIGHE)
        })
      } else if (ev.type === 'session_started') {
        setRegistrando(true)
        setRighe([])
      } else if (ev.type === 'session_stopped') {
        setRegistrando(false)
      }
    })

    window.scriba.get<{ in_registrazione: boolean }>('/session/state').then((r) => {
      if (r.ok) setRegistrando(Boolean(r.body?.in_registrazione))
    })
    window.scriba.get<{ modello: string }>('/health').then((r) => {
      if (r.ok) setPronto(r.body?.modello === 'pronto')
    })

    return off
  }, [])

  useEffect(() => {
    if (!registrando) return
    const timer = setInterval(async () => {
      const r = await window.scriba.get<{ now_ms: number }>('/session/state')
      if (r.ok && r.body?.now_ms != null) setTrascorsi(r.body.now_ms)
    }, 1000)
    return () => clearInterval(timer)
  }, [registrando])

  const avvia = async () => {
    // Dall'overlay non si salta il consenso: si apre la finestra grande, dove
    // la conferma c'e'. Registrare altre persone non e' un gesto da un clic
    // dentro una striscia senza cornice.
    window.scriba.overlay.apriPrincipale()
  }

  const ferma = () => window.scriba.post('/session/stop')

  return (
    <div className="guscio">
      <div className="testa">
        <span className={`spia ${registrando ? 'registra' : pronto ? 'pronto' : ''}`} />
        <span className="tempo">{registrando ? tempo(trascorsi) : 'Scriba'}</span>

        <button onClick={() => window.scriba.screenshot()} disabled={!registrando} title="Screenshot">
          Scatta
        </button>
        {registrando ? (
          <button className="rec" onClick={ferma}>
            Ferma
          </button>
        ) : (
          <button onClick={avvia}>Registra</button>
        )}
        <button
          className="icona"
          onClick={() => window.scriba.overlay.apriPrincipale()}
          title="Apri la finestra principale"
        >
          ⤢
        </button>
        <button className="icona" onClick={() => window.scriba.overlay.nascondi()} title="Nascondi">
          ✕
        </button>
      </div>

      <div className="righe">
        {righe.length === 0 ? (
          <div className="vuoto">
            {registrando ? (
              'In ascolto…'
            ) : (
              <>
                Nessuna registrazione in corso.
                <br />
                <kbd>Alt</kbd> + <kbd>R</kbd> per nascondere questa striscia.
              </>
            )}
          </div>
        ) : (
          righe.map((r, i) => (
            <div
              key={r.chiave}
              className={`riga ${r.source} ${r.provvisoria ? 'provvisoria' : ''} ${
                i < righe.length - 3 ? 'vecchia' : ''
              }`}
            >
              <span className="chi">{ETICHETTA[r.source] ?? r.source}</span>
              <span className="testo">{r.testo}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
