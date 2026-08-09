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
import { etichettaValore, useT } from '../lingua'

const PREDEFINITE: Record<(typeof VOCI)[number], string> = {
  scorciatoia_overlay: 'Alt+R',
  scorciatoia_screenshot: 'CommandOrControl+Shift+S',
}

const VOCI = ['scorciatoia_overlay', 'scorciatoia_screenshot'] as const

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
  const [catturando, setCatturando] = useState<(typeof VOCI)[number] | null>(null)
  const [conflitti, setConflitti] = useState<Partial<Record<(typeof VOCI)[number], boolean>>>({})

  const applica = async (chiave: (typeof VOCI)[number], combinazione: string) => {
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

  const cattura = (chiave: (typeof VOCI)[number]) => (e: TastoEvento<HTMLButtonElement>) => {
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
          {VOCI.map((chiave) => {
            const valore = impostazioni.interfaccia[chiave]
            const inConflitto = Boolean(conflitti[chiave])
            return (
              <div key={chiave} className={`shortcut ${inConflitto ? 'has-conflict' : ''}`}>
                <div className="shortcut__top">
                  <span className="shortcut__name">{etichettaValore(t, 'sco_nome', chiave)}</span>
                  <button
                    className={`keycap ${catturando === chiave ? 'is-capturing' : ''}`}
                    onClick={(e) => {
                      setCatturando(chiave)
                      e.currentTarget.focus()
                    }}
                    onBlur={() => setCatturando((c) => (c === chiave ? null : c))}
                    onKeyDown={catturando === chiave ? cattura(chiave) : undefined}
                  >
                    {catturando === chiave ? t('sco2.premi') : scorciatoiaLeggibile(valore)}
                  </button>
                  <button className="btn btn--sm" onClick={() => applica(chiave, PREDEFINITE[chiave])}>
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
