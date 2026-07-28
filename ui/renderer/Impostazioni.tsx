/**
 * Scelta del motore che analizza le call.
 *
 * La differenza fra le opzioni non è tecnica ma pratica, ed è quella che conta
 * per chi sceglie: quanto ci mette, quanto costa, e soprattutto se la
 * trascrizione della riunione esce o no dal computer. Ogni voce lo dice
 * esplicitamente invece di limitarsi al nome del fornitore.
 */

import { useCallback, useEffect, useState } from 'react'

interface Provider {
  id: string
  etichetta: string
  descrizione: string
  model: string
  disponibile: boolean
  attivo: boolean
}

const FUORI_DAL_COMPUTER = new Set(['claude-cli', 'anthropic', 'openai'])

const RIMEDIO: Record<string, string> = {
  local: 'Il modello locale non risponde. Avvialo dal terminale con: python -m scriba_core.models_manager avvia --model gemma-4-12b',
  'claude-cli': "L'eseguibile claude non è nel PATH: serve Claude Code installato.",
  anthropic: 'Manca la chiave API di Anthropic.',
  openai: 'Manca la chiave API di OpenAI.',
}

export function Impostazioni({ onChiudi }: { onChiudi: () => void }) {
  const [providers, setProviders] = useState<Provider[]>([])
  const [salvando, setSalvando] = useState<string | null>(null)
  const [errore, setErrore] = useState<string | null>(null)

  const [scOverlay, setScOverlay] = useState('')
  const [esitoScorciatoia, setEsitoScorciatoia] = useState<string | null>(null)

  const carica = useCallback(async () => {
    const r = await window.scriba.get<Provider[]>('/providers')
    if (r.ok) setProviders(r.body)
    else setErrore(`Impossibile leggere le impostazioni (${r.status}).`)

    const s = await window.scriba.get<{ interfaccia?: { scorciatoia_overlay?: string } }>(
      '/settings',
    )
    if (s.ok) setScOverlay(s.body?.interfaccia?.scorciatoia_overlay ?? 'Alt+R')
  }, [])

  useEffect(() => {
    carica()
  }, [carica])

  /**
   * Salva la combinazione e prova subito a registrarla.
   *
   * Si riferisce l'esito perché una combinazione già presa da un'altra
   * applicazione viene rifiutata dal sistema in silenzio: senza dirlo, si
   * resterebbe a premere un tasto che non fa niente.
   */
  const salvaScorciatoia = async () => {
    const combinazione = scOverlay.trim()
    if (!combinazione) return
    setEsitoScorciatoia(null)

    const r = await window.scriba.post('/settings', {
      interfaccia: { scorciatoia_overlay: combinazione },
    })
    if (!r.ok) {
      setEsitoScorciatoia(`Non salvata (${r.status}).`)
      return
    }
    const attiva = await window.scriba.registraScorciatoiaOverlay()
    setEsitoScorciatoia(
      attiva
        ? `Attiva: ${attiva}`
        : `${combinazione} non è disponibile: la sta già usando un'altra applicazione.`,
    )
  }

  const scegli = async (p: Provider) => {
    setSalvando(p.id)
    setErrore(null)
    const r = await window.scriba.post('/settings', {
      llm: { provider: p.id, model: p.model },
    })
    if (!r.ok) setErrore(`Non è stato possibile salvare (${r.status}).`)
    await carica()
    setSalvando(null)
  }

  return (
    <div className="velo" onClick={onChiudi}>
      <div className="dialogo largo" onClick={(e) => e.stopPropagation()}>
        <h2>Come analizzare le call</h2>
        <p>
          La trascrizione avviene sempre sul tuo computer. Questa scelta riguarda solo il
          riassunto, i punti salienti e l'estrazione delle task.
        </p>

        {errore && <div className="avviso" style={{ marginBottom: 16 }}>{errore}</div>}

        <div className="scelte">
          {providers.map((p) => (
            <button
              key={p.id}
              className={`scelta ${p.attivo ? 'attiva' : ''}`}
              disabled={!p.disponibile || salvando !== null}
              onClick={() => scegli(p)}
            >
              <div className="scelta-testa">
                <span className="scelta-nome">{p.etichetta}</span>
                {p.attivo && <span className="targhetta">in uso</span>}
                {!p.disponibile && <span className="targhetta spenta">non disponibile</span>}
                {FUORI_DAL_COMPUTER.has(p.id) && (
                  // Detto sempre, anche sull'opzione già scelta: è la
                  // conseguenza che si dimentica più facilmente.
                  <span className="targhetta esce">i dati escono</span>
                )}
              </div>
              <div className="scelta-descrizione">{p.descrizione}</div>
              {!p.disponibile && <div className="scelta-rimedio">{RIMEDIO[p.id]}</div>}
            </button>
          ))}
        </div>

        <h2 style={{ marginTop: 28 }}>Scorciatoie</h2>
        <p>
          Funzionano anche quando Scriba non è in primo piano, che è il punto: durante una
          call il fuoco ce l'ha la riunione.
        </p>

        <div className="campo">
          <label htmlFor="sc-overlay">Mostra e nascondi la trascrizione sovrapposta</label>
          <input
            id="sc-overlay"
            type="text"
            value={scOverlay}
            placeholder="Alt+R"
            onChange={(e) => setScOverlay(e.target.value)}
            onBlur={salvaScorciatoia}
            onKeyDown={(e) => {
              if (e.key === 'Enter') e.currentTarget.blur()
            }}
          />
          <div className="nota">
            Scrivila come <code>Alt+R</code>, <code>Ctrl+Shift+T</code>,{' '}
            <code>Super+M</code>. Se la combinazione è già usata da un'altra applicazione
            viene segnalato qui sotto.
          </div>
          {esitoScorciatoia && <div className="nota esito">{esitoScorciatoia}</div>}
        </div>

        <div className="azioni">
          <button onClick={carica}>Ricontrolla</button>
          <button className="primario" onClick={onChiudi}>
            Chiudi
          </button>
        </div>
      </div>
    </div>
  )
}
