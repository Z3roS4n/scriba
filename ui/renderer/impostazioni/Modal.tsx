/**
 * Velo scuro più `.modal`, per le conferme che non possono essere un clic
 * solo — qui serve per "elimina tutto di una call" (istruzioni del task:
 * quale call, poi una conferma scritta).
 *
 * Riusa `--scrim` e le classi di Dialoghi (5) già presenti in app.css:
 * nessuna regola nuova, solo il posizionamento a schermo intero che nel
 * handoff era dato dalla pagina di prova (`.scrimwrap`) e qui va rifatto a
 * mano perché la finestra vera non ha quella cornice.
 */

import type { ReactNode } from 'react'

export function Modal({
  children,
  onChiudi,
  larghezza,
}: {
  children: ReactNode
  onChiudi: () => void
  /**
   * Oltre i 480px del design, per le sole tabelle a due colonne (etichetta più
   * controllo) che a quella larghezza si accavallano — vedi D-UI-06.
   */
  larghezza?: number
}) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'var(--scrim)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
      onClick={onChiudi}
    >
      <div
        className="modal"
        style={larghezza ? { width: larghezza } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}
