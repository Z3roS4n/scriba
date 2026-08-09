/**
 * Dati e privacy: dove stanno i file, e le due cancellazioni.
 *
 * «Elimina tutto di una call» deve chiedere quale call e poi una conferma
 * scritta (istruzioni del task): due passaggi, non un clic solo, perché non
 * si torna indietro. «Elimina l'audio» è irreversibile ma più contenuto —
 * qui basta un secondo clic che cambia l'etichetta del pulsante, senza un
 * intero modale.
 */

import { useEffect, useState } from 'react'

import type { Sessione, VoceDati } from '../tipi'
import { dimensione } from '../tipi'
import { Modal } from './Modal'

const FRASE_CONFERMA = 'ELIMINA'

type Passo = 'chiusa' | 'elenco' | 'conferma'

/**
 * Che build si sta usando.
 *
 * Sta qui e non in un «Informazioni» a parte perché è la stessa domanda di
 * «dove stanno i miei dati»: la si fa quando qualcosa non torna. Il commit
 * accanto al numero non è pignoleria — durante lo sviluppo si fanno molte
 * build con lo stesso numero, ed è l'unica cosa che le distingue.
 */
function Versione() {
  const [v, setV] = useState<{
    versione: string
    commit: string | null
    pulito: boolean | null
    costruito_il: string | null
  } | null>(null)

  useEffect(() => {
    window.scriba.versione().then(setV)
  }, [])

  if (!v) return null
  const quando = v.costruito_il ? new Date(v.costruito_il) : null
  return (
    <div className="row">
      <div className="row__text">
        <b>Versione</b>
        <span>
          {quando && !Number.isNaN(quando.getTime())
            ? `Compilata il ${quando.toLocaleDateString('it-IT', { day: 'numeric', month: 'long', year: 'numeric' })}.`
            : 'Data di compilazione non disponibile.'}
          {v.pulito === false && ' Contiene modifiche non salvate in nessun commit.'}
        </span>
      </div>
      <span className="pathrow__size">
        {v.versione}
        {v.commit ? ` · ${v.commit}${v.pulito === false ? '+' : ''}` : ''}
      </span>
    </div>
  )
}

export function SezioneDati({
  voci,
  onApri,
  onEliminaAudio,
  onEliminaCall,
  caricaSessioni,
}: {
  voci: VoceDati[]
  onApri: (path: string) => void
  onEliminaAudio: () => Promise<boolean>
  onEliminaCall: (id: number) => Promise<boolean>
  caricaSessioni: () => Promise<Sessione[]>
}) {
  const [confermaAudio, setConfermaAudio] = useState(false)
  const [passo, setPasso] = useState<Passo>('chiusa')
  const [sessioni, setSessioni] = useState<Sessione[]>([])
  const [sessioneScelta, setSessioneScelta] = useState<Sessione | null>(null)
  const [testoConferma, setTestoConferma] = useState('')
  const [eliminando, setEliminando] = useState(false)

  const apriScelta = async () => {
    setPasso('elenco')
    setSessioni(await caricaSessioni())
  }

  const chiudi = () => {
    setPasso('chiusa')
    setSessioneScelta(null)
    setTestoConferma('')
  }

  const confermaEliminazione = async () => {
    if (!sessioneScelta) return
    setEliminando(true)
    const ok = await onEliminaCall(sessioneScelta.id)
    setEliminando(false)
    if (ok) chiudi()
  }

  return (
    <>
      <div className="settings__head">Dati e privacy</div>
      <div className="settings__body">
        <Versione />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)', margin: 'var(--sp-4) 0 18px' }}>
          {voci.map((v) => (
            <div className="pathrow" key={v.chiave}>
              <div className="pathrow__text">
                <b>{v.etichetta}</b>
                <span>{v.path}</span>
              </div>
              <span className="pathrow__size">{dimensione(v.bytes)}</span>
              <button className="btn btn--sm" onClick={() => onApri(v.path)}>
                Apri
              </button>
            </div>
          ))}
        </div>

        <div className="danger">
          <span className="label">CANCELLAZIONI · NON SI TORNA INDIETRO</span>
          <div className="row">
            <div className="row__text">
              <b>Elimina l’audio, tieni la trascrizione</b>
              <span>
                Libera quasi tutto lo spazio. Le task e le loro prove restano, ma non si potrà più riascoltare la
                frase originale.
              </span>
            </div>
            {confermaAudio ? (
              <button
                className="btn btn--danger"
                onClick={async () => {
                  if (await onEliminaAudio()) setConfermaAudio(false)
                }}
              >
                Conferma: elimina
              </button>
            ) : (
              <button className="btn btn--danger" onClick={() => setConfermaAudio(true)}>
                Elimina l’audio
              </button>
            )}
          </div>
          <div className="row">
            <div className="row__text">
              <b>Elimina tutto di una call</b>
              <span>Audio, trascrizione, screenshot, task. Verrà chiesto quale call e poi una conferma scritta.</span>
            </div>
            <button className="btn btn--danger" onClick={apriScelta}>
              Scegli una call
            </button>
          </div>
        </div>
      </div>

      {passo === 'elenco' && (
        <Modal onChiudi={chiudi}>
          <div className="modal__head">
            <h2>Quale call?</h2>
            <p>Verrà cancellato tutto: audio, trascrizione, screenshot e task.</p>
          </div>
          <div
            style={{
              padding: '0 20px 16px',
              display: 'flex',
              flexDirection: 'column',
              gap: 1,
              maxHeight: 320,
              overflowY: 'auto',
            }}
          >
            {sessioni.length === 0 ? (
              <p style={{ color: 'var(--fg-3)', fontSize: 'var(--fs-sm)' }}>Nessuna call registrata.</p>
            ) : (
              sessioni.map((s) => (
                <button
                  key={s.id}
                  className="btn btn--block"
                  onClick={() => {
                    setSessioneScelta(s)
                    setPasso('conferma')
                  }}
                >
                  {s.titolo ?? `Call del ${new Date(s.started_at).toLocaleDateString('it-IT')}`}
                </button>
              ))
            )}
          </div>
          <div className="modal__foot">
            <button className="btn" onClick={chiudi}>
              Annulla
            </button>
          </div>
        </Modal>
      )}

      {passo === 'conferma' && sessioneScelta && (
        <Modal onChiudi={chiudi}>
          <div className="modal__head">
            <h2>Eliminare «{sessioneScelta.titolo ?? 'questa call'}»?</h2>
            <p>Non si torna indietro. Scrivi {FRASE_CONFERMA} per confermare.</p>
          </div>
          <div className="modal__field">
            <input
              className="textfield"
              value={testoConferma}
              autoFocus
              placeholder={FRASE_CONFERMA}
              onChange={(e) => setTestoConferma(e.target.value)}
            />
          </div>
          <div className="modal__foot">
            <button className="btn" onClick={() => setPasso('elenco')}>
              Indietro
            </button>
            <button
              className="btn btn--danger"
              disabled={testoConferma.trim() !== FRASE_CONFERMA || eliminando}
              onClick={confermaEliminazione}
            >
              Elimina definitivamente
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
