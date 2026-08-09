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

import type { Disco, Modello } from '../tipi'
import { dataBreve, dimensione } from '../tipi'
import { etichettaValore, useLocale, useT, type Traduci } from '../lingua'

function tempoRimanente(secondi: number, t: Traduci): string {
  if (secondi < 60) return t('mod2.secondi', { n: Math.round(secondi) })
  return t('mod2.minuti', { n: Math.round(secondi / 60) })
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

  return (
    <div className="model">
      <div className="model__top">
        <span className="model__name">{m.nome}</span>
        <span className="model__use">{m.uso}</span>
        <span className="model__size">{dimensione(m.size_bytes, locale)}</span>
        <span className={`model__state ${classeStato(m.stato)}`}>{etichettaValore(t, 'mod_stato', m.stato)}</span>

        {m.stato === 'non_installato' && (
          <button className="btn btn--sm btn--primary" onClick={onScarica}>
            {t('mod.scarica')}
          </button>
        )}
        {m.stato === 'in_download' && (
          <button className="btn btn--sm" onClick={onSospendi}>
            {t('mod.sospendi')}
          </button>
        )}
        {m.stato === 'in_pausa' && (
          <button className="btn btn--sm" onClick={onScarica}>
            {t('mod.riprendi')}
          </button>
        )}
        {m.stato === 'installato' && m.uso === 'analisi' && (
          <button className="btn btn--sm" onClick={onAvvia}>
            {t('mod.avvia')}
          </button>
        )}
        {m.stato === 'installato' && (
          <button className="btn btn--sm" onClick={onElimina}>
            {t('mod.elimina')}
          </button>
        )}
        {(m.stato === 'in_uso' || m.stato === 'in_avvio') && (
          <button className="btn btn--sm" onClick={onFerma}>
            {t('mod.ferma')}
          </button>
        )}
        {(m.stato === 'spazio_insufficiente' || m.stato === 'errore') && (
          <button className="btn btn--sm" onClick={onScarica}>
            {t('mod.scarica')}
          </button>
        )}
      </div>

      {(m.stato === 'in_download' || m.stato === 'in_pausa') && (
        <div className="model__bar">
          <i style={{ width: `${percentualeScaricata}%` }} />
        </div>
      )}
      {/* La verifica è uno stato visibile, non un passaggio silenzioso: niente
          percentuale finta, la barra piena più l'etichetta bastano a dirlo. */}
      {m.stato === 'in_verifica' && (
        <div className="model__bar">
          <i style={{ width: '100%' }} />
        </div>
      )}

      {m.stato === 'in_download' && (
        <span className="model__meta">
          {t('mod2.scaricati', {
            fatti: dimensione(m.scaricati_bytes, locale),
            totale: dimensione(m.size_bytes, locale),
          })}
          {m.velocita_bps != null ? ` · ${dimensione(m.velocita_bps, locale)}/s` : ''}
          {m.secondi_rimanenti != null ? ` · ${tempoRimanente(m.secondi_rimanenti, t)}` : ''}
        </span>
      )}
      {m.stato === 'in_pausa' && (
        <span className="model__meta">
          {t('mod2.scaricati', {
            fatti: dimensione(m.scaricati_bytes, locale),
            totale: dimensione(m.size_bytes, locale),
          })}{' · '}
          {etichettaValore(t, 'mod_stato', 'in_pausa')}
        </span>
      )}
      {/* La nota del core ha la precedenza: non tutti i modelli si scaricano
          allo stesso modo, e per quelli affidati a una libreria esterna qui
          non si sta verificando un hash — si sta ancora scaricando. Il testo
          fisso vale solo quando il core non ha niente di più preciso da dire. */}
      {m.stato === 'in_verifica' && (
        <span className="model__meta">{m.nota || t('mod2.integrita')}</span>
      )}
      {m.stato === 'installato' && m.installato_at != null && (
        <span className="model__meta">{t('mod2.installato_il', { data: dataBreve(m.installato_at, locale, t('data.oggi')) })}</span>
      )}
      {m.stato === 'in_avvio' && (
        <span className="model__meta">
          {t('mod2.in_memoria')}
          {m.ram_bytes != null ? ` · ${t('mod2.ram_finora', { ram: dimensione(m.ram_bytes, locale) })}` : ''}
        </span>
      )}
      {m.stato === 'in_uso' && (
        <span className="model__meta">
          {t('mod2.avviato')}
          {m.endpoint ? ` · ${m.endpoint}` : ''}
          {m.ram_bytes != null ? ` · ${t('mod2.ram', { ram: dimensione(m.ram_bytes, locale) })}` : ''}
        </span>
      )}
      {m.stato === 'non_installato' && m.nota && <span className="model__meta">{m.nota}</span>}

      {m.stato === 'spazio_insufficiente' && (
        <>
          <span className="model__meta">
            {t('mod2.servono', {
              servono: dimensione(m.size_bytes, locale),
              restano: disco ? dimensione(disco.libero_bytes, locale) : '—',
            })}
          </span>
          <p className="model__err">
            {t('mod2.non_parte', {
              mancano: mancano != null ? dimensione(mancano, locale) : t('mod2.alcuni_gb'),
            })}
          </p>
        </>
      )}
      {m.stato === 'errore' && m.errore && <p className="model__err">{m.errore}</p>}
    </div>
  )
}
