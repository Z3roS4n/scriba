/**
 * Gli schermi collegati, tenuti aggiornati.
 *
 * Sta in un file suo perche' lo usano due bundle diversi — la finestra
 * principale e l'overlay — e sono due processi separati che non condividono
 * stato: l'unico modo di tenerli d'accordo e' che chiedano la stessa cosa allo
 * stesso posto.
 *
 * L'elenco cambia mentre l'app gira: ci si collega a una dock, si attacca un
 * proiettore per la riunione. Senza l'ascolto dell'evento, i pulsanti
 * resterebbero quelli dell'avvio e uno di loro chiederebbe di catturare uno
 * schermo che non c'e' piu'.
 */

import { useEffect, useState } from 'react'

import type { Schermo } from './scriba'

export function useSchermi(): Schermo[] {
  const [schermi, setSchermi] = useState<Schermo[]>([])

  useEffect(() => {
    let vivo = true
    window.scriba.schermi().then((elenco) => {
      if (vivo) setSchermi(elenco)
    })
    const disiscrivi = window.scriba.on('schermi:cambiati', (elenco: Schermo[]) => {
      setSchermi(elenco)
    })
    return () => {
      vivo = false
      disiscrivi()
    }
  }, [])

  return schermi
}
