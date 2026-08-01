/**
 * Il tema dell'interfaccia: chiaro, scuro, o come il sistema.
 *
 * `tokens.css` ha la palette chiara nel `:root` e quella scura come insieme di
 * sovrascritture sotto `[data-theme="dark"]`. Cambiare tema è quindi
 * un'operazione sola: mettere o togliere quell'attributo sull'elemento radice.
 * Nessun componente sa che esistono due temi, e non deve saperlo.
 *
 * Sta in un file suo perché lo usano tre bundle diversi — finestra principale,
 * impostazioni, overlay — che sono tre processi separati. È anche il motivo per
 * cui esiste l'evento `tema:cambiato`: cambiarlo in una finestra non cambia le
 * altre da sé, e vederne due di colori diversi è peggio che non poterlo
 * cambiare affatto.
 */

import { useEffect, useState } from 'react'

export type Tema = 'sistema' | 'chiaro' | 'scuro'

const CHIARE = ['sistema', 'chiaro', 'scuro'] as const

export function temaValido(valore: unknown): Tema {
  return (CHIARE as readonly string[]).includes(valore as string) ? (valore as Tema) : 'scuro'
}

/** Cosa vuole il sistema operativo adesso. */
function temaDiSistema(): 'chiaro' | 'scuro' {
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'chiaro' : 'scuro'
}

export function risolvi(tema: Tema): 'chiaro' | 'scuro' {
  return tema === 'sistema' ? temaDiSistema() : tema
}

/**
 * Applica il tema al documento.
 *
 * Per il chiaro si scrive `light` invece di togliere l'attributo: togliendolo
 * funzionerebbe lo stesso — solo `[data-theme="dark"]` sovrascrive — ma
 * leggere `data-theme="light"` negli strumenti di sviluppo dice quale tema è
 * attivo, mentre l'assenza dell'attributo non distingue «chiaro» da «nessuno
 * l'ha ancora impostato».
 */
export function applica(tema: Tema): void {
  document.documentElement.setAttribute(
    'data-theme',
    risolvi(tema) === 'chiaro' ? 'light' : 'dark',
  )
}

/**
 * Tiene il documento allineato al tema scelto, ovunque lo si cambi.
 *
 * Il valore iniziale arriva dal ponte, non da `GET /settings`: quello richiede
 * che il core sia già partito, e nel frattempo la finestra sarebbe già visibile
 * con il tema sbagliato.
 */
export function useTema(): Tema {
  const [tema, setTema] = useState<Tema>(() => temaValido(window.scriba.temaIniziale))

  useEffect(() => {
    applica(tema)
  }, [tema])

  useEffect(() => {
    return window.scriba.on('tema:cambiato', (nuovo: unknown) => setTema(temaValido(nuovo)))
  }, [])

  // Con «come il sistema» il tema può cambiare senza che nessuno tocchi
  // Scriba: Windows lo fa da solo al tramonto, se glielo si è chiesto.
  useEffect(() => {
    if (tema !== 'sistema') return
    const query = window.matchMedia('(prefers-color-scheme: light)')
    const alCambio = () => applica('sistema')
    query.addEventListener('change', alCambio)
    return () => query.removeEventListener('change', alCambio)
  }, [tema])

  return tema
}
