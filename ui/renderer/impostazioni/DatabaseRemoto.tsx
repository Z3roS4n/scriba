/**
 * Collegamento a un database PostgreSQL remoto.
 *
 * A passi come il collegamento a Notion, e per lo stesso motivo: sono scelte
 * che dipendono l'una dall'altra — non si può scegliere uno schema prima di
 * essersi collegati, né mappare colonne prima di aver scelto una tabella — e
 * mostrarle tutte insieme significa mostrarne tre su quattro spente.
 *
 * Due cose che questa schermata fa apposta:
 *
 * - **la password non torna mai indietro.** Il campo dell'indirizzo si
 *   ripresenta vuoto quando si è già collegati, e sotto c'è scritto a quale
 *   server: sapere *dove* si scrive serve, sapere *con quale password* no.
 * - **il DDL si legge prima di eseguirlo.** Sta per scrivere nel database di
 *   qualcuno; leggerlo prima è l'unico modo di sapere cosa sta per succedere.
 */

import { useCallback, useEffect, useState } from 'react'

import type {
  ColonneRemote,
  DatiRemoti,
  PezzoDdl,
  StatoDatabaseRemoto,
  TabellaModello,
} from '../tipi'
import { Select } from '../Select'

const MODALITA: Array<{ id: string; etichetta: string; nota: string }> = [
  { id: 'diretta', etichetta: 'Diretta', nota: 'Porta 5432 sul server vero. Su Supabase spesso risponde solo in IPv6.' },
  { id: 'pooling_transazione', etichetta: 'Pooling (transazione)', nota: 'Porta 6543. Gli statement preparati si spengono da soli: senza, il secondo invio fallisce.' },
  { id: 'pooling_sessione', etichetta: 'Pooling (sessione)', nota: 'Il pooler sulla 5432. Ripiego quando la diretta non è raggiungibile in IPv4.' },
]

type Passo = 'connessione' | 'schema' | 'tabelle' | 'mappa' | 'collegato'

export function SezioneDatabaseRemoto() {
  const [stato, setStato] = useState<StatoDatabaseRemoto | null>(null)
  const [modelloDati, setModelloDati] = useState<TabellaModello[]>([])
  const [passo, setPasso] = useState<Passo>('connessione')
  const [errore, setErrore] = useState<string | null>(null)
  const [occupato, setOccupato] = useState(false)

  const [url, setUrl] = useState('')
  const [modalita, setModalita] = useState('diretta')
  const [schemi, setSchemi] = useState<string[]>([])
  const [schema, setSchema] = useState('')
  const [versione, setVersione] = useState('')

  const [strada, setStrada] = useState<'crea' | 'mappa'>('crea')
  const [prefisso, setPrefisso] = useState('scriba_')
  const [scelte, setScelte] = useState<string[]>([])
  const [ddl, setDdl] = useState<PezzoDdl[]>([])

  const [tabelleRemote, setTabelleRemote] = useState<string[]>([])
  const [mappa, setMappa] = useState<Record<string, { nome: string; colonne: Record<string, string> }>>({})
  const [colonne, setColonne] = useState<Record<string, ColonneRemote>>({})

  const [esitoSync, setEsitoSync] = useState<string | null>(null)

  const ricarica = useCallback(async () => {
    const [s, m] = await Promise.all([
      window.scriba.get<StatoDatabaseRemoto>('/database-remoto/stato'),
      window.scriba.get<TabellaModello[]>('/database-remoto/modello'),
    ])
    if (m.ok) {
      setModelloDati(m.body)
      setScelte((prec) => (prec.length ? prec : m.body.filter((t) => t.predefinita).map((t) => t.chiave)))
    }
    if (s.ok) {
      setStato(s.body)
      if (s.body.collegato) {
        setPasso('collegato')
        setModalita(s.body.modalita ?? 'diretta')
        setSchema(s.body.schema ?? '')
      }
    }
  }, [])

  useEffect(() => {
    ricarica()
  }, [ricarica])

  /** Ogni chiamata che può fallire passa da qui: l'errore si mostra, non si perde. */
  const con = useCallback(async <T,>(fn: () => Promise<{ ok: boolean; body: T }>): Promise<T | null> => {
    setErrore(null)
    setOccupato(true)
    try {
      const r = await fn()
      if (!r.ok) {
        setErrore((r as any).body?.detail ?? 'Non è riuscito.')
        return null
      }
      return r.body
    } finally {
      setOccupato(false)
    }
  }, [])

  const provaConnessione = useCallback(async () => {
    const r = await con(() =>
      window.scriba.post<DatiRemoti>('/database-remoto/prova', { url, modalita }),
    )
    if (!r) return
    setSchemi(r.schemi)
    setVersione(r.versione)
    setModalita(r.modalita)
    setSchema((prec) => prec || (r.schemi.includes('public') ? 'public' : r.schemi[0] ?? ''))
    setPasso('schema')
  }, [con, url, modalita])

  const vaiAlleTabelle = useCallback(async () => {
    const r = await con(() =>
      window.scriba.post<PezzoDdl[]>('/database-remoto/anteprima', {
        schema_remoto: schema,
        prefisso,
        tabelle: scelte,
      }),
    )
    if (r) setDdl(r)
    const t = await con(() =>
      window.scriba.post<string[]>('/database-remoto/tabelle', { url, modalita, schema_remoto: schema }),
    )
    if (t) setTabelleRemote(t)
    setPasso('tabelle')
  }, [con, schema, prefisso, scelte, url, modalita])

  // L'anteprima segue le spunte: cambiare idea su una tabella deve cambiare
  // quello che si sta per eseguire, non lasciare a schermo il DDL di prima.
  useEffect(() => {
    if (passo !== 'tabelle' || strada !== 'crea') return
    window.scriba
      .post<PezzoDdl[]>('/database-remoto/anteprima', {
        schema_remoto: schema,
        prefisso,
        tabelle: scelte,
      })
      .then((r) => {
        if (r.ok) setDdl(r.body)
      })
  }, [passo, strada, schema, prefisso, scelte])

  const creaTabelle = useCallback(async () => {
    const r = await con(() =>
      window.scriba.post<StatoDatabaseRemoto>('/database-remoto/crea', {
        url,
        modalita,
        schema_remoto: schema,
        prefisso,
        tabelle: scelte,
      }),
    )
    if (!r) return
    setUrl('')
    await ricarica()
    setPasso('collegato')
  }, [con, url, modalita, schema, prefisso, scelte, ricarica])

  const caricaColonne = useCallback(
    async (chiave: string, tabella: string) => {
      const r = await con(() =>
        window.scriba.post<ColonneRemote>('/database-remoto/colonne', {
          url,
          modalita,
          schema_remoto: schema,
          tabella,
          per: chiave,
        }),
      )
      if (!r) return
      setColonne((prec) => ({ ...prec, [chiave]: r }))
      setMappa((prec) => ({
        ...prec,
        [chiave]: {
          nome: tabella,
          // Proposta già compilata quando i nomi coincidono: è il caso più
          // comune e risparmia una decina di scelte identiche.
          colonne: Object.fromEntries(
            r.campi
              .filter((c) => c.ammesse.includes(c.chiave))
              .map((c) => [c.chiave, c.chiave]),
          ),
        },
      }))
    },
    [con, url, modalita, schema],
  )

  const collegaMappa = useCallback(async () => {
    const soloScelte = Object.fromEntries(
      Object.entries(mappa).filter(([k, v]) => scelte.includes(k) && v.nome),
    )
    const r = await con(() =>
      window.scriba.post<StatoDatabaseRemoto>('/database-remoto/collega', {
        url,
        modalita,
        schema_remoto: schema,
        tabelle: soloScelte,
      }),
    )
    if (!r) return
    setUrl('')
    await ricarica()
    setPasso('collegato')
  }, [con, mappa, scelte, url, modalita, schema, ricarica])

  const sincronizzaTutto = useCallback(async () => {
    setEsitoSync(null)
    const r = await con(() =>
      window.scriba.post<{ sincronizzate: number; fallite: number; righe: number; errore: string | null }>(
        '/database-remoto/sincronizza-tutto',
      ),
    )
    if (!r) return
    setEsitoSync(
      r.sincronizzate === 0 && r.fallite === 0
        ? 'Era già tutto sincronizzato.'
        : `${r.sincronizzate} call inviate (${r.righe} righe)` +
            (r.fallite ? `, ${r.fallite} non riuscite: ${r.errore}` : '.'),
    )
  }, [con])

  const scollega = useCallback(async () => {
    if (!window.confirm('Scollegare il database? I dati già scritti là fuori restano dove sono.')) return
    await window.scriba.post('/database-remoto/scollega')
    setPasso('connessione')
    setEsitoSync(null)
    await ricarica()
  }, [ricarica])

  const alterna = (chiave: string) =>
    setScelte((prec) => (prec.includes(chiave) ? prec.filter((c) => c !== chiave) : [...prec, chiave]))

  return (
    <>
      <div className="settings__head">Database remoto</div>
      <div className="settings__body">
        <p className="vis__nota">
          Tiene una copia delle call su un PostgreSQL — Supabase, o qualunque altro. Scegli tu in
          quale schema scrivere e quali dati mandare.{' '}
          <b>La trascrizione, se la includi, esce da questo computer.</b>
        </p>

        {errore && (
          <div className="alert alert--inline">
            <p>{errore}</p>
          </div>
        )}

        {stato?.segreto_in_chiaro && (
          <div className="alert alert--inline">
            <p>
              L'indirizzo è salvato in chiaro: la cifratura di Windows non ha risposto quando è
              stato collegato. Chi legge quel file entra nel database.
            </p>
          </div>
        )}

        {/* ---------------------------------------------------- collegato */}
        {passo === 'collegato' && stato?.collegato && (
          <>
            <div className="row">
              <div className="row__t">
                <b>Collegato</b>
                <span style={{ fontFamily: 'var(--font-code)' }}>
                  {stato.server?.utente}@{stato.server?.host}:{stato.server?.porta}/
                  {stato.server?.database} · schema {stato.schema} ·{' '}
                  {MODALITA.find((m) => m.id === stato.modalita)?.etichetta ?? stato.modalita}
                </span>
              </div>
              <button className="btn" onClick={scollega}>
                Scollega
              </button>
            </div>

            <div className="row">
              <div className="row__t">
                <b>Cosa viene mandato</b>
                <span>
                  {Object.entries(stato.tabelle)
                    .map(([k, v]) => `${modelloDati.find((t) => t.chiave === k)?.etichetta ?? k} → ${v.nome}`)
                    .join(' · ')}
                </span>
              </div>
              <button className="btn" onClick={() => setPasso('connessione')}>
                Cambia
              </button>
            </div>

            <div className="row">
              <div className="row__t">
                <b>Sincronizza da sola a fine analisi</b>
                <span>Una registrazione in corso non aspetta mai il database: se la rete manca, si riprova dopo.</span>
              </div>
              <button
                className={`switch ${stato.automatico ? 'is-on' : ''}`}
                aria-pressed={stato.automatico}
                onClick={async () => {
                  await window.scriba.post('/database-remoto/collega', { automatico: !stato.automatico })
                  ricarica()
                }}
              >
                <span className="sq" />
                {stato.automatico ? 'Attivo' : 'Spento'}
              </button>
            </div>

            <div className="row">
              <div className="row__t">
                <b>Il pregresso</b>
                <span>Manda tutte le call non ancora sincronizzate. Si può rifare quante volte si vuole.</span>
              </div>
              <button className="btn" disabled={occupato} onClick={sincronizzaTutto}>
                {occupato ? 'Invio…' : 'Sincronizza tutto'}
              </button>
            </div>

            {esitoSync && <p className="vis__nota">{esitoSync}</p>}
          </>
        )}

        {/* --------------------------------------------------- connessione */}
        {passo === 'connessione' && (
          <>
            <div className="row">
              <div className="row__t">
                <b>Indirizzo</b>
                <span>
                  <code>postgresql://utente:password@host:5432/database</code>
                  {stato?.collegato && ' — lascialo vuoto per non cambiare quello già salvato.'}
                </span>
              </div>
            </div>
            <input
              className="textfield"
              style={{ maxWidth: '100%' }}
              type="password"
              value={url}
              placeholder="postgresql://…"
              onChange={(e) => {
                setUrl(e.target.value)
                // La modalità si propone dall'indirizzo: la porta 6543 e gli
                // host `pooler.` sono l'unico modo di indovinarla bene.
                try {
                  const u = new URL(e.target.value.replace(/^postgres(ql)?:/, 'http:'))
                  if (u.port === '6543') setModalita('pooling_transazione')
                  else if (u.hostname.includes('pooler.')) setModalita('pooling_sessione')
                  else setModalita('diretta')
                } catch {
                  /* indirizzo incompleto: si lascia la modalità com'è */
                }
              }}
            />

            <div className="row">
              <div className="row__t">
                <b>Come ci si collega</b>
                <span>{MODALITA.find((m) => m.id === modalita)?.nota}</span>
              </div>
              <Select
                opzioni={MODALITA.map((m) => ({ id: m.id, etichetta: m.etichetta }))}
                selezionato={modalita}
                onScegli={setModalita}
              />
            </div>

            <div className="row">
              <div className="row__t">
                <b>Prova il collegamento</b>
                <span>Non salva niente: si collega, chiede la versione e gli schemi, e riferisce.</span>
              </div>
              <button className="btn" disabled={occupato || !url.trim()} onClick={provaConnessione}>
                {occupato ? 'Provo…' : 'Prova'}
              </button>
            </div>
          </>
        )}

        {/* -------------------------------------------------------- schema */}
        {passo === 'schema' && (
          <>
            <p className="vis__nota">Collegato a {versione.split(',')[0]}.</p>
            <div className="row">
              <div className="row__t">
                <b>In quale schema scrivere</b>
                <span>Gli schemi di sistema non sono in elenco: non sarebbero una scelta sensata.</span>
              </div>
              <Select
                opzioni={schemi.map((s) => ({ id: s, etichetta: s }))}
                selezionato={schema}
                onScegli={setSchema}
              />
            </div>
            <div className="row">
              <div className="row__t">
                <b>Le tabelle</b>
                <span>Le crea Scriba, oppure gliele indichi tu se ce le hai già.</span>
              </div>
              <div className="picker">
                <button className={strada === 'crea' ? 'is-on' : ''} onClick={() => setStrada('crea')}>
                  Creale tu
                </button>
                <button className={strada === 'mappa' ? 'is-on' : ''} onClick={() => setStrada('mappa')}>
                  Ce le ho già
                </button>
              </div>
            </div>
            <div className="row">
              <div className="row__t" />
              <button className="btn" disabled={occupato || !schema} onClick={vaiAlleTabelle}>
                Avanti
              </button>
            </div>
          </>
        )}

        {/* ------------------------------------------------------- tabelle */}
        {passo === 'tabelle' && (
          <>
            <div className="row">
              <div className="row__t">
                <b>Quali dati mandare</b>
                <span>Quello che non spunti non esce da questo computer.</span>
              </div>
              {strada === 'crea' && (
                <input
                  className="textfield"
                  style={{ maxWidth: 140 }}
                  value={prefisso}
                  onChange={(e) => setPrefisso(e.target.value)}
                  title="Prefisso dei nomi delle tabelle"
                />
              )}
            </div>

            {modelloDati.map((t) => (
              <div key={t.chiave} className="cli__row">
                <button
                  className={`checkbox ${scelte.includes(t.chiave) ? 'is-on' : ''}`}
                  onClick={() => alterna(t.chiave)}
                  aria-label={t.etichetta}
                >
                  {scelte.includes(t.chiave) ? '✓' : ''}
                </button>
                <div className="row__t" style={{ flex: 1 }}>
                  <b>
                    {t.etichetta}
                    {t.voluminosa && ' — può essere grande'}
                  </b>
                  <span>{t.descrizione}</span>
                </div>
                {strada === 'mappa' && scelte.includes(t.chiave) && (
                  <Select
                    opzioni={[
                      { id: '', etichetta: '— quale tabella? —' },
                      ...tabelleRemote.map((n) => ({ id: n, etichetta: n })),
                    ]}
                    selezionato={mappa[t.chiave]?.nome ?? ''}
                    onScegli={(v) => caricaColonne(t.chiave, v)}
                    larghezza={240}
                  />
                )}
              </div>
            ))}

            {strada === 'crea' ? (
              <>
                <div className="row">
                  <div className="row__t">
                    <b>Cosa verrà eseguito</b>
                    <span>Nessun DROP, nessun ALTER: su un database che è tuo si aggiunge, non si sistema d'ufficio.</span>
                  </div>
                </div>
                <pre className="ddl">{ddl.map((p) => p.sql).join(';\n\n')}</pre>
                <div className="row">
                  <div className="row__t" />
                  <button className="btn" onClick={() => setPasso('schema')}>
                    Indietro
                  </button>
                  <button
                    className="btn btn--rec"
                    disabled={occupato || scelte.length === 0}
                    onClick={creaTabelle}
                  >
                    {occupato ? 'Creo…' : 'Crea e collega'}
                  </button>
                </div>
              </>
            ) : (
              <>
                {scelte
                  .filter((k) => colonne[k])
                  .map((k) => (
                    <div key={k}>
                      <div className="arch__group">
                        {modelloDati.find((t) => t.chiave === k)?.etichetta} → {mappa[k]?.nome}
                      </div>
                      {colonne[k].campi.map((c) => (
                        <div key={c.chiave} className="cli__row">
                          <span className="cli__nome">
                            {c.etichetta}
                            {c.chiave_naturale && ' *'}
                          </span>
                          <span className="cli__meta">{c.descrizione}</span>
                          <Select
                            opzioni={[
                              { id: '', etichetta: '— non mandare —' },
                              ...c.ammesse.map((n) => ({ id: n, etichetta: n })),
                            ]}
                            selezionato={mappa[k]?.colonne[c.chiave] ?? ''}
                            onScegli={(v) =>
                              setMappa((prec) => {
                                const colonneOra = { ...(prec[k]?.colonne ?? {}) }
                                if (v) colonneOra[c.chiave] = v
                                else delete colonneOra[c.chiave]
                                return { ...prec, [k]: { ...prec[k], colonne: colonneOra } }
                              })
                            }
                            larghezza={240}
                          />
                        </div>
                      ))}
                    </div>
                  ))}
                <p className="vis__nota">
                  I campi con <b>*</b> servono a riconoscere una riga già inviata: senza, ogni
                  sincronizzazione ne aggiungerebbe di nuove.
                </p>
                <div className="row">
                  <div className="row__t" />
                  <button className="btn" onClick={() => setPasso('schema')}>
                    Indietro
                  </button>
                  <button className="btn btn--rec" disabled={occupato} onClick={collegaMappa}>
                    {occupato ? 'Collego…' : 'Collega'}
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </>
  )
}
