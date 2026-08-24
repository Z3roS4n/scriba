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
import { useT, type Chiave } from '../lingua'

const MODI = ['diretta', 'pooling_transazione', 'pooling_sessione'] as const

type Passo = 'connessione' | 'schema' | 'tabelle' | 'mappa' | 'collegato'

export function SezioneDatabaseRemoto() {
  const t = useT()
  const MODALITA = MODI.map((id) => ({
    id,
    etichetta: t(`db2.modo.${id}` as Chiave),
    nota: t(`db2.modo_nota.${id}` as Chiave),
  }))
  const [stato, setStato] = useState<StatoDatabaseRemoto | null>(null)
  const [modelloDati, setModelloDati] = useState<TabellaModello[]>([])
  const [passo, setPasso] = useState<Passo>('connessione')
  const [errore, setErrore] = useState<string | null>(null)
  const [occupato, setOccupato] = useState(false)

  const [url, setUrl] = useState('')
  // Mostrare l'indirizzo è una scelta per un momento, non uno stato da
  // ricordare: si riparte sempre coperto, e si scopre chiedendolo.
  const [mostraUrl, setMostraUrl] = useState(false)
  const [modalita, setModalita] = useState('diretta')
  const [schemi, setSchemi] = useState<string[]>([])
  const [schema, setSchema] = useState('')
  // Scegliere fra quelli che ci sono, oppure scriverne uno che ancora non c'è.
  const [scriviSchema, setScriviSchema] = useState(false)
  const [versione, setVersione] = useState('')

  const [strada, setStrada] = useState<'crea' | 'mappa'>('crea')
  const [prefisso, setPrefisso] = useState('scriba_')
  const [scelte, setScelte] = useState<string[]>([])
  const [ddl, setDdl] = useState<PezzoDdl[]>([])

  const [tabelleRemote, setTabelleRemote] = useState<string[]>([])
  const [mappa, setMappa] = useState<Record<string, { nome: string; colonne: Record<string, string> }>>({})
  const [colonne, setColonne] = useState<Record<string, ColonneRemote>>({})

  const [esitoSync, setEsitoSync] = useState<string | null>(null)

  // Va creato quello che il server non ha elencato — non quello scritto a
  // mano. Chi digita il nome di uno schema che esiste vuole quello, e un
  // `CREATE SCHEMA` di troppo chiede un permesso (`CREATE` sul database) che
  // per scrivere in uno schema esistente non serve.
  const nomeSchema = schema.trim()
  const daCreare = nomeSchema !== '' && !schemi.includes(nomeSchema)

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

  // Fuori dal passo della connessione l'indirizzo torna coperto. Detto qui una
  // volta invece che su ogni pulsante che porta via: le strade per uscire da
  // quel passo sono quattro, e una dimenticata è un indirizzo che resta a
  // schermo.
  useEffect(() => {
    if (passo !== 'connessione') setMostraUrl(false)
  }, [passo])

  /** Ogni chiamata che può fallire passa da qui: l'errore si mostra, non si perde. */
  const con = useCallback(async <T,>(fn: () => Promise<{ ok: boolean; body: T }>): Promise<T | null> => {
    setErrore(null)
    setOccupato(true)
    try {
      const r = await fn()
      if (!r.ok) {
        setErrore((r as any).body?.detail ?? t('db2.non_riuscito'))
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
    // Da una prova si arriva sempre sull'elenco, con dentro una voce che
    // l'elenco ha davvero. Tenere quello di prima quando non c'è più — altro
    // server, altri schemi — lascerebbe scritto sul selettore un nome che fra
    // le sue opzioni non compare.
    setScriviSchema(false)
    setSchema((prec) =>
      r.schemi.includes(prec.trim())
        ? prec.trim()
        : r.schemi.includes('public')
          ? 'public'
          : (r.schemi[0] ?? ''),
    )
    setPasso('schema')
  }, [con, url, modalita])

  const vaiAlleTabelle = useCallback(async () => {
    const r = await con(() =>
      window.scriba.post<PezzoDdl[]>('/database-remoto/anteprima', {
        schema_remoto: nomeSchema,
        prefisso,
        tabelle: scelte,
        crea_schema: daCreare,
      }),
    )
    if (r) setDdl(r)
    // Uno schema che ancora non esiste non ha tabelle da chiedere, e chiederle
    // significherebbe mostrare un errore per una risposta che si conosce già.
    if (!daCreare) {
      const t = await con(() =>
        window.scriba.post<string[]>('/database-remoto/tabelle', {
          url,
          modalita,
          schema_remoto: nomeSchema,
        }),
      )
      if (t) setTabelleRemote(t)
    } else {
      setTabelleRemote([])
    }
    setPasso('tabelle')
  }, [con, nomeSchema, daCreare, prefisso, scelte, url, modalita])

  // L'anteprima segue le spunte: cambiare idea su una tabella deve cambiare
  // quello che si sta per eseguire, non lasciare a schermo il DDL di prima.
  useEffect(() => {
    if (passo !== 'tabelle' || strada !== 'crea') return
    window.scriba
      .post<PezzoDdl[]>('/database-remoto/anteprima', {
        schema_remoto: nomeSchema,
        prefisso,
        tabelle: scelte,
        crea_schema: daCreare,
      })
      .then((r) => {
        if (r.ok) setDdl(r.body)
      })
  }, [passo, strada, nomeSchema, daCreare, prefisso, scelte])

  const creaTabelle = useCallback(async () => {
    const r = await con(() =>
      window.scriba.post<StatoDatabaseRemoto>('/database-remoto/crea', {
        url,
        modalita,
        schema_remoto: nomeSchema,
        prefisso,
        tabelle: scelte,
        crea_schema: daCreare,
      }),
    )
    if (!r) return
    setUrl('')
    setMostraUrl(false)
    await ricarica()
    setPasso('collegato')
  }, [con, url, modalita, nomeSchema, daCreare, prefisso, scelte, ricarica])

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
    setMostraUrl(false)
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
        ? t('db2.gia_sincronizzato')
        : t('db2.inviate', { n: r.sincronizzate, righe: r.righe }) +
            (r.fallite ? t('db2.fallite', { n: r.fallite, errore: r.errore ?? '' }) : '.'),
    )
  }, [con])

  const scollega = useCallback(async () => {
    if (!window.confirm(t('db2.scollegare'))) return
    await window.scriba.post('/database-remoto/scollega')
    setPasso('connessione')
    setEsitoSync(null)
    await ricarica()
  }, [ricarica])

  const alterna = (chiave: string) =>
    setScelte((prec) => (prec.includes(chiave) ? prec.filter((c) => c !== chiave) : [...prec, chiave]))

  return (
    <>
      <div className="settings__head">{t('db.titolo')}</div>
      <div className="settings__body">
        <p className="vis__nota">
          {t('db2.intro')}{' '}
          <b>{t('db.esce')}</b>
        </p>

        {errore && (
          <div className="alert alert--inline">
            <p>{errore}</p>
          </div>
        )}

        {stato?.segreto_in_chiaro && (
          <div className="alert alert--inline">
            <p>
              {t('db.in_chiaro')}
            </p>
          </div>
        )}

        {/* ---------------------------------------------------- collegato */}
        {passo === 'collegato' && stato?.collegato && (
          <>
            <div className="row">
              <div className="row__t">
                <b>{t('db.collegato')}</b>
                <span style={{ fontFamily: 'var(--font-code)' }}>
                  {stato.server?.utente}@{stato.server?.host}:{stato.server?.porta}/
                  {stato.server?.database} · schema {stato.schema} ·{' '}
                  {MODALITA.find((m) => m.id === stato.modalita)?.etichetta ?? stato.modalita}
                </span>
              </div>
              <button className="btn" onClick={scollega}>
                {t('db.scollega')}
              </button>
            </div>

            <div className="row">
              <div className="row__t">
                <b>{t('db.cosa_manda')}</b>
                <span>
                  {Object.entries(stato.tabelle)
                    .map(([k, v]) => `${modelloDati.find((t) => t.chiave === k)?.etichetta ?? k} → ${v.nome}`)
                    .join(' · ')}
                </span>
              </div>
              <button className="btn" onClick={() => setPasso('connessione')}>
                {t('db.cambia')}
              </button>
            </div>

            <div className="row">
              <div className="row__t">
                <b>{t('db.auto')}</b>
                <span>{t('db.auto_nota')}</span>
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
                {t(stato.automatico ? 'db2.attivo' : 'db2.spento')}
              </button>
            </div>

            <div className="row">
              <div className="row__t">
                <b>{t('db.pregresso')}</b>
                <span>{t('db.pregresso_nota')}</span>
              </div>
              <button className="btn" disabled={occupato} onClick={sincronizzaTutto}>
                {occupato ? t('db2.invio') : t('db2.sincronizza_tutto')}
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
                <b>{t('db.indirizzo')}</b>
                <span>
                  <code>postgresql://utente:password@host:5432/database</code>
                  {stato?.collegato && ` ${t('db2.lascialo_vuoto')}`}
                </span>
              </div>
            </div>
            <div className="secret">
              <input
                className="textfield"
                type={mostraUrl ? 'text' : 'password'}
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
              <button
                className="btn btn--icon"
                aria-pressed={mostraUrl}
                aria-label={t(mostraUrl ? 'db3.nascondi_indirizzo' : 'db3.mostra_indirizzo')}
                title={t(mostraUrl ? 'db3.nascondi_indirizzo' : 'db3.mostra_indirizzo')}
                onClick={() => setMostraUrl((prec) => !prec)}
              >
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">
                  <path d="M1.3 8S4 3.6 8 3.6 14.7 8 14.7 8 12 12.4 8 12.4 1.3 8 1.3 8Z" />
                  <circle cx="8" cy="8" r="1.9" />
                  {!mostraUrl && <path d="M3 13 13 3" />}
                </svg>
              </button>
            </div>

            <div className="row">
              <div className="row__t">
                <b>{t('db.come')}</b>
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
                <b>{t('db.prova')}</b>
                <span>{t('db.prova_nota')}</span>
              </div>
              <button className="btn" disabled={occupato || !url.trim()} onClick={provaConnessione}>
                {occupato ? t('db2.provo') : t('db2.prova')}
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
                <b>{t('db.schema')}</b>
                <span>{scriviSchema ? t('db3.schema_nuovo_nota') : t('db.schema_nota')}</span>
              </div>
              <div className="picker">
                <button
                  className={!scriviSchema ? 'is-on' : ''}
                  onClick={() => {
                    setScriviSchema(false)
                    // Tornando all'elenco si riparte da una voce che c'è:
                    // lasciare scritto un nome inesistente dentro un
                    // selettore mostrerebbe una scelta che il menù non ha.
                    setSchema((prec) =>
                      schemi.includes(prec.trim())
                        ? prec.trim()
                        : schemi.includes('public')
                          ? 'public'
                          : (schemi[0] ?? ''),
                    )
                  }}
                >
                  {t('db3.schema_esiste')}
                </button>
                <button
                  className={scriviSchema ? 'is-on' : ''}
                  onClick={() => {
                    setScriviSchema(true)
                    // Si riparte in bianco. Lasciando dentro `public`, preso
                    // dal menù di prima, il campo si presentava già pieno del
                    // nome che chi preme qui NON vuole — e subito sotto
                    // compariva «ce n'è già uno così», che sembra un rimprovero
                    // per qualcosa che nessuno ha ancora scritto.
                    setSchema('')
                    // Uno schema che ancora non c'è non contiene tabelle da
                    // mappare: l'unica strada che resta è farle creare.
                    setStrada('crea')
                  }}
                >
                  {t('db3.schema_nuovo')}
                </button>
              </div>
            </div>
            {scriviSchema ? (
              <div className="row">
                <div className="row__t">
                  {!daCreare && nomeSchema !== '' && (
                    <span>{t('db3.schema_esiste_gia')}</span>
                  )}
                </div>
                <input
                  className="textfield textfield--md"
                  style={{ maxWidth: 240 }}
                  value={schema}
                  placeholder="scriba"
                  aria-label={t('db3.nome_schema')}
                  onChange={(e) => setSchema(e.target.value)}
                />
              </div>
            ) : (
              <div className="row">
                <div className="row__t" />
                <Select
                  opzioni={schemi.map((s) => ({ id: s, etichetta: s }))}
                  selezionato={schema}
                  onScegli={setSchema}
                />
              </div>
            )}
            <div className="row">
              <div className="row__t">
                <b>{t('db.tabelle')}</b>
                <span>{daCreare ? t('db3.schema_vuoto') : t('db.tabelle_nota')}</span>
              </div>
              {/* Con uno schema da creare la scelta non esiste, e un selettore
                  con una sola risposta possibile è una domanda finta. */}
              {!daCreare && (
                <div className="picker">
                  <button className={strada === 'crea' ? 'is-on' : ''} onClick={() => setStrada('crea')}>
                    {t('db.creale')}
                  </button>
                  <button className={strada === 'mappa' ? 'is-on' : ''} onClick={() => setStrada('mappa')}>
                    {t('db.ce_le_ho')}
                  </button>
                </div>
              )}
            </div>
            <div className="row">
              <div className="row__t" />
              <button className="btn" disabled={occupato || !nomeSchema} onClick={vaiAlleTabelle}>
                {t('db.avanti')}
              </button>
            </div>
          </>
        )}

        {/* ------------------------------------------------------- tabelle */}
        {passo === 'tabelle' && (
          <>
            <div className="row">
              <div className="row__t">
                <b>{t('db.quali_dati')}</b>
                <span>{t('db.quali_dati_nota')}</span>
              </div>
              {strada === 'crea' && (
                <input
                  className="textfield"
                  style={{ maxWidth: 140 }}
                  value={prefisso}
                  onChange={(e) => setPrefisso(e.target.value)}
                  title={t('db.prefisso')}
                />
              )}
            </div>

            {modelloDati.map((tab) => (
              <div key={tab.chiave} className="cli__row">
                <button
                  className={`checkbox ${scelte.includes(tab.chiave) ? 'is-on' : ''}`}
                  onClick={() => alterna(tab.chiave)}
                  aria-label={tab.etichetta}
                >
                  {scelte.includes(tab.chiave) ? '✓' : ''}
                </button>
                <div className="row__t" style={{ flex: 1 }}>
                  <b>
                    {tab.etichetta}
                    {tab.voluminosa && ` ${t('db2.voluminosa')}`}
                  </b>
                  <span>{tab.descrizione}</span>
                </div>
                {strada === 'mappa' && scelte.includes(tab.chiave) && (
                  <Select
                    opzioni={[
                      { id: '', etichetta: t('db2.quale_tabella') },
                      ...tabelleRemote.map((n) => ({ id: n, etichetta: n })),
                    ]}
                    selezionato={mappa[tab.chiave]?.nome ?? ''}
                    onScegli={(v) => caricaColonne(tab.chiave, v)}
                    larghezza={240}
                  />
                )}
              </div>
            ))}

            {strada === 'crea' ? (
              <>
                <div className="row">
                  <div className="row__t">
                    <b>{t('db.ddl')}</b>
                    <span>{t('db.ddl_nota')}</span>
                  </div>
                </div>
                <pre className="ddl">{ddl.map((p) => p.sql).join(';\n\n')}</pre>
                <div className="row">
                  <div className="row__t" />
                  <button className="btn" onClick={() => setPasso('schema')}>
                    {t('db.indietro')}
                  </button>
                  <button
                    className="btn btn--rec"
                    disabled={occupato || scelte.length === 0}
                    onClick={creaTabelle}
                  >
                    {occupato ? t('db2.creo') : t('db2.crea_collega')}
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
                  {t('db.chiave_nota_1')} <b>*</b> {t('db.chiave_nota_2')}
                </p>
                <div className="row">
                  <div className="row__t" />
                  <button className="btn" onClick={() => setPasso('schema')}>
                    {t('db.indietro')}
                  </button>
                  <button className="btn btn--rec" disabled={occupato} onClick={collegaMappa}>
                    {occupato ? t('db2.collego') : t('db2.collega')}
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
