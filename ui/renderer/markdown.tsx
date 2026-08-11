/**
 * Il poco Markdown che i modelli scrivono, reso una volta sola.
 *
 * Ce n'erano due copie: una in `Analisi.tsx` per il riassunto, che il
 * grassetto lo faceva, e una in `NotaDiLavoro.tsx` per la nota, che non lo
 * faceva — così nella nota di lavoro si leggevano gli asterischi (#88). Due
 * renderer per lo stesso testo divergono sempre, e a divergere è quello che
 * si guarda meno.
 *
 * Non è un renderer Markdown: è **esattamente** quello che i prompt chiedono
 * di scrivere — titoli, paragrafi, elenchi puntati e numerati, grassetto in
 * linea. Tutto il resto arriva a schermo com'è scritto, che è meglio di un
 * pezzo di sintassi tolto e di un testo che cambia senso. Il contenuto viene
 * da un modello di linguaggio, quindi non gli si concede di produrre HTML.
 */

import { memo, type ReactNode } from 'react'

/** `**così**` diventa grassetto; il resto resta testo. */
export function grassetto(testo: string): ReactNode {
  const pezzi = testo.split(/(\*\*[^*]+\*\*)/g)
  return pezzi.map((p, i) => (p.startsWith('**') && p.endsWith('**') ? <b key={i}>{p.slice(2, -2)}</b> : p))
}

/**
 * Come si chiamano i pezzi.
 *
 * Il riassunto usa `sum__*`, la nota di lavoro `nota__*`: sono due posti
 * dell'interfaccia con due misure diverse, e passarli da fuori evita di
 * dover scegliere quale dei due vince.
 */
export interface ClassiMarkdown {
  /** Il contenitore di un gruppo: un titolo e quello che lo segue. */
  gruppo: string
  paragrafo: string
  elenco: string
  /** Il titolo dentro il gruppo. In mancanza, l'etichetta del sistema. */
  titolo?: string
}

interface Elenco {
  numerato: boolean
  /** Da che numero parte: un «3.» in mezzo a un testo parte da tre. */
  primo: number
  voci: string[]
}

export const Markdown = memo(function Markdown({
  testo,
  classi,
}: {
  testo: string
  classi: ClassiMarkdown
}) {
  const gruppi: ReactNode[][] = [[]]
  let aperto: Elenco | null = null

  const dentro = () => gruppi[gruppi.length - 1]

  const chiudiElenco = () => {
    if (!aperto) return
    const { numerato, primo, voci } = aperto
    aperto = null
    // `ol` e non un numero scritto dentro la voce: l'ordine sta nel tag, e
    // chi legge con uno screen reader sente «elemento 2 di 5» invece di un
    // «2.» che è soltanto testo.
    const Lista = numerato ? 'ol' : 'ul'
    dentro().push(
      <Lista
        key={`l${dentro().length}`}
        className={classi.elenco}
        start={numerato ? primo : undefined}
      >
        {voci.map((v, i) => (
          <li key={i}>{grassetto(v)}</li>
        ))}
      </Lista>,
    )
  }

  const apri = (numerato: boolean, primo: number) => {
    if (aperto && aperto.numerato !== numerato) chiudiElenco()
    if (!aperto) aperto = { numerato, primo, voci: [] }
    return aperto
  }

  for (const riga of testo.split('\n')) {
    const pulita = riga.trim()
    if (!pulita) {
      chiudiElenco()
      continue
    }

    const puntata = pulita.match(/^[-*•]\s+(.*)$/)
    if (puntata) {
      apri(false, 1).voci.push(puntata[1])
      continue
    }
    const numerata = pulita.match(/^(\d+)[.)]\s+(.*)$/)
    if (numerata) {
      apri(true, Number(numerata[1])).voci.push(numerata[2])
      continue
    }

    chiudiElenco()
    const titolo = pulita.match(/^#{1,6}\s+(.*)$/)
    if (titolo) {
      // Un titolo apre un gruppo: è così che il riassunto tiene distanti fra
      // loro le sue sezioni senza margini scritti a mano.
      gruppi.push([
        <h3 key="h" className={classi.titolo ?? 'label'}>
          {titolo[1]}
        </h3>,
      ])
      continue
    }
    dentro().push(
      <p key={`p${dentro().length}`} className={classi.paragrafo}>
        <span>{grassetto(pulita)}</span>
      </p>,
    )
  }
  chiudiElenco()

  return (
    <>
      {gruppi
        .filter((g) => g.length)
        .map((g, i) => (
          <div className={classi.gruppo} key={i}>
            {g}
          </div>
        ))}
    </>
  )
})
