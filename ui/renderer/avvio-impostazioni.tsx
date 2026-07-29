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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Impostazioni />
  </StrictMode>,
)
