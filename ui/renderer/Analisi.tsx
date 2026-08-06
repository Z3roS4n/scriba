/**
 * Pannello di analisi: riassunto, punti salienti e revisione delle task.
 *
 * La parte che conta è la revisione. Le task le propone un modello, e un
 * modello sbaglia: ogni campo mostra accanto il minuto della call da cui
 * proviene, cliccabile per andare a leggere il punto esatto. Confermare è un
 * ritmo (C / X / J / K / Invio / Esc), non una serie di click isolati — vedi
 * la sezione 5 di comportamento.md.
 */

import { memo, useCallback, useEffect, useMemo, useState } from 'react'
import { ControlloRifinitura, useRifinitura } from './Rifinitura'
import type { Analisi, FaseAnalisi, Provider, Segmento, Sessione, StatoAnalisi, StatoTask, Task } from './tipi'
import { tempo } from './tipi'

/**
 * Rende il Markdown prodotto dal modello, quando il core non manda ancora le
 * versioni già divise in pezzi.
 *
 * Esce con le stesse classi del riassunto vero (`.sum__group`, `.sum__h`,
 * `.sum__item`) invece che con un contenitore proprio: un contenitore proprio
 * vorrebbe dire CSS che il design non ha, quindi testo senza stile — e la
 * ricaduta si vede solo quando il modello ha scritto qualcosa di inatteso,
 * cioè proprio quando la schermata deve restare leggibile.
 *
 * Volutamente minimale e senza librerie: intestazioni, elenchi e grassetto, e
 * tutto il resto resta testo. Il contenuto arriva da un modello di
 * linguaggio, quindi non gli si concede di produrre HTML arbitrario.
 */
const Markdown = memo(function Markdown({ testo }: { testo: string }) {
  const gruppi: Array<{ titolo: string | null; voci: string[] }> = []
  const ultimo = () => {
    if (!gruppi.length) gruppi.push({ titolo: null, voci: [] })
    return gruppi[gruppi.length - 1]
  }

  for (const riga of testo.split('\n')) {
    const pulita = riga.trim()
    if (!pulita) continue
    if (pulita.startsWith('## ')) {
      gruppi.push({ titolo: pulita.slice(3), voci: [] })
    } else if (pulita.startsWith('- ') || pulita.startsWith('* ')) {
      ultimo().voci.push(pulita.slice(2))
    } else {
      ultimo().voci.push(pulita)
    }
  }

  return (
    <>
      {gruppi.map((g, i) => (
        <div className="sum__group" key={i}>
          {g.titolo && <h3 className="sum__h">{g.titolo}</h3>}
          {g.voci.map((v, j) => (
            <p className="sum__item" key={j}>
              <span>{grassetto(v)}</span>
            </p>
          ))}
        </div>
      ))}
    </>
  )
})

function grassetto(testo: string): React.ReactNode {
  const pezzi = testo.split(/(\*\*[^*]+\*\*)/g)
  return pezzi.map((p, i) => (p.startsWith('**') && p.endsWith('**') ? <b key={i}>{p.slice(2, -2)}</b> : p))
}

/**
 * Le quattro priorità che il design colora, scritte per esteso.
 *
 * Non `chip--prio-${priorita}`: la priorità la sceglie un modello, e al primo
 * «urgente» al posto di «alta» quella classe non esisterebbe nel foglio di
 * stile. Il chip uscirebbe senza colore, che è esattamente il modo in cui una
 * priorità critica smette di sembrare critica senza che nessuno se ne accorga.
 */
const CHIP_PRIORITA: Record<string, string> = {
  bassa: 'chip chip--prio-bassa',
  media: 'chip chip--prio-media',
  alta: 'chip chip--prio-alta',
  critica: 'chip chip--prio-critica',
}

/** «14 ago 2026». Solo per le task: la trascrizione usa tempo(), non date. */
function dataEstesa(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' }).replace('.', '')
}

/** «X,XX €». Il campo si chiama costo_usd in tipi.ts ma il pannello lo mostra
 * in euro, com'è nel design: è il core a decidere la valuta, non questo file. */
function formattaEuro(n: number): string {
  return `${n.toFixed(2).replace('.', ',')} €`
}

/** «3m 12s»: la nota accanto al motore, diversa dal formato mm:ss dei minuti
 * cliccabili — qui non si salta da nessuna parte, è solo una durata. */
function formattaDurataMeta(ms: number): string {
  const totale = Math.max(0, Math.round(ms / 1000))
  return `${Math.floor(totale / 60)}m ${totale % 60}s`
}

function oraCorrente(): string {
  return new Date().toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
}

/** Scadenza risolta, detta a voce, o assente — la stessa logica del chip e
 * del campo in rassegna, quindi vive qui una volta sola. */
function testoScadenza(t: Pick<Task, 'due_date' | 'due_raw'>): string | null {
  if (t.due_date) return `${dataEstesa(t.due_date)}${t.due_raw ? ` · «${t.due_raw}»` : ''}`
  if (t.due_raw) return `solo a voce: «${t.due_raw}»`
  return null
}

function SchedeTask({
  tasks,
  selezionataId,
  onSeleziona,
  onImposta,
  onProve,
  onRassegna,
}: {
  tasks: Task[]
  selezionataId: number | null
  onSeleziona: (id: number) => void
  onImposta: (task: Task, stato: StatoTask) => void
  onProve: (task: Task) => void
  onRassegna: (indice: number) => void
}) {
  const daConfermare = tasks.filter((t) => t.needs_review && t.stato === 'proposed').length

  return (
    <>
      <div className="tasks__bar">
        {daConfermare > 0 && <span className="tasks__todo">{daConfermare} da confermare</span>}
        <span className="tasks__keys">C conferma · X scarta · J K scorri</span>
      </div>
      <div className="tasks__list">
        {tasks.map((t) => {
          const flag = t.needs_review && t.stato === 'proposed'
          const classi = [
            'task',
            flag ? 'is-flagged' : '',
            t.stato === 'confirmed' ? 'is-confirmed' : '',
            t.stato === 'rejected' ? 'is-discarded' : '',
            selezionataId === t.id ? 'is-selected' : '',
          ]
            .filter(Boolean)
            .join(' ')
          const scadenza = testoScadenza(t)

          return (
            <article key={t.id} className={classi} tabIndex={0} onClick={() => onSeleziona(t.id)}>
              <div className="task__top">
                <h3 className="task__title">{t.titolo}</h3>
                {flag && <span className="task__flag">DA CONFERMARE</span>}
              </div>
              <div className="chips">
                {t.assignee_text ? (
                  <span className="chip chip--plain">{t.assignee_text}</span>
                ) : (
                  <span className="chip chip--muted">nessun responsabile</span>
                )}
                {scadenza ? (
                  <span className={`chip ${t.due_date ? 'chip--plain' : 'chip--said'}`}>{scadenza}</span>
                ) : (
                  <span className="chip chip--muted">nessuna scadenza</span>
                )}
                {t.priorita && CHIP_PRIORITA[t.priorita] && (
                  <span className={CHIP_PRIORITA[t.priorita]}>{t.priorita}</span>
                )}
                {t.confidence != null && (
                  <span className={`chip chip--conf${t.confidence < 0.7 ? ' is-low' : ''}`}>
                    conf. {t.confidence.toFixed(2).replace('.', ',')}
                  </span>
                )}
              </div>
              <div className="task__foot">
                <button
                  className="task__ev"
                  onClick={(e) => {
                    e.stopPropagation()
                    onProve(t)
                  }}
                >
                  {t.evidence.length === 1 ? '1 prova' : `${t.evidence.length} prove`}
                </button>
                {t.stato === 'proposed' ? (
                  <div className="task__actions">
                    <button
                      className="btn btn--sm btn--confirm"
                      onClick={(e) => {
                        e.stopPropagation()
                        onImposta(t, 'confirmed')
                      }}
                    >
                      Conferma
                    </button>
                    <button
                      className="btn btn--sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        onRassegna(tasks.findIndex((x) => x.id === t.id))
                      }}
                    >
                      Modifica
                    </button>
                    <button
                      className="btn btn--sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        onImposta(t, 'rejected')
                      }}
                    >
                      Scarta
                    </button>
                  </div>
                ) : (
                  // Annullabile dalla riga stessa: nessuna conferma modale.
                  <span className={`task__settled${t.stato === 'confirmed' ? ' is-ok' : ''}`}>
                    {t.stato === 'confirmed' ? 'confermata' : 'scartata'}
                    <button
                      className="btn--link"
                      onClick={(e) => {
                        e.stopPropagation()
                        onImposta(t, 'proposed')
                      }}
                    >
                      annulla
                    </button>
                  </span>
                )}
              </div>
            </article>
          )
        })}
      </div>
    </>
  )
}

/**
 * Cosa questa finestra sa, in un dato momento, di una diarizzazione in corso.
 *
 * `'in_corso_altrove'` esiste perche' il modello resta in memoria un'esecuzione
 * alla volta (vedi la 409 del core): se il tentativo di avvio la trova gia'
 * occupata da un'altra call, non e' un errore da correggere, e' solo uno stato
 * da mostrare — diverso da "sta girando qui", che invece ha una frazione e una
 * nota da seguire.
 */
type DiarizStato =
  | { fase: 'in_corso'; sessionId: number; frazione: number; nota: string }
  | { fase: 'in_corso_altrove'; messaggio: string }
  | null

/** Stima in minuti, 20-30 al minuto per ora — la misura vera è nella
 * docstring di `stt/diarizzazione.py`, non un numero a caso: sotto ai 40
 * minuti che l'avrebbero resa impraticabile, ma senza un margine comodo. */
function stimaDiarizzazione(durata_ms: number | null): { min: number; max: number } {
  const ore = (durata_ms ?? 0) / 3_600_000
  const min = Math.max(1, Math.round(ore * 20))
  const max = Math.max(min + 1, Math.round(ore * 30))
  return { min, max }
}

/**
 * Comando per assegnare le voci dentro «altri», accanto a «Rianalizza»: e' lo
 * stesso posto in cui vive gia' il vocabolario di "avvia un lavoro lungo su
 * questa call". Un lavoro di venti-trenta minuti non parte con un solo clic —
 * c'e' un passo di conferma in mezzo, con la stima scritta chiara.
 */
function ControlloDiarizzazione({
  sessione,
  disponibile,
  giaDiarizzata,
  stato,
  errore,
  conferma,
  onChiediConferma,
  onAnnullaConferma,
  onAvvia,
}: {
  sessione: Sessione
  /** null finche' non si e' ancora saputo, per non far comparire il comando e poi sparire. */
  disponibile: boolean | null
  giaDiarizzata: boolean
  stato: DiarizStato
  errore: { sessionId: number; messaggio: string } | null
  conferma: boolean
  onChiediConferma: () => void
  onAnnullaConferma: () => void
  onAvvia: () => void
}) {
  const inCorsoQui = stato?.fase === 'in_corso' && stato.sessionId === sessione.id
  const inCorsoAltrove =
    stato?.fase === 'in_corso_altrove' || (stato?.fase === 'in_corso' && stato.sessionId !== sessione.id)
  const erroreQui = errore && errore.sessionId === sessione.id ? errore : null

  if (disponibile === false) {
    // Detto, non nascosto: il pacchetto non include pyannote.audio (pesa 800
    // MB), e chi apre questa call deve saperlo invece di chiedersi perche'
    // "Voce 2" non diventa mai un nome.
    return (
      <p style={{ fontSize: 'var(--fs-xs)', lineHeight: 'var(--lh-body)', color: 'var(--fg5)', margin: 0 }}>
        Distinguere le voci dentro «altri» non è disponibile: manca pyannote.audio, non incluso nel
        pacchetto. Va installato a parte.
      </p>
    )
  }

  if (disponibile !== true) return null

  if (giaDiarizzata) {
    return <span className="chip chip--muted">voci distinte</span>
  }

  if (inCorsoQui) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
        <div className="progress" style={{ width: 90 }}>
          <i></i>
        </div>
        <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--fg5)' }}>{stato.nota || 'in corso'}</span>
      </div>
    )
  }

  if (inCorsoAltrove) {
    return (
      <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--fg5)' }}>
        {stato.fase === 'in_corso_altrove'
          ? stato.messaggio
          : "C'è già una diarizzazione in corso, su un'altra call."}
      </span>
    )
  }

  if (conferma) {
    const { min, max } = stimaDiarizzazione(sessione.durata_ms)
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', maxWidth: 320 }}>
        <div className="kv">
          <div className="kv__row">
            <span>Durata stimata</span>
            <b>
              {min}-{max} min
            </b>
          </div>
        </div>
        <p style={{ fontSize: 'var(--fs-xs)', lineHeight: 'var(--lh-body)', color: 'var(--fg5)', margin: 0 }}>
          Misurati davvero su questa macchina. Gira in locale: nessun dato esce dal computer. Puoi
          chiudere la finestra, il lavoro continua e lo ritrovi finito.
        </p>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <button className="btn btn--sm btn--confirm" onClick={onAvvia}>
            Avvia
          </button>
          <button className="btn btn--sm" onClick={onAnnullaConferma}>
            Annulla
          </button>
        </div>
      </div>
    )
  }

  if (erroreQui) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
        <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--red-dim)' }}>{erroreQui.messaggio}</span>
        <button className="btn btn--sm" onClick={onChiediConferma}>
          Riprova
        </button>
      </div>
    )
  }

  return (
    <button className="btn btn--sm" onClick={onChiediConferma}>
      Distingui le voci
    </button>
  )
}

export function PannelloAnalisi({
  sessione,
  segmenti,
  registrando,
  compatto,
  onVaiA,
  onCitazioni,
  onProve,
  onRassegna,
  onRicaricaSegmenti,
}: {
  sessione: Sessione | null
  /** Serve solo a sapere se la call e' gia' stata diarizzata (`speaker` non
   * nullo su almeno un segmento): la trascrizione li ha gia' caricati, non si
   * rifanno qui la stessa richiesta. */
  segmenti: Segmento[]
  registrando: boolean
  compatto: boolean
  onVaiA: (t_ms: number) => void
  onCitazioni: (t_ms: number[]) => void
  onProve: (task: Task | null) => void
  onRassegna: (indice: number) => void
  /** Rete di sicurezza della diarizzazione: ricarica i segmenti (index.tsx)
   * quando si sospetta che sia finita ma potrebbe essere passato un evento. */
  onRicaricaSegmenti: () => void
}) {
  const [analisi, setAnalisi] = useState<Analisi | null>(null)
  const [scheda, setScheda] = useState<'sum' | 'high' | 'task'>('sum')
  const [inCorso, setInCorso] = useState(false)
  const [fasi, setFasi] = useState<FaseAnalisi[]>([])
  const [errore, setErrore] = useState<{ messaggio: string; ora: string | null } | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [selezionataId, setSelezionataId] = useState<number | null>(null)

  // Stato della diarizzazione: non si azzera cambiando call (a differenza di
  // analisi/fasi/errore sopra) perche' il lock e' del processo, non della
  // sessione — una diarizzazione partita su un'altra call resta "in corso"
  // anche sfogliando qui.
  const [diarizDisponibile, setDiarizDisponibile] = useState<boolean | null>(null)
  const [diarizStato, setDiarizStato] = useState<DiarizStato>(null)
  const [diarizErrore, setDiarizErrore] = useState<{ sessionId: number; messaggio: string } | null>(null)
  const [diarizConferma, setDiarizConferma] = useState(false)
  // Come la diarizzazione, e per lo stesso motivo: il lavoro è del processo,
  // non della call che si sta guardando.
  const { stato: statoRifinitura } = useRifinitura()

  const carica = useCallback(async (id: number) => {
    const r = await window.scriba.get<Analisi>(`/sessions/${id}/analysis`)
    if (r.ok) setAnalisi(r.body)
  }, [])

  // I motori disponibili servono solo a "da analizzare" e alla variante
  // compatta, per dire quanto costa e se i dati escono dal computer. Non
  // cambiano da una call all'altra, quindi si chiedono una volta sola.
  useEffect(() => {
    window.scriba.get<Provider[]>('/providers').then((r) => {
      if (r.ok) setProviders(r.body)
    })
    // Idem per la disponibilita' della diarizzazione: dipende da cosa e'
    // installato su questa macchina, non dalla call che si guarda.
    window.scriba.get<{ disponibile: boolean }>('/diarizzazione/disponibile').then((r) => {
      if (r.ok) setDiarizDisponibile(r.body.disponibile)
    })
  }, [])

  // Il passo di conferma ("venti-trenta minuti, sicuro?") e' per forza legato
  // alla call che si sta guardando: cambiandola non deve restare aperto su
  // quella vecchia.
  useEffect(() => {
    setDiarizConferma(false)
  }, [sessione?.id])

  // Se una call e' gia' stata diarizzata almeno un segmento (mic o loopback,
  // non importa: il flag scatta per l'intera sessione) porta `speaker` non
  // nullo — vedi `diarizzata_at` in server.py. E' il modo per sapere "e' gia'
  // stato fatto" senza un campo dedicato nell'elenco call.
  const giaDiarizzata = useMemo(() => segmenti.some((s) => s.speaker != null), [segmenti])

  // L'avanzamento arriva per eventi, compreso quello partito da un'altra
  // finestra (il lock e' del processo, non di questa finestra): si ascolta
  // sempre, non solo mentre si guarda la call in questione.
  useEffect(() => {
    return window.scriba.on('core:event', (ev: any) => {
      if (ev?.type !== 'diarizzazione') return
      if (ev.stato === 'in_corso') {
        setDiarizStato({ fase: 'in_corso', sessionId: ev.session_id, frazione: ev.frazione ?? 0, nota: ev.nota ?? '' })
        setDiarizErrore(null)
      } else if (ev.stato === 'fatto') {
        setDiarizStato((c) => (c?.fase === 'in_corso' && c.sessionId === ev.session_id ? null : c))
      } else if (ev.stato === 'errore') {
        setDiarizStato((c) => (c?.fase === 'in_corso' && c.sessionId === ev.session_id ? null : c))
        setDiarizErrore({ sessionId: ev.session_id, messaggio: ev.dettaglio ?? 'Diarizzazione non riuscita.' })
      }
    })
  }, [])

  // Rete di sicurezza, stesso principio del punto 7 sopra per l'analisi: il
  // core non ha una rotta "stato diarizzazione" dedicata (il lavoro e' troppo
  // raro e troppo lungo per giustificarne una), quindi si ricontrolla la
  // verita' con l'unico segnale che il core da' gia': i segmenti, che dopo la
  // diarizzazione portano tutti `speaker` non nullo.
  useEffect(() => {
    if (!sessione || diarizStato?.fase !== 'in_corso' || diarizStato.sessionId !== sessione.id) return
    const timer = setInterval(onRicaricaSegmenti, 5000)
    return () => clearInterval(timer)
  }, [diarizStato, sessione, onRicaricaSegmenti])

  useEffect(() => {
    if (sessione && diarizStato?.fase === 'in_corso' && diarizStato.sessionId === sessione.id && giaDiarizzata) {
      setDiarizStato(null)
    }
  }, [giaDiarizzata, diarizStato, sessione])

  const avviaDiarizzazione = useCallback(async () => {
    if (!sessione) return
    const idSessione = sessione.id
    setDiarizErrore(null)
    setDiarizConferma(false)
    // Ottimista: il pulsante sparisce subito, non al giro di rete. Se il core
    // rifiuta (409, gia' in corso altrove) si corregge sotto senza che
    // l'utente abbia visto un lampo di "Distingui le voci" ancora cliccabile.
    setDiarizStato({ fase: 'in_corso', sessionId: idSessione, frazione: 0, nota: 'avviata' })
    const r = await window.scriba.post<{ detail?: string }>(`/sessions/${idSessione}/diarizzazione`)
    if (!r.ok) {
      if (r.status === 409) {
        setDiarizStato({
          fase: 'in_corso_altrove',
          messaggio: r.body?.detail ?? "C'è già una diarizzazione in corso.",
        })
      } else {
        setDiarizStato((c) => (c?.fase === 'in_corso' && c.sessionId === idSessione ? null : c))
        setDiarizErrore({
          sessionId: idSessione,
          messaggio: r.body?.detail ?? `Diarizzazione non riuscita (${r.status}).`,
        })
      }
    }
  }, [sessione])

  useEffect(() => {
    if (!sessione) {
      setAnalisi(null)
      setFasi([])
      setErrore(null)
      setInCorso(false)
      setSelezionataId(null)
      return
    }
    carica(sessione.id)
    setSelezionataId(null)
    setFasi([])
    setInCorso(sessione.stato === 'analyzing')
    // Se la call risulta già "non riuscita" non sappiamo più né il messaggio
    // né l'orario esatto del tentativo: l'evento che li portava è passato
    // prima che questa finestra si aprisse. Meglio dirlo in modo generico che
    // tacere l'errore.
    setErrore(sessione.stato === 'failed' ? { messaggio: "L'ultima analisi non è riuscita.", ora: null } : null)

    // Si chiede subito se un'analisi sta già girando, comprese le fasi.
    // Senza, riaprendo la finestra mentre il lavoro è in corso l'interfaccia
    // mostrerebbe "Analizza la call" come se non fosse mai partito.
    window.scriba.get<StatoAnalisi>('/analisi/stato').then((r) => {
      if (r.ok && r.body.session_id === sessione.id) {
        if (r.body.in_corso) setInCorso(true)
        setFasi(r.body.fasi)
      }
    })
  }, [sessione?.id, carica])

  // La fine dell'analisi arriva da un evento — comprese le fasi via via che
  // cambiano, così il pannello non deve interrogare per aggiornarle.
  useEffect(() => {
    return window.scriba.on('core:event', (ev: any) => {
      if (ev.type !== 'analisi' || !sessione || ev.session_id !== sessione.id) return
      if (ev.fasi) setFasi(ev.fasi)
      if (ev.stato === 'in_corso') {
        setInCorso(true)
        setErrore(null)
      } else {
        setInCorso(false)
        if (ev.stato === 'errore') {
          setErrore({ messaggio: ev.dettaglio ?? 'Analisi non riuscita.', ora: oraCorrente() })
        } else {
          carica(ev.session_id)
        }
      }
    })
  }, [sessione, carica])

  const inCorsoEffettivo = inCorso || sessione?.stato === 'analyzing'

  // Rete di sicurezza. Fidarsi solo degli eventi significa restare fermi per
  // sempre quando se ne perde uno, ed è successo davvero: due ore a mostrare
  // "analisi in corso" per un lavoro concluso da un pezzo. Finché la spia è
  // accesa si chiede al core come stanno le cose, fasi comprese.
  useEffect(() => {
    if (!inCorsoEffettivo || !sessione) return
    const id = sessione.id
    const timer = setInterval(async () => {
      const r = await window.scriba.get<StatoAnalisi>('/analisi/stato')
      if (r.ok && r.body.session_id === id) {
        setFasi(r.body.fasi)
        if (!r.body.in_corso) {
          setInCorso(false)
          carica(id)
        }
      }
    }, 5000)
    return () => clearInterval(timer)
  }, [inCorsoEffettivo, sessione, carica])

  const analizza = useCallback(async () => {
    if (!sessione) return
    setErrore(null)
    setInCorso(true)
    try {
      // La risposta dice solo che il lavoro è partito: dura minuti, e la fine
      // arriva da un evento. Aspettarla qui non funzionava — la richiesta
      // scadeva molto prima.
      const r = await window.scriba.post<{ detail?: string }>(`/sessions/${sessione.id}/analyze`)
      if (!r.ok) {
        setInCorso(false)
        setErrore({ messaggio: r.body?.detail ?? `Analisi non riuscita (${r.status}).`, ora: oraCorrente() })
      }
    } catch (e) {
      // Senza questo, un errore lasciava la spia accesa per sempre.
      setInCorso(false)
      setErrore({ messaggio: e instanceof Error ? e.message : String(e), ora: oraCorrente() })
    }
  }, [sessione])

  const interrompi = useCallback(async () => {
    if (!sessione) return
    await window.scriba.post(`/sessions/${sessione.id}/analyze/stop`)
  }, [sessione])

  const impostaStato = useCallback(async (task: Task, stato: StatoTask) => {
    const precedente = task.stato
    setAnalisi((a) => (a ? { ...a, tasks: a.tasks.map((t) => (t.id === task.id ? { ...t, stato } : t)) } : a))
    const r = await window.scriba.post(`/tasks/${task.id}`, { stato })
    if (!r.ok) {
      // Il ripristino tiene la riga coerente con quel che il core ha davvero
      // salvato, invece di lasciar credere un esito che non c'è stato.
      setAnalisi((a) =>
        a ? { ...a, tasks: a.tasks.map((t) => (t.id === task.id ? { ...t, stato: precedente } : t)) } : a,
      )
    }
  }, [])

  const apriProve = useCallback(
    (task: Task | null) => {
      if (task) setSelezionataId(task.id)
      onProve(task)
      onCitazioni(task ? task.evidence.map((e) => e.t_ms) : [])
    },
    [onProve, onCitazioni],
  )

  const tasks = useMemo(() => analisi?.tasks ?? [], [analisi])
  // Con `?? []` invece che leggendo la lunghezza direttamente: se il core
  // mandasse null al posto di una lista vuota — cosa che un campo nuovo fa
  // facilmente — il pannello diventerebbe una schermata bianca, e nessuno
  // saprebbe perché.
  const gruppi = useMemo(() => analisi?.riassunto_gruppi ?? [], [analisi])
  const salienti = useMemo(() => analisi?.salienti ?? [], [analisi])

  // Il ritmo da tastiera vale solo quando la scheda task è davvero quella
  // visibile, e non mentre si sta scrivendo altrove nella finestra.
  const pannelloTaskVisibile = !compatto && !inCorsoEffettivo && !errore && scheda === 'task' && tasks.length > 0

  useEffect(() => {
    if (!pannelloTaskVisibile) return
    const onKey = (e: KeyboardEvent) => {
      const fuoco = document.activeElement
      if (fuoco instanceof HTMLElement && (/INPUT|TEXTAREA/.test(fuoco.tagName) || fuoco.isContentEditable)) return

      const idx = tasks.findIndex((t) => t.id === selezionataId)
      if (e.key === 'Escape') {
        e.preventDefault()
        apriProve(null)
        return
      }
      const k = e.key.toLowerCase()
      if (k === 'j') {
        e.preventDefault()
        setSelezionataId(tasks[Math.min(tasks.length - 1, idx + 1)].id)
      } else if (k === 'k') {
        e.preventDefault()
        setSelezionataId(tasks[Math.max(0, idx - 1)].id)
      } else if (k === 'c' && idx >= 0) {
        e.preventDefault()
        impostaStato(tasks[idx], 'confirmed')
      } else if (k === 'x' && idx >= 0) {
        e.preventDefault()
        impostaStato(tasks[idx], 'rejected')
      } else if (e.key === 'Enter' && idx >= 0) {
        e.preventDefault()
        apriProve(tasks[idx])
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [pannelloTaskVisibile, tasks, selezionataId, impostaStato, apriProve])

  const providerAttivo = providers.find((p) => p.attivo) ?? null

  // -------------------------------------------------------------- render

  if (!sessione) {
    return (
      <section className="analysis">
        <div className="pad">
          <span className="label">ANALISI</span>
          <p style={{ fontSize: 'var(--fs-base)', lineHeight: 1.6, color: 'var(--fg4)' }}>
            Seleziona una call per vederne l'analisi.
          </p>
        </div>
      </section>
    )
  }

  if (compatto) {
    return (
      <section className="analysis analysis--muted">
        <div className="pad">
          <span className="label">ANALISI</span>
          <p style={{ fontSize: 'var(--fs-md)', lineHeight: 1.6, color: 'var(--fg4)' }}>
            Si fa a call finita. Riassunto, punti salienti e task su tutta la registrazione, non a pezzi.
          </p>
          {providerAttivo?.esce_dal_computer && (
            <div className="callout callout--inline">
              <p>Motore: {providerAttivo.etichetta}. La trascrizione lascia questo computer.</p>
            </div>
          )}
        </div>
      </section>
    )
  }

  if (inCorsoEffettivo) {
    return (
      <section className="analysis">
        <div className="pad">
          <span className="label">ANALISI IN CORSO</span>
          <div className="progress">
            <i></i>
          </div>
          <div className="stages">
            {fasi.map((f) => (
              <div
                key={f.chiave}
                className={`stage${f.stato === 'fatta' ? ' is-done' : f.stato === 'in_corso' ? ' is-current' : ''}`}
              >
                <span className="stage__mark">{f.stato === 'fatta' ? '✓' : ''}</span>
                {f.titolo}
                <span className="stage__note">{f.nota ?? 'in attesa'}</span>
              </div>
            ))}
          </div>
          <div className="kv">
            <p style={{ fontSize: 'var(--fs-base)', color: 'var(--fg2)' }}>Puoi chiudere la finestra.</p>
            <p style={{ fontSize: 'var(--fs-xs)', lineHeight: 'var(--lh-body)', color: 'var(--fg4)' }}>
              Il lavoro continua e lo ritrovi finito. Ti avvisiamo quando è pronto.
            </p>
          </div>
          <button className="btn" style={{ alignSelf: 'flex-start' }} onClick={interrompi}>
            Interrompi
          </button>
        </div>
      </section>
    )
  }

  if (errore) {
    return (
      <section className="analysis">
        <div className="pad">
          <span className="label" style={{ color: 'var(--red-dim)' }}>
            ANALISI NON RIUSCITA
          </span>
          <div className="errorbox">
            <h3>Analisi non riuscita</h3>
            <p>{errore.messaggio}</p>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
            {/* Le prime due riportano alle impostazioni: cambiare motore non è
                un gesto che questo pannello può fare da solo. */}
            <button className="btn btn--primary btn--block" onClick={() => window.scriba.apriImpostazioni()}>
              Avvia il modello locale
            </button>
            <button className="btn btn--block" onClick={() => window.scriba.apriImpostazioni()}>
              Usa un altro motore
            </button>
            <button className="btn btn--block" onClick={analizza}>
              Riprova
            </button>
          </div>
          {errore.ora && <span className="mono-note">ultimo tentativo {errore.ora}</span>}
        </div>
      </section>
    )
  }

  if (!analisi) {
    return (
      <section className="analysis">
        <div className="pad">
          <span className="label">ANALISI</span>
          <p style={{ fontSize: 'var(--fs-base)', lineHeight: 1.6, color: 'var(--fg4)' }}>Carico l'analisi…</p>
        </div>
      </section>
    )
  }

  const haContenuto =
    tasks.length > 0 ||
    gruppi.length > 0 ||
    salienti.length > 0 ||
    !!analisi.riassunto ||
    !!analisi.punti_salienti

  if (!haContenuto) {
    const ore = (sessione.durata_ms ?? 0) / 3_600_000
    const minutiSessione = Math.max(1, Math.round((sessione.durata_ms ?? 0) / 60_000))
    const minutiStimati =
      providerAttivo?.minuti_per_ora != null ? Math.max(1, Math.round(providerAttivo.minuti_per_ora * ore)) : null
    const costoTesto = !providerAttivo
      ? '—'
      : providerAttivo.costo_ora_eur == null
        ? 'gratis'
        : formattaEuro(providerAttivo.costo_ora_eur * ore)

    return (
      <section className="analysis">
        <div className="pad">
          <span className="label">ANALISI</span>
          <p style={{ fontSize: 'var(--fs-base)', lineHeight: 1.6, color: 'var(--fg2)' }}>
            Questa call non è ancora stata analizzata.
          </p>
          <button className="btn btn--primary btn--block" onClick={analizza} disabled={registrando}>
            Analizza la call
          </button>
          <div className="kv">
            <div className="kv__row">
              <span>Motore</span>
              <b>{providerAttivo?.etichetta ?? '—'}</b>
            </div>
            <div className="kv__row">
              <span>Durata stimata</span>
              <b>{minutiStimati != null ? `circa ${minutiStimati} min` : '—'}</b>
            </div>
            <div className="kv__row">
              <span>Costo stimato</span>
              <b>{costoTesto}</b>
            </div>
          </div>
          {/* Conseguenza, non errore: resta visibile anche a motore già scelto. */}
          {providerAttivo?.esce_dal_computer && (
            <div className="callout">
              <p>
                La trascrizione di {minutiSessione} minuti esce da questo computer e viene inviata a{' '}
                {providerAttivo.etichetta}.
              </p>
            </div>
          )}
          {/* Indipendente dall'analisi sopra: lavora sull'audio, non sul suo
              risultato, quindi ha senso anche prima che l'analisi sia mai
              partita. */}
          <ControlloDiarizzazione
            sessione={sessione}
            disponibile={diarizDisponibile}
            giaDiarizzata={giaDiarizzata}
            stato={diarizStato}
            errore={diarizErrore}
            conferma={diarizConferma}
            onChiediConferma={() => setDiarizConferma(true)}
            onAnnullaConferma={() => setDiarizConferma(false)}
            onAvvia={avviaDiarizzazione}
          />
          {/* Anche qui prima dell'analisi: lavora sull'audio, e rifare la
              trascrizione ha senso soprattutto *prima* di analizzarla — le
              task escono da quel testo. */}
          <ControlloRifinitura
            sessione={sessione}
            stato={statoRifinitura}
            onFinita={onRicaricaSegmenti}
          />
        </div>
      </section>
    )
  }

  const meta = analisi.meta
  return (
    <section className="analysis">
      <div className="analysis__head">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
          <button className="btn" onClick={analizza} disabled={registrando}>
            Rianalizza
          </button>
          {meta && (
            <span className="analysis__meta">
              {[
                meta.etichetta_provider,
                meta.costo_usd != null ? formattaEuro(meta.costo_usd) : null,
                meta.durata_ms != null ? formattaDurataMeta(meta.durata_ms) : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            </span>
          )}
        </div>
        {/* Riga propria, non incollata a quella di Rianalizza: a 392 px di
            larghezza (comportamento.md, 8) il passo di conferma — stima più
            due pulsanti — non ci starebbe nella stessa riga. */}
        <ControlloDiarizzazione
          sessione={sessione}
          disponibile={diarizDisponibile}
          giaDiarizzata={giaDiarizzata}
          stato={diarizStato}
          errore={diarizErrore}
          conferma={diarizConferma}
          onChiediConferma={() => setDiarizConferma(true)}
          onAnnullaConferma={() => setDiarizConferma(false)}
          onAvvia={avviaDiarizzazione}
        />
        <ControlloRifinitura
          sessione={sessione}
          stato={statoRifinitura}
          onFinita={onRicaricaSegmenti}
        />
        <div className="tabs" role="tablist">
          <button className={`tab${scheda === 'sum' ? ' is-active' : ''}`} onClick={() => setScheda('sum')}>
            Riassunto
          </button>
          <button className={`tab${scheda === 'high' ? ' is-active' : ''}`} onClick={() => setScheda('high')}>
            Punti salienti<span className="tab__count">{salienti.length}</span>
          </button>
          <button className={`tab${scheda === 'task' ? ' is-active' : ''}`} onClick={() => setScheda('task')}>
            Task<span className="tab__count">{tasks.length}</span>
          </button>
        </div>
      </div>

      <div className="tabpanel" data-panel="sum" hidden={scheda !== 'sum'}>
        <div className="sum">
          {gruppi.length > 0
            ? gruppi.map((g, i) => (
                <div className="sum__group" key={i}>
                  <h3 className="sum__h">{g.titolo}</h3>
                  {g.voci.map((v, j) => (
                    <p className="sum__item" key={j}>
                      <span>
                        {v.testo}{' '}
                        {v.t_ms != null && (
                          <button className="ref" onClick={() => onVaiA(v.t_ms as number)}>
                            {tempo(v.t_ms)}
                          </button>
                        )}
                      </span>
                    </p>
                  ))}
                </div>
              ))
            : analisi.riassunto && <Markdown testo={analisi.riassunto} />}
        </div>
      </div>

      <div className="tabpanel" data-panel="high" hidden={scheda !== 'high'}>
        {/* Cambia anche il contenitore, non solo il contenuto: `.hls` è una
            griglia minuto/testo, e senza i minuti non ha niente da allineare. */}
        <div className={salienti.length > 0 ? 'hls' : 'sum'}>
          {salienti.length > 0
            ? salienti.map((p, i) => (
                <div className="hl" key={i} onClick={() => onVaiA(p.t_ms)}>
                  <button
                    className="ref"
                    onClick={(e) => {
                      e.stopPropagation()
                      onVaiA(p.t_ms)
                    }}
                  >
                    {tempo(p.t_ms)}
                  </button>
                  <div>
                    <span className="hl__label">{p.etichetta}</span>
                    <span className="hl__body">{p.corpo}</span>
                  </div>
                </div>
              ))
            : analisi.punti_salienti && <Markdown testo={analisi.punti_salienti} />}
        </div>
      </div>

      <div
        className="tabpanel"
        data-panel="task"
        hidden={scheda !== 'task'}
        style={scheda === 'task' ? { display: 'flex', flexDirection: 'column', overflow: 'hidden' } : undefined}
      >
        {tasks.length === 0 ? (
          <p style={{ padding: '13px 20px', color: 'var(--fg4)' }}>Nessun impegno individuato.</p>
        ) : (
          <SchedeTask
            tasks={tasks}
            selezionataId={selezionataId}
            onSeleziona={setSelezionataId}
            onImposta={impostaStato}
            onProve={apriProve}
            onRassegna={onRassegna}
          />
        )}
      </div>
    </section>
  )
}
