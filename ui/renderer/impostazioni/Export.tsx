/**
 * Cartella di export, formato, e il collegamento a Notion.
 *
 * Il collegamento (token + id del database) non passa da `onCambia`/
 * `Impostazioni`: non vive in `impostazioni.export` (quella forma è di sola
 * lettura, vedi `tipi.ts`) né in `settings.json` — il core lo tiene in un
 * file a parte (`export/notion.py`), fuori dal perimetro di `Settings`. Si
 * parla quindi direttamente al core con `window.scriba.get/post`, come fa già
 * `Scorciatoie.tsx` per `provaScorciatoia`/`registraScorciatoie`.
 */

import { useEffect, useState } from 'react'

import type { Impostazioni } from '../tipi'

const FORMATI = [
  { id: 'markdown', etichetta: 'Markdown' },
  { id: 'testo', etichetta: 'Testo' },
  { id: 'json', etichetta: 'JSON' },
] as const

interface StatoNotion {
  collegato: boolean
  database_id: string | null
}

function SezioneNotion() {
  const [stato, setStato] = useState<StatoNotion | null>(null)
  const [token, setToken] = useState('')
  const [databaseId, setDatabaseId] = useState('')
  const [lavorando, setLavorando] = useState(false)
  const [errore, setErrore] = useState<string | null>(null)

  useEffect(() => {
    window.scriba.get<StatoNotion>('/export/notion/stato').then((r) => {
      if (r.ok) setStato(r.body)
    })
  }, [])

  const collega = async () => {
    if (!token.trim() || !databaseId.trim()) return
    setLavorando(true)
    setErrore(null)
    const r = await window.scriba.post<StatoNotion>('/export/notion/collega', {
      token: token.trim(),
      database_id: databaseId.trim(),
    })
    setLavorando(false)
    if (r.ok) {
      setStato(r.body)
      setToken('')
      setDatabaseId('')
    } else {
      setErrore(`Collegamento non riuscito (${r.status}).`)
    }
  }

  const scollega = async () => {
    setLavorando(true)
    setErrore(null)
    const r = await window.scriba.post<StatoNotion>('/export/notion/scollega')
    setLavorando(false)
    if (r.ok) setStato(r.body)
    else setErrore(`Scollegamento non riuscito (${r.status}).`)
  }

  const collegato = stato?.collegato ?? false

  return (
    <div className="row row--risk">
      <div className="row__text">
        <b>Manda le task a Notion</b>
        <span>
          {collegato
            ? `Collegato al database ${stato?.database_id}. Le task confermate diventano righe lì, con il minuto della prova nel testo.`
            : 'Le task confermate diventano righe in un database di Notion, con il minuto della prova come citazione.'}
        </span>
        <span>I dati della call escono dal computer verso Notion.</span>
        {errore && <span style={{ color: 'var(--red-fg)' }}>{errore}</span>}
      </div>
      {collegato ? (
        <button className="btn btn--sm" disabled={lavorando} onClick={scollega}>
          Scollega
        </button>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', alignItems: 'flex-end' }}>
          <input
            type="password"
            className="textfield"
            style={{ width: 220 }}
            placeholder="Token dell'integrazione"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <input
            className="textfield"
            style={{ width: 220 }}
            placeholder="Id del database"
            value={databaseId}
            onChange={(e) => setDatabaseId(e.target.value)}
          />
          <button
            className="btn btn--sm btn--primary"
            disabled={lavorando || !token.trim() || !databaseId.trim()}
            onClick={collega}
          >
            Collega
          </button>
        </div>
      )}
    </div>
  )
}

export function SezioneExport({
  impostazioni,
  onCambia,
  onCambiaCartella,
}: {
  impostazioni: Impostazioni
  onCambia: (patch: Partial<Impostazioni>) => void
  onCambiaCartella: () => void
}) {
  const esp = impostazioni.export ?? { cartella: null, formato: 'markdown' as const }

  return (
    <>
      <div className="settings__head">Export</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__text">
            <b>Cartella predefinita</b>
            <span style={{ fontFamily: 'var(--mono)' }}>{esp.cartella ?? 'Non ancora scelta'}</span>
          </div>
          <button className="btn" onClick={onCambiaCartella}>
            Cambia
          </button>
        </div>
        <div className="row">
          <div className="row__text">
            <b>Formato</b>
            <span>Il markdown contiene anche i minuti delle prove. Il testo è la trascrizione pulita, il JSON porta tutto — comprese le prove — in una forma per un programma.</span>
          </div>
          <div className="segment">
            {FORMATI.map((f) => (
              <button
                key={f.id}
                className={esp.formato === f.id ? 'is-on' : ''}
                onClick={() => onCambia({ export: { ...esp, formato: f.id } })}
              >
                {f.etichetta}
              </button>
            ))}
          </div>
        </div>
        <SezioneNotion />
      </div>
    </>
  )
}
