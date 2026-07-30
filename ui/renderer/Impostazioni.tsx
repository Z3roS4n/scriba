/**
 * Finestra Impostazioni.
 *
 * Non è più un dialogo dentro la finestra principale: è una finestra a sé,
 * con la sua barra del titolo e otto sezioni raggiungibili dalla barra
 * laterale (handoff/impostazioni.html). Ogni impostazione viene salvata
 * davvero con `POST /settings` e riletta con `GET /settings` — uno stato
 * che vive solo in React e sparisce alla chiusura sarebbe peggio di niente.
 *
 * Il montaggio della finestra sta in `avvio-impostazioni.tsx`. Il nome esteso
 * non è un vezzo: NTFS qui non distingue maiuscole e minuscole, quindi un
 * `impostazioni.tsx` sarebbe finito sullo stesso file di questo.
 */

import { useCallback, useEffect, useState } from 'react'

import type { Disco, Dispositivi, Impostazioni as ImpostazioniT, Modello, Provider, Sessione, VoceDati } from './tipi'
import { SezioneAnalisi } from './impostazioni/Analisi'
import { SezioneDati } from './impostazioni/Dati'
import { SezioneExport } from './impostazioni/Export'
import { SezioneModelli } from './impostazioni/Modelli'
import { SezioneMotore } from './impostazioni/Motore'
import { SezioneRilevamento } from './impostazioni/Rilevamento'
import { SezioneScorciatoie } from './impostazioni/Scorciatoie'
import { SezioneTrascrizione } from './impostazioni/Trascrizione'

type Sezione =
  | 'motore'
  | 'modelli'
  | 'trascrizione'
  | 'rilevamento'
  | 'scorciatoie'
  | 'analisi'
  | 'dati'
  | 'export'

const NAV: { id: Sezione; etichetta: string }[] = [
  { id: 'motore', etichetta: 'Motore di analisi' },
  { id: 'modelli', etichetta: 'Modelli locali' },
  { id: 'trascrizione', etichetta: 'Trascrizione' },
  { id: 'rilevamento', etichetta: 'Rilevamento call' },
  { id: 'scorciatoie', etichetta: 'Scorciatoie' },
  { id: 'analisi', etichetta: 'Analisi' },
  { id: 'dati', etichetta: 'Dati e privacy' },
  { id: 'export', etichetta: 'Export' },
]

function Topbar() {
  return (
    <header className="topbar">
      <span className="brand">Impostazioni</span>
      <div className="topbar__spacer" />
      <div className="wincontrols">
        <button onClick={() => window.scriba.finestra.riduci()}>—</button>
        <button onClick={() => window.scriba.finestra.chiudi()}>✕</button>
      </div>
    </header>
  )
}

export function Impostazioni() {
  const [sezione, setSezione] = useState<Sezione>('motore')
  const [impostazioni, setImpostazioni] = useState<ImpostazioniT | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [dispositivi, setDispositivi] = useState<Dispositivi | null>(null)
  const [disco, setDisco] = useState<Disco | null>(null)
  const [modelli, setModelli] = useState<Modello[]>([])
  const [dati, setDati] = useState<VoceDati[]>([])
  const [errore, setErrore] = useState<string | null>(null)

  const carica = useCallback(async () => {
    // Tutto in una volta: è una finestra di impostazioni, non lo schermo
    // principale durante una call, quindi non c'è motivo di rimandare il
    // caricamento di una sezione a quando viene aperta.
    const [s, p, d, disc, mod, dt] = await Promise.all([
      window.scriba.get<ImpostazioniT>('/settings'),
      window.scriba.get<Provider[]>('/providers'),
      window.scriba.get<Dispositivi>('/dispositivi'),
      window.scriba.get<Disco>('/disco'),
      window.scriba.get<Modello[]>('/modelli'),
      window.scriba.get<VoceDati[]>('/dati'),
    ])
    if (s.ok) setImpostazioni(s.body)
    if (p.ok) setProviders(p.body)
    if (d.ok) setDispositivi(d.body)
    if (disc.ok) setDisco(disc.body)
    if (mod.ok) setModelli(mod.body)
    if (dt.ok) setDati(dt.body)
  }, [])

  useEffect(() => {
    carica()
  }, [carica])

  // L'avanzamento di un download arriva da qui, non da un'interrogazione al
  // secondo: un download dura fino a un'ora, e chiedere ogni secondo per
  // un'ora sarebbe assurdo (contratto-api.md). Il payload dell'evento non è
  // tipato a monte — come `transcript` in overlay.tsx e index.tsx — quindi
  // si legge `any` e si affida alla forma dichiarata in tipi.ts.
  useEffect(() => {
    return window.scriba.on('core:event', (ev: any) => {
      if (ev?.type === 'modello_locale' && ev.modello) {
        const aggiornato: Modello = ev.modello
        setModelli((prec) => {
          const i = prec.findIndex((m) => m.id === aggiornato.id)
          if (i < 0) return [...prec, aggiornato]
          return prec.map((m, k) => (k === i ? aggiornato : m))
        })
        // Anche i motori: la disponibilità del modello locale la decide il
        // core interrogando il server appena avviato, e questo evento è il
        // momento in cui la risposta cambia. Senza, «Modello locale» restava
        // «non disponibile» finché non si chiudeva e riapriva la finestra.
        if (aggiornato.uso === 'analisi') {
          window.scriba.get<Provider[]>('/providers').then((r) => {
            if (r.ok) setProviders(r.body)
          })
        }
      }
    })
  }, [])

  /** Salva una porzione di impostazioni e rilegge lo stato vero dal core,
   *  invece di fidarsi solo dell'aggiornamento ottimistico in memoria. */
  const salva = useCallback(async (patch: Partial<ImpostazioniT>): Promise<boolean> => {
    setErrore(null)
    const r = await window.scriba.post('/settings', patch)
    if (!r.ok) {
      setErrore(`Impostazione non salvata (${r.status}).`)
      return false
    }
    const fresca = await window.scriba.get<ImpostazioniT>('/settings')
    if (fresca.ok) setImpostazioni(fresca.body)
    return true
  }, [])

  const scegliProvider = useCallback(
    (p: Provider) =>
      salva({
        llm: {
          provider: p.id,
          model: p.model,
          base_url: impostazioni?.llm.base_url ?? '',
          api_key_presente: impostazioni?.llm.api_key_presente ?? false,
        },
      }),
    [salva, impostazioni],
  )

  /** La forma esatta del payload per la chiave non è nella tabella di
   *  contratto-api.md (che parla solo di `llm.api_key_presente`, un booleano
   *  di sola lettura): si assume che il core accetti `llm.api_key` in
   *  scrittura, sullo stesso modello di `provider`/`model`. Da verificare
   *  quando quella rotta sarà pronta. */
  const salvaChiave = useCallback(async (p: Provider, chiave: string): Promise<boolean> => {
    setErrore(null)
    const r = await window.scriba.post('/settings', { llm: { provider: p.id, api_key: chiave } })
    if (!r.ok) {
      setErrore(`Chiave non salvata (${r.status}).`)
      return false
    }
    const [pr, fresca] = await Promise.all([
      window.scriba.get<Provider[]>('/providers'),
      window.scriba.get<ImpostazioniT>('/settings'),
    ])
    if (pr.ok) setProviders(pr.body)
    if (fresca.ok) setImpostazioni(fresca.body)
    return true
  }, [])

  const scarica = useCallback((id: string) => window.scriba.post(`/modelli/${id}/scarica`), [])
  const sospendi = useCallback((id: string) => window.scriba.post(`/modelli/${id}/sospendi`), [])
  const avvia = useCallback((id: string) => window.scriba.post(`/modelli/${id}/avvia`), [])
  const ferma = useCallback((id: string) => window.scriba.post(`/modelli/${id}/ferma`), [])
  const eliminaModello = useCallback(async (id: string) => {
    const r = await window.scriba.post(`/modelli/${id}/elimina`)
    if (r.ok) setModelli((prec) => prec.filter((m) => m.id !== id))
  }, [])

  const eliminaAudio = useCallback(async (): Promise<boolean> => {
    const r = await window.scriba.post('/dati/elimina-audio')
    if (!r.ok) {
      setErrore(`Audio non eliminato (${r.status}).`)
      return false
    }
    const dt = await window.scriba.get<VoceDati[]>('/dati')
    if (dt.ok) setDati(dt.body)
    return true
  }, [])

  const eliminaCall = useCallback(async (id: number): Promise<boolean> => {
    const r = await window.scriba.post(`/sessions/${id}/elimina`)
    if (!r.ok) {
      setErrore(`Call non eliminata (${r.status}).`)
      return false
    }
    const dt = await window.scriba.get<VoceDati[]>('/dati')
    if (dt.ok) setDati(dt.body)
    return true
  }, [])

  const caricaSessioni = useCallback(async (): Promise<Sessione[]> => {
    const r = await window.scriba.get<Sessione[]>('/sessions')
    return r.ok ? r.body : []
  }, [])

  const cambiaCartellaExport = useCallback(async () => {
    const cartella = await window.scriba.scegliCartella()
    if (cartella) {
      await salva({ export: { cartella, formato: impostazioni?.export?.formato ?? 'markdown' } })
    }
  }, [salva, impostazioni])

  if (!impostazioni) {
    return (
      <div className="win settings">
        <Topbar />
        <div className="win__body">
          <div className="settings__main">
            <div className="settings__body">
              <p>Caricamento delle impostazioni…</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="win settings">
      <Topbar />
      {errore && (
        <div className="notice notice--error">
          <span>{errore}</span>
          <div className="notice__spacer" />
          <button className="btn btn--sm" onClick={() => setErrore(null)}>
            Chiudi
          </button>
        </div>
      )}
      <div className="win__body">
        <nav className="settings__nav">
          {NAV.map((n) => (
            <button
              key={n.id}
              className={`navitem ${sezione === n.id ? 'is-active' : ''}`}
              onClick={() => setSezione(n.id)}
            >
              {n.etichetta}
            </button>
          ))}
        </nav>
        <div className="settings__main">
          <div className="sec" style={{ display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}>
            {sezione === 'motore' && (
              <SezioneMotore providers={providers} onScegli={scegliProvider} onSalvaChiave={salvaChiave} />
            )}
            {sezione === 'modelli' && (
              <SezioneModelli
                disco={disco}
                modelli={modelli}
                onScarica={scarica}
                onSospendi={sospendi}
                onElimina={eliminaModello}
                onAvvia={avvia}
                onFerma={ferma}
                onApriCartella={() => disco && window.scriba.apriCartella(disco.cartella)}
              />
            )}
            {sezione === 'trascrizione' && (
              <SezioneTrascrizione
                impostazioni={impostazioni}
                microfoni={dispositivi?.microfoni ?? []}
                loopback={dispositivi?.loopback ?? []}
                onCambia={salva}
              />
            )}
            {sezione === 'rilevamento' && <SezioneRilevamento impostazioni={impostazioni} onCambia={salva} />}
            {sezione === 'scorciatoie' && <SezioneScorciatoie impostazioni={impostazioni} onCambia={salva} />}
            {sezione === 'analisi' && <SezioneAnalisi impostazioni={impostazioni} onCambia={salva} />}
            {sezione === 'dati' && (
              <SezioneDati
                voci={dati}
                onApri={(path) => window.scriba.apriCartella(path)}
                onEliminaAudio={eliminaAudio}
                onEliminaCall={eliminaCall}
                caricaSessioni={caricaSessioni}
              />
            )}
            {sezione === 'export' && (
              <SezioneExport impostazioni={impostazioni} onCambia={salva} onCambiaCartella={cambiaCartellaExport} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
