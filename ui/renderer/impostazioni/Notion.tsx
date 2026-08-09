/**
 * Notion: quale database, e quale dato di Scriba va in quale colonna.
 *
 * Il collegamento non passa da `onCambia`/`Impostazioni`: non vive in
 * `impostazioni.export` (quella forma è di sola lettura, vedi `tipi.ts`) né in
 * `settings.json` — il core lo tiene in un file a parte (`export/notion.py`),
 * fuori dal perimetro di `Settings`. Si parla quindi direttamente al core con
 * `window.scriba.get/post`, come fa già `Scorciatoie.tsx`.
 *
 * L'elenco dei campi mappabili arriva dal core (`/export/notion/campi`): è là
 * la definizione, e riscriverla qui significherebbe vederla divergere.
 *
 * L'id del database non si incolla a mano: si sceglie fra quelli che
 * l'integrazione può vedere. Un id sbagliato e un database non condiviso danno
 * lo stesso errore, e non c'è modo per chi lo riceve di capire quale dei due
 * gli è capitato.
 */

import { useEffect, useState } from 'react'

import type {
  CampoNotion,
  DestinazioniNotion,
  SchemaNotion,
  StatoNotion,
} from '../tipi'
import { Modal } from './Modal'
import { Select } from '../Select'

const ETICHETTE_TIPO: Record<string, string> = {
  title: 'titolo',
  rich_text: 'testo',
  number: 'numero',
  date: 'data',
  checkbox: 'spunta',
  select: 'elenco',
  multi_select: 'elenco multiplo',
  status: 'stato',
  url: 'link',
}

const NON_MANDARE = ''

type Passo = 'chiusa' | 'token' | 'scelta' | 'mappa' | 'crea'

const tipoLeggibile = (tipo: string) => ETICHETTE_TIPO[tipo] ?? tipo

function motivo(risposta: { status: number; body: unknown }, ripiego: string): string {
  const corpo = risposta.body as { detail?: string } | null
  return corpo?.detail ?? `${ripiego} (${risposta.status}).`
}

export function SezioneNotion() {
  const [stato, setStato] = useState<StatoNotion | null>(null)
  const [campi, setCampi] = useState<CampoNotion[]>([])
  const [passo, setPasso] = useState<Passo>('chiusa')
  const [token, setToken] = useState('')
  const [destinazioni, setDestinazioni] = useState<DestinazioniNotion | null>(null)
  const [schema, setSchema] = useState<SchemaNotion | null>(null)
  const [mappa, setMappa] = useState<Record<string, string>>({})
  const [pagina, setPagina] = useState<string | null>(null)
  const [nomeNuovo, setNomeNuovo] = useState('Task da Scriba')
  const [scelti, setScelti] = useState<string[]>([])
  const [lavorando, setLavorando] = useState(false)
  const [errore, setErrore] = useState<string | null>(null)

  useEffect(() => {
    window.scriba.get<StatoNotion>('/export/notion/stato').then((r) => {
      if (r.ok) setStato(r.body)
    })
    window.scriba.get<CampoNotion[]>('/export/notion/campi').then((r) => {
      if (!r.ok) return
      setCampi(r.body)
      setScelti(r.body.filter((c) => c.consigliato && !c.obbligatorio).map((c) => c.id))
    })
  }, [])

  const collegato = stato?.collegato ?? false
  const opzionali = campi.filter((c) => !c.obbligatorio)
  const campoTitolo = campi.find((c) => c.obbligatorio)

  const chiudi = () => {
    setPasso('chiusa')
    setErrore(null)
    setToken('')
    setDestinazioni(null)
    setSchema(null)
  }

  const caricaDestinazioni = async (conToken: string) => {
    setLavorando(true)
    setErrore(null)
    const r = await window.scriba.post<DestinazioniNotion>('/export/notion/destinazioni', {
      token: conToken,
    })
    setLavorando(false)
    if (!r.ok) {
      setErrore(motivo(r, 'Notion non ha risposto'))
      return
    }
    setDestinazioni(r.body)
    setPasso('scelta')
  }

  const apriSchema = async (databaseId: string) => {
    setLavorando(true)
    setErrore(null)
    const r = await window.scriba.post<SchemaNotion>('/export/notion/schema', {
      token,
      database_id: databaseId,
    })
    setLavorando(false)
    if (!r.ok) {
      setErrore(motivo(r, 'Il database non si è letto'))
      return
    }
    setSchema(r.body)
    // La mappatura già salvata vale solo per il database a cui si riferisce:
    // su un altro database gli stessi nomi di colonna non ci sono.
    const salvata = stato?.database_id === r.body.database_id ? stato?.mappa : undefined
    setMappa(salvata && Object.keys(salvata).length > 0 ? salvata : r.body.mappa_proposta)
    setPasso('mappa')
  }

  const salvaMappatura = async () => {
    if (!schema) return
    setLavorando(true)
    setErrore(null)
    const r = await window.scriba.post<StatoNotion>('/export/notion/collega', {
      token,
      database_id: schema.database_id,
      database_titolo: schema.titolo,
      mappa,
    })
    setLavorando(false)
    if (!r.ok) {
      setErrore(motivo(r, 'Il collegamento non è riuscito'))
      return
    }
    setStato(r.body)
    chiudi()
  }

  const creaDatabase = async () => {
    if (!pagina) return
    setLavorando(true)
    setErrore(null)
    const r = await window.scriba.post<StatoNotion>('/export/notion/database', {
      token,
      pagina_id: pagina,
      titolo: nomeNuovo,
      campi: scelti,
    })
    setLavorando(false)
    if (!r.ok) {
      setErrore(motivo(r, 'Il database non si è creato'))
      return
    }
    setStato(r.body)
    chiudi()
  }

  const scollega = async () => {
    setLavorando(true)
    const r = await window.scriba.post<StatoNotion>('/export/notion/scollega')
    setLavorando(false)
    if (r.ok) setStato(r.body)
    else setErrore(motivo(r, 'Lo scollegamento non è riuscito'))
  }

  const descrizione = collegato
    ? `Collegato al database «${stato?.database_titolo ?? stato?.database_id}». Le task confermate diventano righe lì, nelle colonne che hai scelto.`
    : 'Le task confermate diventano righe in un database di Notion, con il minuto della prova come citazione.'

  return (
    <>
      <div className="row row--risk">
        <div className="row__text">
          <b>Manda le task a Notion</b>
          <span>{descrizione}</span>
          <span>I dati della call escono dal computer verso Notion.</span>
          {errore && passo === 'chiusa' && <span style={{ color: 'var(--red)' }}>{errore}</span>}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', alignItems: 'flex-end' }}>
          {collegato ? (
            <>
              <button
                className="btn btn--sm"
                disabled={lavorando}
                onClick={() => {
                  setErrore(null)
                  apriSchema(stato?.database_id ?? '')
                }}
              >
                Cambia le colonne
              </button>
              <button
                className="btn btn--sm"
                disabled={lavorando}
                onClick={() => {
                  setErrore(null)
                  caricaDestinazioni('')
                }}
              >
                Cambia database
              </button>
              <button className="btn btn--sm" disabled={lavorando} onClick={scollega}>
                Scollega
              </button>
            </>
          ) : (
            <button
              className="btn btn--sm btn--primary"
              onClick={() => {
                setErrore(null)
                setPasso('token')
              }}
            >
              Collega Notion
            </button>
          )}
        </div>
      </div>

      {passo === 'token' && (
        <Modal onChiudi={chiudi}>
          <div className="modal__head">
            <h2>Il token dell’integrazione</h2>
            <p>
              Si crea su notion.so/my-integrations. Poi va condiviso, dal menù «…» della pagina o del database,
              con l’integrazione appena creata: senza quel passaggio Notion non la lascia entrare.
            </p>
          </div>
          <div className="modal__field">
            <input
              type="password"
              className="textfield"
              autoFocus
              placeholder="ntn_…"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
          </div>
          {errore && (
            <div className="modal__field" style={{ paddingTop: 0, color: 'var(--red)', fontSize: 'var(--fs-sm)' }}>
              {errore}
            </div>
          )}
          <div className="modal__foot">
            <button className="btn" onClick={chiudi}>
              Annulla
            </button>
            <button
              className="btn btn--primary"
              disabled={lavorando || !token.trim()}
              onClick={() => caricaDestinazioni(token.trim())}
            >
              {lavorando ? 'Sto guardando…' : 'Continua'}
            </button>
          </div>
        </Modal>
      )}

      {passo === 'scelta' && destinazioni && (
        <Modal onChiudi={chiudi}>
          <div className="modal__head">
            <h2>Quale database?</h2>
            <p>
              Solo quelli che hai condiviso con l’integrazione. Se il tuo non c’è, aprilo in Notion e condividilo,
              oppure fatene creare uno nuovo con le colonne che ti servono.
            </p>
          </div>
          <div
            style={{
              padding: '0 20px 16px',
              display: 'flex',
              flexDirection: 'column',
              gap: 1,
              maxHeight: 300,
              overflowY: 'auto',
            }}
          >
            {destinazioni.database.length === 0 ? (
              <p style={{ color: 'var(--fg-3)', fontSize: 'var(--fs-sm)' }}>
                Nessun database condiviso con l’integrazione.
              </p>
            ) : (
              destinazioni.database.map((d) => (
                <button key={d.id} className="btn btn--block" disabled={lavorando} onClick={() => apriSchema(d.id)}>
                  {d.titolo}
                </button>
              ))
            )}
          </div>
          {errore && (
            <div className="modal__field" style={{ paddingTop: 0, color: 'var(--red)', fontSize: 'var(--fs-sm)' }}>
              {errore}
            </div>
          )}
          <div className="modal__foot">
            <button className="btn" onClick={chiudi}>
              Annulla
            </button>
            <button
              className="btn"
              disabled={destinazioni.pagine.length === 0}
              onClick={() => {
                setErrore(null)
                setPasso('crea')
              }}
            >
              Creane uno nuovo
            </button>
          </div>
        </Modal>
      )}

      {passo === 'mappa' && schema && (
        <Modal onChiudi={chiudi} larghezza={560}>
          <div className="modal__head">
            <h2>Cosa va in quale colonna</h2>
            <p>
              Database «{schema.titolo}». Un campo lasciato su «Non mandare» resta in Scriba e non arriva a Notion.
            </p>
          </div>
          <div
            style={{
              padding: '0 20px',
              display: 'flex',
              flexDirection: 'column',
              maxHeight: 340,
              overflowY: 'auto',
            }}
          >
            {campoTitolo && (
              <div className="row" style={{ paddingTop: 'var(--sp-5)', paddingBottom: 'var(--sp-5)' }}>
                <div className="row__text">
                  <b>{campoTitolo.etichetta}</b>
                  <span>{campoTitolo.aiuto}</span>
                </div>
                <span style={{ fontSize: 'var(--fs-sm)', color: 'var(--fg-3)', paddingTop: 3 }}>
                  {schema.titolo_proprieta} · titolo
                </span>
              </div>
            )}
            {opzionali.map((campo) => {
              const usate = new Set(
                Object.entries(mappa)
                  .filter(([id]) => id !== campo.id)
                  .map(([, nome]) => nome)
              )
              const compatibili = schema.proprieta.filter((p) => campo.tipi.includes(p.tipo))
              const opzioni = [
                { id: NON_MANDARE, etichetta: 'Non mandare' },
                ...compatibili
                  .filter((p) => !usate.has(p.nome))
                  .map((p) => ({ id: p.nome, etichetta: `${p.nome} · ${tipoLeggibile(p.tipo)}` })),
              ]
              return (
                <div
                  className="row"
                  key={campo.id}
                  style={{ paddingTop: 'var(--sp-5)', paddingBottom: 'var(--sp-5)' }}
                >
                  <div className="row__text">
                    <b>{campo.etichetta}</b>
                    <span>{campo.aiuto}</span>
                  </div>
                  {compatibili.length === 0 ? (
                    <span
                      style={{
                        fontSize: 'var(--fs-sm)',
                        color: 'var(--fg-3)',
                        maxWidth: 190,
                        textAlign: 'right',
                        paddingTop: 3,
                      }}
                    >
                      Serve una colonna di tipo {campo.tipi.map(tipoLeggibile).join(' o ')}
                    </span>
                  ) : (
                    <Select
                      opzioni={opzioni}
                      selezionato={mappa[campo.id] ?? NON_MANDARE}
                      vuoto="Non mandare"
                      onScegli={(nome) =>
                        setMappa((precedente) => {
                          const nuova = { ...precedente }
                          if (nome === NON_MANDARE) delete nuova[campo.id]
                          else nuova[campo.id] = nome
                          return nuova
                        })
                      }
                    />
                  )}
                </div>
              )
            })}
          </div>
          {errore && (
            <div className="modal__field" style={{ paddingBottom: 0, color: 'var(--red)', fontSize: 'var(--fs-sm)' }}>
              {errore}
            </div>
          )}
          <div className="modal__foot">
            <span className="modal__hint">{Object.keys(mappa).length} campi su Notion</span>
            <button className="btn" onClick={chiudi}>
              Annulla
            </button>
            <button className="btn btn--primary" disabled={lavorando} onClick={salvaMappatura}>
              {lavorando ? 'Sto salvando…' : 'Salva'}
            </button>
          </div>
        </Modal>
      )}

      {passo === 'crea' && destinazioni && (
        <Modal onChiudi={chiudi}>
          <div className="modal__head">
            <h2>Un database nuovo</h2>
            <p>Lo crea Scriba dentro una pagina che gli hai condiviso, con le sole colonne che scegli qui.</p>
          </div>
          <div className="modal__field">
            <span className="label">DENTRO QUALE PAGINA</span>
            <Select
              opzioni={destinazioni.pagine.map((p) => ({ id: p.id, etichetta: p.titolo }))}
              selezionato={pagina}
              vuoto="Scegli una pagina"
              onScegli={setPagina}
            />
          </div>
          <div className="modal__field" style={{ paddingTop: 0 }}>
            <span className="label">NOME DEL DATABASE</span>
            <input
              className="textfield"
              value={nomeNuovo}
              onChange={(e) => setNomeNuovo(e.target.value)}
            />
          </div>
          <div className="modal__field" style={{ paddingTop: 0 }}>
            <span className="label">COLONNE</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)', maxHeight: 240, overflowY: 'auto' }}>
              {campoTitolo && (
                <div style={{ display: 'flex', gap: 11, alignItems: 'flex-start' }}>
                  <button type="button" className="checkbox is-on" disabled aria-pressed>
                    ✓
                  </button>
                  <div className="row__text">
                    <b>
                      {campoTitolo.nome_notion} · {campoTitolo.etichetta}
                    </b>
                    <span>{campoTitolo.aiuto}</span>
                  </div>
                </div>
              )}
              {opzionali.map((campo) => {
                const acceso = scelti.includes(campo.id)
                return (
                  <div key={campo.id} style={{ display: 'flex', gap: 11, alignItems: 'flex-start' }}>
                    <button
                      type="button"
                      className={`checkbox${acceso ? ' is-on' : ''}`}
                      aria-pressed={acceso}
                      onClick={() =>
                        setScelti((precedenti) =>
                          acceso ? precedenti.filter((id) => id !== campo.id) : [...precedenti, campo.id]
                        )
                      }
                    >
                      ✓
                    </button>
                    <div className="row__text">
                      <b>
                        {campo.nome_notion} · {tipoLeggibile(campo.tipi[0])}
                      </b>
                      <span>{campo.aiuto}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
          {errore && (
            <div className="modal__field" style={{ paddingTop: 0, color: 'var(--red)', fontSize: 'var(--fs-sm)' }}>
              {errore}
            </div>
          )}
          <div className="modal__foot">
            <button className="btn" onClick={() => setPasso('scelta')}>
              Indietro
            </button>
            <button
              className="btn btn--primary"
              disabled={lavorando || !pagina || !nomeNuovo.trim()}
              onClick={creaDatabase}
            >
              {lavorando ? 'Sto creando…' : 'Crea e collega'}
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
