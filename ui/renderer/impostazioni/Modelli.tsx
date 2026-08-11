/**
 * Modelli locali: trascrizione e analisi, con lo spazio su disco in testa.
 *
 * Tre regole vincolanti da comportamento.md e contratto-api.md, non solo
 * dal disegno: un download si sospende e riprende dal punto in cui era
 * (anche dopo aver chiuso l'app), lo spazio si controlla PRIMA di partire,
 * e la verifica d'integrità è uno stato visibile (`in_verifica`), non un
 * passaggio muto. L'avanzamento arriva dall'evento `modello_locale` sul
 * websocket — questo componente si limita a mostrare la lista che il
 * genitore tiene aggiornata, non interroga niente.
 */

import { Fragment } from 'react'

import type { Disco, Modello } from '../tipi'
import { dataBreve, dimensione } from '../tipi'
import { etichettaValore, useLocale, useT, type Chiave, type Traduci } from '../lingua'

function tempoRimanente(secondi: number, t: Traduci): string {
  if (secondi < 60) return t('mod2.secondi', { n: Math.round(secondi) })
  return t('mod2.minuti', { n: Math.round(secondi / 60) })
}

/** Le voci di una riga di `meta`, separate dal punto del sistema. */
function separa(voci: string[]): React.ReactNode[] {
  return voci.map((v, i) => (
    <Fragment key={i}>
      {i > 0 && <span className="call__sep">·</span>}
      <span>{v}</span>
    </Fragment>
  ))
}

function classeStato(stato: Modello['stato']): string {
  if (stato === 'installato' || stato === 'in_uso') return 'is-ok'
  if (stato === 'in_avvio') return 'is-busy'
  if (stato === 'in_download' || stato === 'in_pausa' || stato === 'in_verifica') return 'is-busy'
  if (stato === 'spazio_insufficiente' || stato === 'errore') return 'is-err'
  return ''
}

export function SezioneModelli({
  disco,
  modelli,
  onScarica,
  onSospendi,
  onElimina,
  onAvvia,
  onFerma,
  onApriCartella,
}: {
  disco: Disco | null
  modelli: Modello[]
  onScarica: (id: string) => void
  onSospendi: (id: string) => void
  onElimina: (id: string) => void
  onAvvia: (id: string) => void
  onFerma: (id: string) => void
  onApriCartella: () => void
}) {
  const t = useT()
  const locale = useLocale()
  const percentualeUsata = disco
    ? Math.min(100, Math.round(((disco.totale_bytes - disco.libero_bytes) / Math.max(1, disco.totale_bytes)) * 100))
    : 0

  return (
    <>
      <div className="settings__head">{t('mod.titolo')}</div>
      <div className="settings__body">
        {disco && (
          <div className="disk">
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--fs-md)' }}>
                <span style={{ color: 'var(--fg-2)' }}>{t('mod.spazio')}</span>
                <span style={{ color: 'var(--fg-body)' }}>
                  {t('mod2.liberi_di', {
                    liberi: dimensione(disco.libero_bytes, locale),
                    totale: dimensione(disco.totale_bytes, locale),
                  })}
                </span>
              </div>
              <div className="disk__bar">
                <i style={{ width: `${percentualeUsata}%` }} />
              </div>
            </div>
            <button className="btn" onClick={onApriCartella}>
              {t('mod.apri_cartella')}
            </button>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
          {modelli.map((m) => (
            <RigaModello
              key={m.id}
              m={m}
              disco={disco}
              onScarica={() => onScarica(m.id)}
              onSospendi={() => onSospendi(m.id)}
              onElimina={() => onElimina(m.id)}
              onAvvia={() => onAvvia(m.id)}
              onFerma={() => onFerma(m.id)}
            />
          ))}
        </div>

        <p>
          {t('mod.download_nota')}
        </p>
      </div>
    </>
  )
}

function RigaModello({
  m,
  disco,
  onScarica,
  onSospendi,
  onElimina,
  onAvvia,
  onFerma,
}: {
  m: Modello
  disco: Disco | null
  onScarica: () => void
  onSospendi: () => void
  onElimina: () => void
  onAvvia: () => void
  onFerma: () => void
}) {
  const t = useT()
  const locale = useLocale()
  const percentualeScaricata = m.size_bytes > 0 ? Math.round((m.scaricati_bytes / m.size_bytes) * 100) : 0
  const mancano = disco ? Math.max(0, m.size_bytes - disco.libero_bytes) : null

  /* La riga com'è disegnata nel handoff 1.0: nome, descrizione e una riga di
     `meta` a sinistra, lo stato a destra, i comandi in fondo. Prima nome, uso
     e dimensione erano tre voci pari, con `.model__name`, `.model__use`,
     `.model__size`, `.model__bar` — nomi del design vecchio, che nel foglio
     1.0 non esistono più: quella riga usciva senza stile (#86). */
  const comandi: Array<{ chiave: Chiave; onClick: () => void; primaria?: boolean }> = []
  if (m.stato === 'non_installato') comandi.push({ chiave: 'mod.scarica', onClick: onScarica, primaria: true })
  if (m.stato === 'in_download') comandi.push({ chiave: 'mod.sospendi', onClick: onSospendi })
  if (m.stato === 'in_pausa') comandi.push({ chiave: 'mod.riprendi', onClick: onScarica })
  if (m.stato === 'installato' && m.uso === 'analisi') comandi.push({ chiave: 'mod.avvia', onClick: onAvvia })
  if (m.stato === 'installato') comandi.push({ chiave: 'mod.elimina', onClick: onElimina })
  if (m.stato === 'in_uso' || m.stato === 'in_avvio') comandi.push({ chiave: 'mod.ferma', onClick: onFerma })
  if (m.stato === 'spazio_insufficiente' || m.stato === 'errore') {
    comandi.push({ chiave: 'mod.scarica', onClick: onScarica })
  }

  /** La riga sotto il nome: quanto pesa, a cosa serve, e cosa sta facendo. */
  const meta: string[] = [dimensione(m.size_bytes, locale), etichettaValore(t, 'uso', m.uso)]
  if (m.stato === 'installato' && m.installato_at != null) {
    meta.push(t('mod2.installato_il', { data: dataBreve(m.installato_at, locale, t('data.oggi')) }))
  }
  if (m.stato === 'in_uso') {
    if (m.endpoint) meta.push(m.endpoint)
    if (m.ram_bytes != null) meta.push(t('mod2.ram', { ram: dimensione(m.ram_bytes, locale) }))
  }
  if (m.stato === 'in_avvio') {
    meta.push(t('mod2.in_memoria'))
    if (m.ram_bytes != null) meta.push(t('mod2.ram_finora', { ram: dimensione(m.ram_bytes, locale) }))
  }
  if (m.stato === 'spazio_insufficiente') {
    meta.push(
      t('mod2.servono', {
        servono: dimensione(m.size_bytes, locale),
        restano: disco ? dimensione(disco.libero_bytes, locale) : '—',
      }),
    )
  }

  /* Sotto la barra: quanto è sceso e quanto manca. Per la verifica la nota del
     core ha la precedenza — per i modelli affidati a una libreria esterna lì
     non si sta controllando un hash, si sta ancora scaricando, e una riga che
     descrive la cosa sbagliata è peggio di una riga assente. */
  let scaricamento: string[] | null = null
  if (m.stato === 'in_download' || m.stato === 'in_pausa') {
    scaricamento = [
      t('mod2.scaricati', {
        fatti: dimensione(m.scaricati_bytes, locale),
        totale: dimensione(m.size_bytes, locale),
      }),
    ]
    if (m.stato === 'in_pausa') scaricamento.push(etichettaValore(t, 'mod_stato', 'in_pausa'))
    else {
      if (m.velocita_bps != null) scaricamento.push(`${dimensione(m.velocita_bps, locale)}/s`)
      if (m.secondi_rimanenti != null) scaricamento.push(tempoRimanente(m.secondi_rimanenti, t))
    }
  } else if (m.stato === 'in_verifica') {
    scaricamento = [m.nota || t('mod2.integrita')]
  }

  return (
    <div className="model">
      <div className="model__top">
        <div className="model__testo">
          <span className="model__n">{m.nome}</span>
          {m.nota && m.stato !== 'in_verifica' && <span className="model__d">{m.nota}</span>}
          <div className="model__meta">{separa(meta)}</div>
        </div>
        <span className={`model__state ${classeStato(m.stato)}`}>
          {etichettaValore(t, 'mod_stato', m.stato)}
        </span>
        {comandi.map((c) => (
          <button
            key={c.chiave}
            className={`btn btn--sm${c.primaria ? ' btn--primary' : ''}`}
            onClick={c.onClick}
          >
            {t(c.chiave)}
          </button>
        ))}
      </div>

      {scaricamento && (
        <div className="model__dl">
          {/* In verifica la barra è piena: nessuna percentuale inventata, lo
              stato lo dice l'etichetta. */}
          <div className="progress">
            <i style={{ width: m.stato === 'in_verifica' ? '100%' : `${percentualeScaricata}%` }} />
          </div>
          <div className="model__dlmeta">{separa(scaricamento)}</div>
        </div>
      )}

      {m.stato === 'spazio_insufficiente' && (
        <p className="model__err">
          {t('mod2.non_parte', {
            mancano: mancano != null ? dimensione(mancano, locale) : t('mod2.alcuni_gb'),
          })}
        </p>
      )}
      {m.stato === 'errore' && m.errore && <p className="model__err">{m.errore}</p>}
    </div>
  )
}
