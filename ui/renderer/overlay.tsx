/**
 * Contenuto dell'overlay: le ultime righe di trascrizione e i comandi minimi.
 *
 * Sta sopra la finestra della call — niente cornice, sempre in primo piano —
 * quindi il vetro scuro e la sua struttura sono quelli fissati dal handoff
 * (`.overlay`, `.overlay__bar`, `.ovline`...): qui c'è solo la logica che li
 * riempie. Tiene poche righe di proposito: serve a cogliere con la coda
 * dell'occhio cosa è appena stato detto, non a rileggere la riunione.
 */

import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'

import { useSchermi } from './schermi'
import { useTema } from './tema'
import type { Impostazioni, Traccia } from './tipi'
import { scorciatoiaLeggibile, tempo } from './tipi'
import { ContestoLingua, useLingua } from './lingua'
import { useT } from './lingua'

interface Riga {
  chiave: string
  source: Traccia
  t_ms: number
  testo: string
  provvisoria: boolean
}

const CLASSE_PARLANTE: Record<Traccia, string> = { mic: 'ovline--me', loopback: 'ovline--other' }
const MAX_RIGHE_PREDEFINITO = 6
/** Quanto resta visibile «Salvato nella trascrizione»: il tempo di leggerlo di sfuggita. */
const DURATA_FLASH_MS = 2000

/** Una riga di trascrizione, con o senza il minuto (la variante ridotta lo nasconde). */
function LineaOverlay({ riga, conMinuto }: { riga: Riga; conMinuto: boolean }) {
  return (
    <div className={`ovline ${CLASSE_PARLANTE[riga.source]}`}>
      {conMinuto && <span className="ovline__t">{tempo(riga.t_ms)}</span>}
      <span className="ovline__text">
        {riga.provvisoria ? (
          <>
            <span className="is-provisional">{riga.testo}</span>
            <i className="caret" />
          </>
        ) : (
          riga.testo
        )}
      </span>
    </div>
  )
}

function App() {
  const t = useT()
  const [righe, setRighe] = useState<Riga[]>([])
  const [registrando, setRegistrando] = useState(false)
  const [trascorsi, setTrascorsi] = useState(0)
  const [ridotto, setRidotto] = useState(false)
  const schermi = useSchermi()
  // Il tema si applica anche qui, ma **il vetro dell'overlay resta scuro in
  // entrambi**: le sue regole in app.css non usano nessun token di colore, solo
  // misure. Non e' una dimenticanza. Questa striscia sta sopra la finestra di
  // una riunione, spesso a schermo intero e spesso scura: un rettangolo bianco
  // li' sopra e' un abbaglio, e per leggerne due righe con la coda dell'occhio
  // serve il contrario. Il tema serve comunque, perche' `data-theme` resti
  // coerente se un giorno qualcosa qui dentro usasse i colori del prodotto.
  useTema()
  const [scattoRecente, setScattoRecente] = useState(false)
  const [scorciatoie, setScorciatoie] = useState<{ overlay: string | null; screenshot: string | null }>({
    overlay: null,
    screenshot: null,
  })

  const contatore = useRef(0)
  const maxRighe = useRef(MAX_RIGHE_PREDEFINITO)
  const timerFlash = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    // Il tipo dell'evento resta `any`: `EventoCore` è un'unione discriminata con
    // in coda una variante generica (`{ type: string; ... }`) per gli eventi non
    // ancora tipizzati, e quella variante impedisce a TypeScript di restringere
    // i campi anche dentro i rami noti come 'transcript'.
    const off = window.scriba.on('core:event', (ev: any) => {
      if (ev.type === 'transcript') {
        setRighe((prec) => {
          // Un parziale e il suo definitivo sono lo stesso pezzo di parlato: si
          // sostituisce la riga invece di accodarne un'altra, e la chiave resta
          // la stessa — altrimenti la riga si smonta e rimonta e la lista salta.
          const i = prec.findIndex((r) => r.provvisoria && r.source === ev.source)
          // Definitivo senza testo: la frase si è chiusa senza produrre
          // niente. Si toglie la riga provvisoria invece di lasciarla lì
          // vuota a occupare una delle poche righe dell'overlay.
          if (ev.is_final && !ev.text) return i < 0 ? prec : prec.filter((_, k) => k !== i)
          const riga: Riga = {
            chiave: i >= 0 ? prec[i].chiave : `r${contatore.current++}`,
            source: ev.source,
            t_ms: ev.t_start_ms,
            testo: ev.text,
            provvisoria: !ev.is_final,
          }
          const aggiornate = i >= 0 ? prec.map((r, k) => (k === i ? riga : r)) : [...prec, riga]
          return aggiornate.slice(-maxRighe.current)
        })
      } else if (ev.type === 'session_started') {
        setRegistrando(true)
        setRighe([])
      } else if (ev.type === 'session_stopped') {
        setRegistrando(false)
      } else if (ev.type === 'screenshot') {
        // Arriva per qualunque scatto, non solo quelli presi da qui: la
        // conferma è dello stesso tipo ovunque sia partito il comando.
        setScattoRecente(true)
        clearTimeout(timerFlash.current)
        timerFlash.current = setTimeout(() => setScattoRecente(false), DURATA_FLASH_MS)
      }
    })

    window.scriba.get<{ in_registrazione: boolean }>('/session/state').then((r) => {
      if (r.ok) setRegistrando(Boolean(r.body?.in_registrazione))
    })

    // La variante ridotta è una preferenza salvata, non uno stato che nasce qui:
    // si legge da dove la scrive anche la finestra delle impostazioni. Le
    // scorciatoie mostrate quando non si registra vengono da lì per lo stesso
    // motivo — scriverle a mano le farebbe divergere alla prima modifica.
    window.scriba.get<Impostazioni>('/settings').then((r) => {
      if (!r.ok) return
      setRidotto(Boolean(r.body?.interfaccia?.overlay_ridotto))
      if (r.body?.interfaccia?.righe_overlay) maxRighe.current = r.body.interfaccia.righe_overlay
      setScorciatoie({
        overlay: r.body?.interfaccia?.scorciatoia_overlay ?? null,
        screenshot: r.body?.interfaccia?.scorciatoia_screenshot ?? null,
      })
    })

    return () => {
      off()
      clearTimeout(timerFlash.current)
    }
  }, [])

  useEffect(() => {
    if (!registrando) return
    const timer = setInterval(async () => {
      const r = await window.scriba.get<{ now_ms: number }>('/session/state')
      if (r.ok && r.body?.now_ms != null) setTrascorsi(r.body.now_ms)
    }, 1000)
    return () => clearInterval(timer)
  }, [registrando])

  const scatta = (idSchermo?: string) => window.scriba.screenshot(idSchermo)
  const ferma = () => window.scriba.post('/session/stop')
  // Dall'overlay non si salta il consenso: si apre la finestra grande, dove la
  // conferma c'è. Registrare altre persone non è un gesto da un clic dentro una
  // striscia senza cornice.
  const apriPrincipale = () => window.scriba.overlay.apriPrincipale()
  const nascondi = () => window.scriba.overlay.nascondi()

  /**
   * Passa fra striscia intera e variante ridotta.
   *
   * Sta sul pulsante ▢ e non su un doppio clic sulla barra: la barra è zona di
   * trascinamento (`-webkit-app-region: drag`) e dentro Electron una zona di
   * trascinamento non riceve eventi del mouse, quindi quel doppio clic non
   * sarebbe mai arrivato — un comando che sembra esserci e non risponde.
   *
   * Nel design ▢ si chiama «Ingrandisci» ed è l'unico comando che, su una
   * striscia da 420 px, può volere dire quello. La finestra grande resta
   * raggiungibile dall'area di notifica, dove il comando c'è già.
   */
  const alternaRidotto = async () => {
    const nuovo = await window.scriba.overlay.alternaRidotto()
    setRidotto(nuovo)
  }

  const righeMostrate = ridotto ? righe.slice(-2) : righe

  return (
    <div className={`overlay ${registrando ? 'is-recording' : ''} ${ridotto ? 'overlay--mini' : ''}`.trim()}>
      <div className="overlay__bar">
        <i className="overlay__dot" />
        {registrando ? (
          <span className="overlay__timer">{tempo(trascorsi)}</span>
        ) : (
          <span style={{ fontSize: 'var(--fs-md)' }}>Scriba</span>
        )}
        {scattoRecente && <span className="overlay__flash">{t('ovl.salvato')}</span>}
        <div className="overlay__spacer" />
        {registrando ? (
          ridotto ? (
            <>
              {/* Nella striscia ridotta resta un pulsante solo, sul principale:
                  sono 420 px, e riempirli di numeri toglierebbe spazio proprio
                  alla trascrizione, che è il motivo per cui la striscia esiste. */}
              <button className="ovbtn ovbtn--icon" aria-label="Scatta" onClick={() => scatta()}>
                ◎
              </button>
              <button className="ovbtn ovbtn--icon" aria-label="Ferma" onClick={ferma}>
                ■
              </button>
              <button className="ovbtn ovbtn--icon" aria-label="Ingrandisci la striscia" onClick={alternaRidotto}>
                ▢
              </button>
              <button className="ovbtn ovbtn--icon" aria-label="Chiudi" onClick={nascondi}>
                ✕
              </button>
            </>
          ) : (
            <>
              {/* Qui lo spazio c'è: con più schermi si scatta quello giusto
                  senza uscire dalla call per cercare una finestra. */}
              {schermi.length <= 1 ? (
                <button className="ovbtn" onClick={() => scatta()}>
                  {t('ovl.scatta')}
                </button>
              ) : (
                schermi.map((s, i) => (
                  <button
                    key={s.id}
                    className="ovbtn"
                    title={`${s.etichetta} — ${s.larghezza}×${s.altezza}${s.principale ? ' (principale)' : ''}`}
                    onClick={() => scatta(s.id)}
                  >
                    Scatta {i + 1}
                  </button>
                ))
              )}
              <button className="ovbtn ovbtn--stop" onClick={ferma}>
                {t('ovl.ferma')}
              </button>
              <button className="ovbtn ovbtn--icon" aria-label="Riduci la striscia" onClick={alternaRidotto}>
                ▢
              </button>
              <button className="ovbtn ovbtn--icon" aria-label="Chiudi" onClick={nascondi}>
                ✕
              </button>
            </>
          )
        ) : (
          <>
            <button className="ovbtn ovbtn--stop" onClick={apriPrincipale}>
              {t('ovl.registra')}
            </button>
            <button className="ovbtn ovbtn--icon" aria-label="Chiudi" onClick={nascondi}>
              ✕
            </button>
          </>
        )}
      </div>

      {registrando ? (
        scattoRecente && !ridotto ? (
          <div className="overlay__shot">
            <i />
            <span>{t('ovl.scatto_nota')}</span>
          </div>
        ) : (
          <div className="overlay__lines">
            {righeMostrate.map((r) => (
              <LineaOverlay key={r.chiave} riga={r} conMinuto={!ridotto} />
            ))}
          </div>
        )
      ) : (
        <div className="overlay__empty">
          <span>{t('ovl.fermo')}</span>
          <small>
            {scorciatoiaLeggibile(scorciatoie.overlay)} nasconde · {scorciatoiaLeggibile(scorciatoie.screenshot)}{' '}
            scatta
          </small>
        </div>
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
  <ConLingua>
    <App />
  </ConLingua>,
)
