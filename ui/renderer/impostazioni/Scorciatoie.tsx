/**
 * Scorciatoie: si premono, non si scrivono.
 *
 * Windows rifiuta in silenzio una combinazione già presa da un'altra
 * applicazione: il vecchio Impostazioni.tsx esisteva apposta per riferire
 * quell'esito, e questa versione tiene lo stesso comportamento — solo con
 * la cattura dei tasti al posto di un campo di testo. `provaScorciatoia` dà
 * il responso immediato mentre si preme; `registraScorciatoie`, chiamato
 * dopo il salvataggio, dice cosa è davvero rimasto attivo.
 */

import { useState } from 'react'
import type { KeyboardEvent as TastoEvento } from 'react'

import type { Impostazioni } from '../tipi'
import { scorciatoiaLeggibile } from '../tipi'
import { useT } from '../lingua'

const PREDEFINITE: Record<Voce['chiave'], string> = {
  scorciatoia_overlay: 'Alt+R',
  scorciatoia_screenshot: 'CommandOrControl+Shift+S',
}

interface Voce {
  chiave: 'scorciatoia_overlay' | 'scorciatoia_screenshot'
  nome: string
}

const VOCI: Voce[] = [
  { chiave: 'scorciatoia_overlay', nome: 'Mostra e nascondi la striscia' },
  { chiave: 'scorciatoia_screenshot', nome: 'Scatta uno screenshot' },
]

/** Tasti il cui `KeyboardEvent.key` non coincide col nome che vuole Electron. */
const MAPPA_TASTI: Record<string, string> = {
  ' ': 'Space',
  ArrowUp: 'Up',
  ArrowDown: 'Down',
  ArrowLeft: 'Left',
  ArrowRight: 'Right',
  Escape: 'Esc',
}

/** Traduce l'evento nel formato di Electron (`Alt+R`, `CommandOrControl+Shift+S`). */
function combinazioneDaEvento(e: TastoEvento<HTMLButtonElement>): string | null {
  const { key } = e
  if (key === 'Control' || key === 'Alt' || key === 'Shift' || key === 'Meta') return null

  const parti: string[] = []
  if (e.ctrlKey) parti.push('CommandOrControl')
  if (e.altKey) parti.push('Alt')
  if (e.shiftKey) parti.push('Shift')
  if (e.metaKey) parti.push('Super')
  parti.push(MAPPA_TASTI[key] ?? (key.length === 1 ? key.toUpperCase() : key))
  return parti.join('+')
}

export function SezioneScorciatoie({
  impostazioni,
  onCambia,
}: {
  impostazioni: Impostazioni
  onCambia: (patch: Partial<Impostazioni>) => Promise<boolean>
}) {
  const t = useT()
  const [catturando, setCatturando] = useState<Voce['chiave'] | null>(null)
  const [conflitti, setConflitti] = useState<Partial<Record<Voce['chiave'], boolean>>>({})

  const applica = async (chiave: Voce['chiave'], combinazione: string) => {
    setCatturando(null)

    // Risposta immediata: senza aspettare il giro di salvataggio, perché
    // Windows rifiuta in silenzio e l'utente deve saperlo subito.
    const provaOk = await window.scriba.provaScorciatoia(combinazione)
    setConflitti((c) => ({ ...c, [chiave]: !provaOk }))

    await onCambia({ interfaccia: { ...impostazioni.interfaccia, [chiave]: combinazione } })

    // Riconferma con quello che è rimasto davvero registrato: due scorciatoie
    // potrebbero competere fra loro, e solo `registraScorciatoie` lo sa.
    const registrate = await window.scriba.registraScorciatoie()
    const attiva = chiave === 'scorciatoia_overlay' ? registrate.overlay : registrate.screenshot
    setConflitti((c) => ({ ...c, [chiave]: attiva !== combinazione }))
  }

  const cattura = (chiave: Voce['chiave']) => (e: TastoEvento<HTMLButtonElement>) => {
    e.preventDefault()
    const combinazione = combinazioneDaEvento(e)
    if (combinazione) applica(chiave, combinazione)
  }

  return (
    <>
      <div className="settings__head">{t('sco.titolo')}</div>
      <div className="settings__body">
        <p>
          {t('sco.titolo_nota')}
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
          {VOCI.map((v) => {
            const valore = impostazioni.interfaccia[v.chiave]
            const inConflitto = Boolean(conflitti[v.chiave])
            return (
              <div key={v.chiave} className={`shortcut ${inConflitto ? 'has-conflict' : ''}`}>
                <div className="shortcut__top">
                  <span className="shortcut__name">{v.nome}</span>
                  <button
                    className={`keycap ${catturando === v.chiave ? 'is-capturing' : ''}`}
                    onClick={(e) => {
                      setCatturando(v.chiave)
                      e.currentTarget.focus()
                    }}
                    onBlur={() => setCatturando((c) => (c === v.chiave ? null : c))}
                    onKeyDown={catturando === v.chiave ? cattura(v.chiave) : undefined}
                  >
                    {catturando === v.chiave ? 'Premi i tasti…' : scorciatoiaLeggibile(valore)}
                  </button>
                  <button className="btn btn--sm" onClick={() => applica(v.chiave, PREDEFINITE[v.chiave])}>
                    {t('sco.ripristina')}
                  </button>
                </div>
                {inConflitto && (
                  <p className="shortcut__conflict">
                    {t('sco.gia_usata')}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </>
  )
}
