/**
 * Selettore a comparsa: un <button> più un elenco disegnato da noi.
 *
 * Esiste perché il design vieta i controlli di form nativi (comportamento.md,
 * 21), e non è una preferenza estetica: su Windows un `<select>` ignora il
 * tema dell'applicazione e apre un menù **di sistema**, chiaro sopra una
 * finestra scura, con un carattere che non è quello dell'interfaccia. Qui
 * l'elenco è HTML vero, quindi eredita i token come tutto il resto.
 *
 * Stava sotto `impostazioni/`, ma non è roba delle impostazioni: i filtri
 * dell'archivio ne hanno bisogno quanto loro, e tenerne due copie vorrebbe
 * dire vederle divergere alla prima modifica.
 *
 * Il grilletto è un `.filter` — il controllo con cui il design disegna già i
 * filtri dell'archivio — e il menù è **un piano bordato e piatto**: le
 * superfici che galleggiano non hanno ombra, il contenuto sotto si scurisce e
 * basta (regola 19).
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
  larghezza,
}: {
  opzioni: OpzioneSelect[]
  selezionato: string | null
  onScegli: (id: string) => void
  vuoto?: string
  /** Larghezza minima del menù, quando le etichette sono più lunghe del grilletto. */
  larghezza?: number
}) {
  const [aperto, setAperto] = useState(false)
  const contenitore = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!aperto) return
    // Un clic fuori chiude il menù, come farebbe un select vero.
    const chiudiSeFuori = (e: MouseEvent) => {
      if (contenitore.current && !contenitore.current.contains(e.target as Node)) setAperto(false)
    }
    // E Esc pure: chi lo apre per sbaglio deve poterne uscire senza mirare.
    const chiudiSeEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setAperto(false)
      }
    }
    document.addEventListener('mousedown', chiudiSeFuori)
    document.addEventListener('keydown', chiudiSeEsc, true)
    return () => {
      document.removeEventListener('mousedown', chiudiSeFuori)
      document.removeEventListener('keydown', chiudiSeEsc, true)
    }
  }, [aperto])

  const corrente = opzioni.find((o) => o.id === selezionato)

  return (
    <div className="sel" ref={contenitore}>
      {/* Niente `is-on` quando il menù è aperto: in questo sistema `is-on`
          vuol dire «questo filtro sta filtrando», e usarlo per «il menù è
          aperto» faceva ingrassare il testo a ogni clic — due stati diversi
          che si accendevano nello stesso modo. Lo stato aperto lo dice
          `aria-expanded`, che il CSS legge da sé. */}
      <button
        type="button"
        className="filter"
        aria-haspopup="listbox"
        aria-expanded={aperto}
        onClick={() => setAperto((a) => !a)}
      >
        {corrente?.etichetta ?? vuoto}
        <span className="chev chev--down" />
      </button>
      {aperto && (
        <div className="pop" role="listbox" style={larghezza ? { minWidth: larghezza } : undefined}>
          {opzioni.length === 0 ? (
            <div className="pop__vuoto">Nessuna opzione disponibile</div>
          ) : (
            opzioni.map((o) => (
              <button
                key={o.id}
                type="button"
                role="option"
                aria-selected={o.id === selezionato}
                className={`pop__voce${o.id === selezionato ? ' is-on' : ''}`}
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
