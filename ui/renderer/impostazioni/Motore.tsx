/**
 * Scelta del motore che analizza le call.
 *
 * La conseguenza — «la trascrizione viene inviata a…» — va mostrata anche
 * sull'opzione già in uso: è quella che si dimentica più facilmente
 * (comportamento.md, punto 6; contratto-api.md la fa arrivare come
 * `esce_dal_computer` invece di scriverla a mano qui).
 */

import { useState } from 'react'

import type { Provider } from '../tipi'
import { useT } from '../lingua'

/** A chi va la trascrizione, per completare la frase del rischio. Il core dice
 *  solo *se* esce (`esce_dal_computer`), non *a chi*: il nome del fornitore
 *  non è nella forma di Provider, quindi si ricava dall'id conosciuto. */
const DESTINAZIONE: Record<string, string> = {
  anthropic: 'Anthropic',
  'claude-cli': 'Anthropic',
  openai: 'OpenAI',
}

export function SezioneMotore({
  providers,
  onScegli,
  onSalvaChiave,
}: {
  providers: Provider[]
  onScegli: (p: Provider) => void
  onSalvaChiave: (p: Provider, chiave: string) => Promise<boolean>
}) {
  const t = useT()
  const [inserendo, setInserendo] = useState<string | null>(null)
  const [chiave, setChiave] = useState('')
  const [salvando, setSalvando] = useState(false)

  const salva = async (p: Provider) => {
    if (!chiave.trim()) return
    setSalvando(true)
    const ok = await onSalvaChiave(p, chiave.trim())
    setSalvando(false)
    if (ok) {
      setInserendo(null)
      setChiave('')
    }
  }

  return (
    <>
      <div className="settings__head">{t('mot.titolo')}</div>
      <div className="settings__body">
        <p>{t('mot.titolo_nota')}</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
          {providers.map((p) => {
            // Non c'è un campo dedicato per "manca la chiave": si deduce dal
            // testo del rimedio, come faceva la versione precedente di questo
            // dialogo con la sua mappa RIMEDIO cablata per id.
            const chiedeChiave = !p.disponibile && /chiave/i.test(p.rimedio ?? '')

            return (
              <div
                key={p.id}
                className={`engine ${p.attivo ? 'is-selected' : ''}`}
                onClick={() => {
                  if (p.disponibile && !p.attivo) onScegli(p)
                }}
              >
                <div className="engine__top">
                  <span className="radio">{p.attivo && <i />}</span>
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
                    <span className="engine__name">{p.etichetta}</span>
                    <span className="engine__desc">{p.descrizione}</span>
                    {p.minuti_per_ora != null && (
                      <span className="engine__speed">{t('mot2.velocita', { n: p.minuti_per_ora })}</span>
                    )}
                  </div>
                  <span className={`engine__state ${p.disponibile ? 'is-ok' : ''}`}>
                    {p.attivo
                      ? 'In uso'
                      : p.disponibile
                        ? 'Pronto'
                        : p.in_avvio
                          ? 'In avvio…'
                          : chiedeChiave
                            ? 'Chiave mancante'
                            : t('mot2.non_disponibile')}
                  </span>
                </div>

                {p.in_avvio && (
                  <div className="engine__need" onClick={(e) => e.stopPropagation()}>
                    <span>
                      {t('mot.in_caricamento')}
                    </span>
                  </div>
                )}

                {!p.disponibile && !p.in_avvio && (
                  <div className="engine__need" onClick={(e) => e.stopPropagation()}>
                    {!chiedeChiave ? (
                      <span>{p.rimedio}</span>
                    ) : inserendo === p.id ? (
                      <>
                        <input
                          type="password"
                          className="textfield textfield--sm"
                          style={{ width: 220 }}
                          placeholder={t('mot.ph_chiave')}
                          value={chiave}
                          autoFocus
                          onChange={(e) => setChiave(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') salva(p)
                            if (e.key === 'Escape') {
                              setInserendo(null)
                              setChiave('')
                            }
                          }}
                        />
                        <button className="btn btn--sm btn--primary" disabled={salvando || !chiave.trim()} onClick={() => salva(p)}>
                          {t('mot.salva')}
                        </button>
                        <button
                          className="btn btn--sm"
                          onClick={() => {
                            setInserendo(null)
                            setChiave('')
                          }}
                        >
                          {t('mot.annulla')}
                        </button>
                      </>
                    ) : (
                      <>
                        {t('mot.serve_chiave')}
                        <button
                          className="btn btn--sm"
                          onClick={() => {
                            setInserendo(p.id)
                            setChiave('')
                          }}
                        >
                          {t('mot.inserisci')}
                        </button>
                      </>
                    )}
                  </div>
                )}

                {p.esce_dal_computer && (
                  <p className="engine__risk">{t('mot2.inviata_a', { dove: DESTINAZIONE[p.id] ?? p.etichetta })}</p>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </>
  )
}
