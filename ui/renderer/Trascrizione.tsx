/**
 * Colonna centrale: la trascrizione. Non si restringe mai — vedi comportamento.md
 * punto 3 — perche' e' il posto dove ogni prova, di una task o di un riassunto, si
 * verifica leggendo davvero cosa e' stato detto.
 *
 * Espone `vaiA` tramite ref: e' cosi' che il pannello analisi, il pannello prove e
 * la rassegna task portano al minuto giusto senza che questo componente debba
 * conoscere nulla di loro.
 */

import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from 'react'

import { tempo, type Scatto, type Segmento, type Sessione } from './tipi'

export interface TrascrizioneHandle {
  /** Scorre alla riga del minuto indicato e la fa lampeggiare una volta. */
  vaiA: (t_ms: number) => void
}

const ETICHETTA: Record<Segmento['source'], string> = { mic: 'Io', loopback: 'Altri' }

/**
 * Una riga di parlato. Memoizzata perche' durante una call arriva un evento al
 * secondo per traccia e le righe gia' definitive non cambiano piu': senza,
 * un'ora di call ricostruirebbe centinaia di righe a ogni parola nuova.
 */
const Riga = memo(function Riga({ s, citata }: { s: Segmento; citata: boolean }) {
  return (
    // data-t serve a ritrovare la riga quando si clicca un minuto altrove nella finestra.
    <div
      className={`line ${s.source === 'mic' ? 'line--me' : 'line--other'} ${citata ? 'is-cited' : ''}`}
      data-t={s.t_start_ms}
    >
      <span className="line__t">{tempo(s.t_start_ms)}</span>
      <span className="line__who">{ETICHETTA[s.source]}</span>
      {/* Provvisorio: colore fioco, MAI corsivo (rallenta la lettura periferica). Alla
          chiusura della frase si toglie solo la classe, la riga non si smonta. */}
      <span className={`line__text ${s.is_final ? '' : 'is-provisional'}`}>
        {s.testo}
        {!s.is_final && <i className="caret" />}
      </span>
    </div>
  )
})

const RigaScatto = memo(function RigaScatto({
  s,
  onApri,
}: {
  s: Scatto
  onApri: (percorso: string) => void
}) {
  return (
    <div className="shot" data-t={s.t_ms}>
      <span className="shot__t">{tempo(s.t_ms)}</span>
      <div>
        <div className="shot__frame" onClick={() => onApri(s.path)}>
          screenshot {s.width && s.height ? `${s.width}×${s.height}` : ''}
        </div>
        <span className="shot__cap">Schermata condivisa · clicca per aprirla</span>
      </div>
    </div>
  )
})

/** «12 ago»: il giorno da solo, senza l'ora. dataBreve() di tipi.ts la include
 * sempre, ma qui accanto ci va la durata della call, non l'orario di inizio. */
function giornoBreve(epochMs: number): string {
  const d = new Date(epochMs)
  const oggi = new Date()
  const stessoGiorno =
    d.getFullYear() === oggi.getFullYear() &&
    d.getMonth() === oggi.getMonth() &&
    d.getDate() === oggi.getDate()
  return stessoGiorno
    ? 'oggi'
    : d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' }).replace('.', '')
}

export const Trascrizione = forwardRef<
  TrascrizioneHandle,
  {
    sessione: Sessione | null
    segmenti: Segmento[]
    scatti: Scatto[]
    /** true quando questa e' proprio la call che si sta registrando adesso. */
    inDiretta: boolean
    /** i minuti (t_start_ms) citati dalla task aperta nel pannello analisi. */
    citate: number[]
    /** scorciatoia della striscia, gia' leggibile ("Alt + R"): solo per il suggerimento a finestra vuota. */
    scorciatoiaStriscia: string | null
    onRegistra: () => void
    onApriScatto: (percorso: string) => void
  }
>(function Trascrizione(props, ref) {
  const { sessione, segmenti, scatti, inDiretta, citate, scorciatoiaStriscia, onRegistra, onApriScatto } =
    props

  const corpo = useRef<HTMLDivElement>(null)
  const fine = useRef<HTMLDivElement>(null)
  const conteggioPrec = useRef(0)

  // L'inseguimento del parlato si sospende quando l'utente scorre indietro, e lo
  // riattiva solo il clic su ".jump": nessun altro evento lo fa, altrimenti si
  // strapperebbe la vista a chi sta rileggendo un punto passato.
  const seguiInFondo = useRef(true)
  const [sospesa, setSospesa] = useState(false)
  const [righeNuove, setRigheNuove] = useState(0)

  const citateSet = useMemo(() => new Set(citate), [citate])

  const righe = useMemo(() => {
    const elementi: Array<{ chiave: string; t: number; seg?: Segmento; scatto?: Scatto }> = [
      ...segmenti.map((s) => ({ chiave: `s${s.id}`, t: s.t_start_ms, seg: s })),
      ...scatti.map((s) => ({ chiave: `i${s.id}`, t: s.t_ms, scatto: s })),
    ]
    return elementi.sort((a, b) => a.t - b.t)
  }, [segmenti, scatti])

  const vaiA = useCallback((t_ms: number) => {
    const el = corpo.current
    if (!el) return
    seguiInFondo.current = false
    setSospesa(true)
    const righeEl = Array.from(el.querySelectorAll<HTMLElement>('[data-t]'))
    const bersaglio = righeEl.find((r) => Number(r.dataset.t) >= t_ms) ?? righeEl[righeEl.length - 1]
    if (!bersaglio) return
    bersaglio.scrollIntoView({ block: 'center', behavior: 'smooth' })
    // Rimossa a fine animazione (flashLine, 1,1s): altrimenti un secondo clic
    // sulla stessa riga non lampeggia perche' la classe c'e' gia'.
    bersaglio.classList.add('is-flashing')
    window.setTimeout(() => bersaglio.classList.remove('is-flashing'), 1100)
  }, [])

  useImperativeHandle(ref, () => ({ vaiA }), [vaiA])

  const onClickMinuto = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      const t = (e.target as HTMLElement).closest('.line__t')
      if (!t) return
      const riga = t.closest<HTMLElement>('[data-t]')
      if (riga) vaiA(Number(riga.dataset.t))
    },
    [vaiA],
  )

  const onScroll = useCallback(() => {
    if (!seguiInFondo.current) return // gia' sospeso: si riattiva solo dal pulsante
    const el = corpo.current
    if (!el) return
    const distanzaDalFondo = el.scrollHeight - el.scrollTop - el.clientHeight
    if (distanzaDalFondo > 48) {
      seguiInFondo.current = false
      setSospesa(true)
    }
  }, [])

  const tornaAlPresente = useCallback(() => {
    seguiInFondo.current = true
    setSospesa(false)
    setRigheNuove(0)
    fine.current?.scrollIntoView({ block: 'end' })
  }, [])

  // Cambiando call si riparte da capo: si insegue di nuovo il fondo (che per una
  // call gia' finita coincide con l'ultima riga) e si azzera il conteggio.
  useEffect(() => {
    seguiInFondo.current = true
    setSospesa(false)
    setRigheNuove(0)
    conteggioPrec.current = 0
  }, [sessione?.id])

  useEffect(() => {
    const delta = righe.length - conteggioPrec.current
    conteggioPrec.current = righe.length
    if (seguiInFondo.current) {
      // Istantaneo, non animato: durante una call arriva un evento al secondo
      // per traccia e le animazioni si accavallerebbero.
      fine.current?.scrollIntoView({ block: 'end' })
    } else if (delta > 0) {
      setRigheNuove((n) => n + delta)
    }
  }, [righe])

  if (!sessione) {
    return (
      <main className="transcript">
        <div className="transcript__head">
          <span className="transcript__title">Nessuna call</span>
        </div>
        <div className="state">
          <div className="state__ph" />
          <div>
            <p className="state__title">Non hai ancora registrato niente</p>
            <p className="state__body" style={{ marginTop: 'var(--sp-2)' }}>
              Avvia la registrazione quando entri in una call. Sentirai il tuo microfono e l’audio del
              computer, così la trascrizione contiene tutti.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-4)' }}>
            <button className="btn btn--rec" onClick={onRegistra}>
              Registra
            </button>
            {scorciatoiaStriscia && (
              <span className="state__hint">oppure {scorciatoiaStriscia} per la striscia</span>
            )}
          </div>
        </div>
      </main>
    )
  }

  const titolo = sessione.titolo || `Call #${sessione.id}`
  const meta = inDiretta
    ? 'in corso'
    : `${giornoBreve(sessione.started_at)} · ${tempo(sessione.durata_ms ?? 0)}`

  return (
    <main className="transcript">
      <div className="transcript__head">
        <span className="transcript__title">{titolo}</span>
        <span className="transcript__meta">{meta}</span>
        <span className="legend">
          <i className="me" />Io<i className="other" />Altri
        </span>
      </div>

      {righe.length === 0 && inDiretta ? (
        <div className="state">
          <div className="meter">
            {[8, 14, 6, 11, 5, 9, 13, 7, 10].map((h, i) => (
              <i key={i} style={{ height: h }} />
            ))}
          </div>
          <p style={{ fontSize: 'var(--fs-line)', color: 'var(--fg2)' }}>
            In ascolto. Nessuno ha ancora parlato.
          </p>
        </div>
      ) : righe.length === 0 ? (
        <div className="state">
          <p className="state__body">Nessuna trascrizione per questa call.</p>
        </div>
      ) : (
        <div className="transcript__body" ref={corpo} onScroll={onScroll} onClick={onClickMinuto}>
          {righe.map((r) =>
            r.seg ? (
              <Riga key={r.chiave} s={r.seg} citata={citateSet.has(r.seg.t_start_ms)} />
            ) : (
              <RigaScatto key={r.chiave} s={r.scatto as Scatto} onApri={onApriScatto} />
            ),
          )}
          <div ref={fine} />
        </div>
      )}

      {/* Fratello del corpo, non figlio: `.jump` e' in posizione assoluta dentro
          `.transcript`, e messo dentro il contenitore che scorre verrebbe
          ritagliato dal suo overflow. Compare solo a inseguimento sospeso —
          questo clic e' l'unico modo per farlo ripartire. */}
      {sospesa && righe.length > 0 && (
        <div className="jump">
          <button className="btn" onClick={tornaAlPresente}>
            Torna al presente · {righeNuove === 1 ? '1 riga nuova' : `${righeNuove} righe nuove`}
          </button>
        </div>
      )}
    </main>
  )
})
