/**
 * Punto di ingresso della finestra delle impostazioni.
 *
 * Sta in un file col nome esteso, e non in `impostazioni.tsx`, per una ragione
 * pratica: NTFS qui non distingue maiuscole e minuscole, quindi
 * `impostazioni.tsx` e `Impostazioni.tsx` sarebbero lo stesso file su disco.
 * Un nome diverso, invece di uno che differisce solo per l'iniziale, evita di
 * dover ricordare questa trappola ogni volta che si tocca la build — e di
 * scoprirla al primo checkout su un filesystem che invece le distingue.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { Impostazioni } from './Impostazioni'
import { ContestoLingua, useLingua } from './lingua'

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
      <Impostazioni />
    </ConLingua>
  </StrictMode>,
)
