/**
 * Clienti: l'anagrafica a cui si attribuiscono le call.
 *
 * L'attribuzione vera si fa dall'archivio, riga per riga, dove si hanno davanti
 * tutte le call insieme. Qui si tiene l'elenco: crearli, rinominarli,
 * archiviarli, e caricarne un file invece di batterli a mano uno per uno.
 *
 * Archiviare invece che eliminare, per il caso normale: un cliente con cui non
 * si lavora più deve sparire dai menu, ma le sue call restano attribuite a
 * qualcuno. Eliminare c'è lo stesso — è la scelta di chi ha sbagliato a
 * crearlo — e dice prima cosa succede alle call.
 */

import { useCallback, useRef, useState } from 'react'

import type { Cliente, EsitoImport } from '../tipi'
import { useLocale, useT, type Traduci } from '../lingua'

/** «14 ago 2026». Le call qui si contano, non si aprono: basta il giorno. */
function quando(ms: number | null, t: Traduci, locale: string): string {
  if (ms == null) return t('cli2.mai')
  return new Date(ms)
    .toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })
    .replace('.', '')
}

function riepilogoImport(e: EsitoImport, t: Traduci): string {
  const pezzi: string[] = []
  if (e.creati) pezzi.push(t(e.creati === 1 ? 'cli2.aggiunto' : 'cli2.aggiunti', { n: e.creati }))
  if (e.gia_presenti)
    pezzi.push(t(e.gia_presenti === 1 ? 'cli2.presente' : 'cli2.presenti', { n: e.gia_presenti }))
  if (e.scartati) pezzi.push(t(e.scartati === 1 ? 'cli2.scartata' : 'cli2.scartate', { n: e.scartati }))
  return pezzi.length ? pezzi.join(', ') : t('cli2.niente')
}

export function SezioneClienti({
  clienti,
  onRicarica,
}: {
  clienti: Cliente[]
  onRicarica: () => void
}) {
  const t = useT()
  const locale = useLocale()
  const [nuovo, setNuovo] = useState('')
  const [errore, setErrore] = useState<string | null>(null)
  const [esito, setEsito] = useState<string | null>(null)
  const [inModifica, setInModifica] = useState<number | null>(null)
  const [bozza, setBozza] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const aggiungi = useCallback(async () => {
    setErrore(null)
    setEsito(null)
    const r = await window.scriba.post<{ id: number }>('/clienti', { nome: nuovo })
    if (!r.ok) {
      setErrore(t('cli2.nome_vuoto'))
      return
    }
    setNuovo('')
    onRicarica()
  }, [nuovo, onRicarica])

  const rinomina = useCallback(
    async (id: number) => {
      setErrore(null)
      const r = await window.scriba.patch(`/clienti/${id}`, { nome: bozza })
      if (!r.ok) {
        setErrore(t('cli2.nome_non_cambiato'))
        return
      }
      setInModifica(null)
      onRicarica()
    },
    [bozza, onRicarica],
  )

  const archivia = useCallback(
    async (c: Cliente) => {
      await window.scriba.patch(`/clienti/${c.id}`, { archiviato: !c.archiviato })
      onRicarica()
    },
    [onRicarica],
  )

  const elimina = useCallback(
    async (c: Cliente) => {
      // Le call non si toccano, e va detto prima: chi elimina un cliente non
      // deve chiedersi se si sta portando via il lavoro.
      const avviso =
        c.n_call > 0
          ? t('cli2.eliminare_con_call', { nome: c.nome, n: c.n_call })
          : t('cli2.eliminare', { nome: c.nome })
      if (!window.confirm(avviso)) return
      await window.scriba.post(`/clienti/${c.id}/elimina`)
      onRicarica()
    },
    [onRicarica],
  )

  const importa = useCallback(
    async (file: File) => {
      setErrore(null)
      setEsito(null)
      const testo = await file.text()
      const r = await window.scriba.post<EsitoImport>('/clienti/importa', { csv: testo })
      if (!r.ok) {
        setErrore(t('cli2.nessun_nome_nel_file'))
        return
      }
      setEsito(riepilogoImport(r.body, t))
      onRicarica()
    },
    [onRicarica],
  )

  return (
    <>
      <div className="settings__head">{t('cli.titolo')}</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__t">
            <b>{t('cli.aggiungi')}</b>
            <span>
              {t('cli.aggiungi_nota')}
            </span>
          </div>
          <input
            className="textfield textfield--md"
            style={{ maxWidth: 220 }}
            value={nuovo}
            placeholder={t('cli.ph_nome')}
            onChange={(e) => setNuovo(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') aggiungi()
            }}
          />
          <button className="btn" disabled={!nuovo.trim()} onClick={aggiungi}>
            {t('cli.aggiungi_btn')}
          </button>
        </div>

        <div className="row">
          <div className="row__t">
            <b>{t('cli.carica')}</b>
            <span>
              {t('cli2.csv_nota')}
            </span>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv,text/plain"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) importa(f)
              // Azzerato perché ricaricare lo stesso file di seguito emetta di
              // nuovo l'evento: senza, un secondo tentativo sembra ignorato.
              e.target.value = ''
            }}
          />
          <button className="btn" onClick={() => fileRef.current?.click()}>
            {t('cli.scegli_file')}
          </button>
        </div>

        {errore && <div className="alert alert--inline"><p>{errore}</p></div>}
        {esito && (
          <p style={{ fontSize: 'var(--fs-md)', color: 'var(--fg-2)', margin: 0 }}>{esito}</p>
        )}

        {clienti.length === 0 ? (
          <p style={{ fontSize: 'var(--fs-md)', color: 'var(--fg-3)', lineHeight: 1.6 }}>
            {t('cli.vuoto')}
          </p>
        ) : (
          <div className="cli">
            {clienti.map((c) => (
              <div key={c.id} className={`cli__row ${c.archiviato ? 'is-off' : ''}`}>
                {inModifica === c.id ? (
                  <>
                    <input
                      className="textfield textfield--md"
                      style={{ maxWidth: 260 }}
                      value={bozza}
                      autoFocus
                      onChange={(e) => setBozza(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') rinomina(c.id)
                        if (e.key === 'Escape') setInModifica(null)
                      }}
                    />
                    <button className="btn btn--sm" onClick={() => rinomina(c.id)}>
                      {t('cli.salva')}
                    </button>
                    <button className="btn btn--sm" onClick={() => setInModifica(null)}>
                      {t('cli.annulla')}
                    </button>
                  </>
                ) : (
                  <>
                    <span className="cli__nome">{c.nome}</span>
                    <span className="cli__meta">
                      {c.n_call} {c.n_call === 1 ? 'call' : 'call'}
                      <span>·</span>
                      {t('cli2.ultima')} {quando(c.ultima_call, t, locale)}
                      {c.archiviato ? <span> {t('cli.archiviato')}</span> : null}
                    </span>
                    <button
                      className="btn btn--sm"
                      onClick={() => {
                        setInModifica(c.id)
                        setBozza(c.nome)
                        setErrore(null)
                      }}
                    >
                      {t('cli.rinomina')}
                    </button>
                    <button className="btn btn--sm" onClick={() => archivia(c)}>
                      {c.archiviato ? 'Ripristina' : 'Archivia'}
                    </button>
                    <button className="btn btn--sm" onClick={() => elimina(c)}>
                      {t('cli.elimina')}
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
