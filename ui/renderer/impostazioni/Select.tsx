/**
 * Selettore a comparsa: sembra un controllo nativo ma è un <button> più un
 * elenco disegnato da noi.
 *
 * Su Windows i <select> nativi ignorano il tema scuro (comportamento.md,
 * punto 10): qui l'elenco è HTML vero, quindi eredita i token di tema come
 * tutto il resto della finestra.
 */

import { useEffect, useRef, useState } from 'react'

export interface OpzioneSelect {
  id: string
  etichetta: string
}

export function Select({
  opzioni,
  selezionato,
  onScegli,
  vuoto = '—',
}: {
  opzioni: OpzioneSelect[]
  selezionato: string | null
  onScegli: (id: string) => void
  vuoto?: string
}) {
  const [aperto, setAperto] = useState(false)
  const contenitore = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!aperto) return
    // Un clic fuori chiude il menù, come un <select> vero farebbe.
    const chiudiSeFuori = (e: MouseEvent) => {
      if (contenitore.current && !contenitore.current.contains(e.target as Node)) setAperto(false)
    }
    document.addEventListener('mousedown', chiudiSeFuori)
    return () => document.removeEventListener('mousedown', chiudiSeFuori)
  }, [aperto])

  const corrente = opzioni.find((o) => o.id === selezionato)

  return (
    <div style={{ position: 'relative' }} ref={contenitore}>
      <button
        type="button"
        className="select"
        aria-haspopup="listbox"
        aria-expanded={aperto}
        onClick={() => setAperto((a) => !a)}
      >
        {corrente?.etichetta ?? vuoto}
        <svg width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="var(--fg5)" strokeWidth="1.5">
          <path d="M1 3.2 5 7l4-3.8" />
        </svg>
      </button>
      {aperto && (
        <div
          role="listbox"
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            minWidth: 200,
            zIndex: 20,
            background: 'var(--win)',
            border: '1px solid var(--line2)',
            borderRadius: 'var(--r-2)',
            boxShadow: 'var(--shadow-pop)',
            padding: 4,
            maxHeight: 260,
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 1,
          }}
        >
          {opzioni.length === 0 ? (
            <div style={{ padding: '9px 13px', fontSize: 'var(--fs-sm)', color: 'var(--fg5)' }}>
              Nessuna opzione disponibile
            </div>
          ) : (
            opzioni.map((o) => (
              <button
                key={o.id}
                type="button"
                role="option"
                aria-selected={o.id === selezionato}
                className="btn btn--block"
                style={o.id === selezionato ? { background: 'var(--sel)', fontWeight: 600 } : undefined}
                onClick={() => {
                  onScegli(o.id)
                  setAperto(false)
                }}
              >
                {o.etichetta}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
