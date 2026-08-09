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

/** «14 ago 2026». Le call qui si contano, non si aprono: basta il giorno. */
function quando(ms: number | null): string {
  if (ms == null) return 'mai'
  return new Date(ms)
    .toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' })
    .replace('.', '')
}

function riepilogoImport(e: EsitoImport): string {
  const pezzi: string[] = []
  if (e.creati) pezzi.push(`${e.creati} ${e.creati === 1 ? 'aggiunto' : 'aggiunti'}`)
  if (e.gia_presenti) pezzi.push(`${e.gia_presenti} ${e.gia_presenti === 1 ? 'già presente' : 'già presenti'}`)
  if (e.scartati) pezzi.push(`${e.scartati} ${e.scartati === 1 ? 'riga senza nome' : 'righe senza nome'}`)
  return pezzi.length ? pezzi.join(', ') : 'niente da aggiungere'
}

export function SezioneClienti({
  clienti,
  onRicarica,
}: {
  clienti: Cliente[]
  onRicarica: () => void
}) {
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
      setErrore('Il nome non può essere vuoto.')
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
        setErrore('Nome non cambiato: è vuoto, oppure è già di un altro cliente.')
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
          ? `Eliminare «${c.nome}»? Le sue ${c.n_call} call restano, ma senza cliente.`
          : `Eliminare «${c.nome}»?`
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
        setErrore('Nessun nome trovato nel file: serve almeno una colonna con i nomi.')
        return
      }
      setEsito(riepilogoImport(r.body))
      onRicarica()
    },
    [onRicarica],
  )

  return (
    <>
      <div className="settings__head">Clienti</div>
      <div className="settings__body">
        <div className="row">
          <div className="row__text">
            <b>Aggiungi un cliente</b>
            <span>
              Serve a raggruppare le call nell'archivio. L'attribuzione si fa da lì, dove le call
              si vedono tutte insieme.
            </span>
          </div>
          <input
            className="arch__search"
            style={{ maxWidth: 220 }}
            value={nuovo}
            placeholder="Nome"
            onChange={(e) => setNuovo(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') aggiungi()
            }}
          />
          <button className="btn" disabled={!nuovo.trim()} onClick={aggiungi}>
            Aggiungi
          </button>
        </div>

        <div className="row">
          <div className="row__text">
            <b>Carica un elenco</b>
            <span>
              Un file CSV con una colonna dei nomi (e, se c'è, una delle note). Separatore virgola o
              punto e virgola. I clienti già presenti non vengono duplicati né sovrascritti.
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
            Scegli un file
          </button>
        </div>

        {errore && <div className="alert alert--inline"><p>{errore}</p></div>}
        {esito && (
          <p style={{ fontSize: 'var(--fs-md)', color: 'var(--fg-2)', margin: 0 }}>{esito}</p>
        )}

        {clienti.length === 0 ? (
          <p style={{ fontSize: 'var(--fs-md)', color: 'var(--fg-3)', lineHeight: 1.6 }}>
            Nessun cliente. Finché non ce n'è, l'archivio funziona lo stesso: le call restano
            cercabili per testo e per data.
          </p>
        ) : (
          <div className="cli">
            {clienti.map((c) => (
              <div key={c.id} className={`cli__row ${c.archiviato ? 'is-off' : ''}`}>
                {inModifica === c.id ? (
                  <>
                    <input
                      className="arch__search"
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
                      Salva
                    </button>
                    <button className="btn btn--sm" onClick={() => setInModifica(null)}>
                      Annulla
                    </button>
                  </>
                ) : (
                  <>
                    <span className="cli__nome">{c.nome}</span>
                    <span className="cli__meta">
                      {c.n_call} {c.n_call === 1 ? 'call' : 'call'}
                      <span>·</span>
                      ultima: {quando(c.ultima_call)}
                      {c.archiviato ? <span> · archiviato</span> : null}
                    </span>
                    <button
                      className="btn btn--sm"
                      onClick={() => {
                        setInModifica(c.id)
                        setBozza(c.nome)
                        setErrore(null)
                      }}
                    >
                      Rinomina
                    </button>
                    <button className="btn btn--sm" onClick={() => archivia(c)}>
                      {c.archiviato ? 'Ripristina' : 'Archivia'}
                    </button>
                    <button className="btn btn--sm" onClick={() => elimina(c)}>
                      Elimina
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
