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
      <div className="settings__head">Motore di analisi</div>
      <div className="settings__body">
        <p>Chi legge la trascrizione e ne ricava riassunto, punti salienti e task. Se ne può usare uno solo alla volta.</p>
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
                      <span className="engine__speed">circa {p.minuti_per_ora} min per un’ora di call</span>
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
                            : 'Non disponibile'}
                  </span>
                </div>

                {p.in_avvio && (
                  <div className="engine__need" onClick={(e) => e.stopPropagation()}>
                    <span>
                      Il modello si sta caricando in memoria. Diventa selezionabile da solo appena risponde:
                      non serve riaprire questa finestra.
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
                          placeholder="Chiave API"
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
                          Salva
                        </button>
                        <button
                          className="btn btn--sm"
                          onClick={() => {
                            setInserendo(null)
                            setChiave('')
                          }}
                        >
                          Annulla
                        </button>
                      </>
                    ) : (
                      <>
                        Serve una chiave API
                        <button
                          className="btn btn--sm"
                          onClick={() => {
                            setInserendo(p.id)
                            setChiave('')
                          }}
                        >
                          Inserisci la chiave
                        </button>
                      </>
                    )}
                  </div>
                )}

                {p.esce_dal_computer && (
                  <p className="engine__risk">La trascrizione viene inviata a {DESTINAZIONE[p.id] ?? p.etichetta}.</p>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </>
  )
}
