/**
 * Colonna centrale: la trascrizione. Non si restringe mai — vedi comportamento.md
 * punto 3 — perche' e' il posto dove ogni prova, di una task o di un riassunto, si
 * verifica leggendo davvero cosa e' stato detto.
 *
 * Espone `vaiA` tramite ref: e' cosi' che il pannello analisi, il pannello prove e
 * la rassegna task portano al minuto giusto senza che questo componente debba
 * conoscere nulla di loro.
 */

import {
  forwardRef,
  memo,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from 'react'

import { tempo, type Scatto, type Segmento, type Sessione, type Voce } from './tipi'
import { etichettaVoce, useT } from './lingua'

export interface TrascrizioneHandle {
  /** Scorre alla riga del minuto indicato e la fa lampeggiare una volta. */
  vaiA: (t_ms: number) => void
}

/** Le due tracce, per chiave: la traduzione la fa chi le mostra. Erano due
 *  stringhe italiane in una costante di modulo — un posto in cui `useT` non
 *  arriva, e quindi un pezzo di trascrizione che sarebbe rimasto in italiano
 *  sotto un chrome inglese. */
const ETICHETTA: Record<Segmento['source'], 'trascrizione.io' | 'trascrizione.altri'> = {
  mic: 'trascrizione.io',
  loopback: 'trascrizione.altri',
}

/**
 * Una riga di parlato. Memoizzata perche' durante una call arriva un evento al
 * secondo per traccia e le righe gia' definitive non cambiano piu': senza,
 * un'ora di call ricostruirebbe centinaia di righe a ogni parola nuova.
 */
const Riga = memo(function Riga({ s, citata }: { s: Segmento; citata: boolean }) {
  const t = useT()
  // Il microfono e' per definizione una persona sola: resta "Io" anche se la
  // diarizzazione (fatta a call finita, su un'altra traccia) gli assegnasse
  // per errore uno speaker.
  //
  // Per gli altri vale anche l'etichetta provvisoria, non solo il nome vero:
  // "Voce 2" e "Voce 3" sono gia' la risposta alla domanda da cui e' partita
  // questa funzione — quante persone diverse stanno parlando. Aspettare che
  // l'utente le battezzi tutte prima di mostrarle vorrebbe dire tenere
  // nascosto proprio il lavoro appena fatto.
  const chi =
    s.source === 'mic'
      ? t(ETICHETTA.mic)
      : s.speaker?.nome_reale ||
        (s.speaker ? etichettaVoce(t, s.speaker.numero ?? null, s.speaker.label) : null) ||
        t(ETICHETTA.loopback)
  return (
    // data-t serve a ritrovare la riga quando si clicca un minuto altrove nella finestra.
    <div
      className={`line ${
        // Una riga di eco NON prende mai il trattamento di «Io», qualunque
        // cosa dica la traccia (comportamento.md, 9). E' audio dell'altro
        // rientrato dal microfono: `.line--me` le darebbe il filetto Ink e la
        // fascia, cioe' i due segni con cui in questo design si riconosce «Io»
        // *senza leggere l'etichetta*. A colpo d'occhio sarebbe mia.
        s.eco ? 'line--echo' : s.source === 'mic' ? 'line--me' : 'line--other'
      } ${citata ? 'is-cited' : ''}`}
      data-t={s.t_start_ms}
    >
      <button className="line__t num">{tempo(s.t_start_ms)}</button>
      <span className="line__who">{s.eco ? t(ETICHETTA.loopback) : chi}</span>
      {/* Provvisorio: colore fioco, MAI corsivo (rallenta la lettura periferica). Alla
          chiusura della frase si toglie solo la classe, la riga non si smonta. */}
      <p className={`line__text ${s.is_final ? '' : 'is-provisional'}`}>
        {/* In testa al testo, non nella colonna del parlante: quella traccia e'
            larga 46px e il badge ne misura 71, quindi ci dipingerebbe sopra. */}
        {s.eco && <span className="echo__tag">ripresa</span>}
        {s.testo}
        {!s.is_final && <i className="caret" />}
      </p>
    </div>
  )
})

/**
 * Da percorso di Windows a URL che il renderer può caricare.
 *
 * `encodeURI` non tocca `#` e `?`, che in un nome di file sono legittimi e in
 * un URL no: senza quei due, uno screenshot salvato in una cartella con un
 * cancelletto non si vedrebbe, e la causa sarebbe invisibile.
 */
function urlFile(percorso: string): string {
  const barre = percorso.replace(/\\/g, '/')
  const assoluto = /^[a-zA-Z]:/.test(barre) ? `/${barre}` : barre
  return 'file://' + encodeURI(assoluto).replace(/#/g, '%23').replace(/\?/g, '%3F')
}

const RigaScatto = memo(function RigaScatto({
  s,
  onApri,
}: {
  s: Scatto
  onApri: (percorso: string) => void
}) {
  const t = useT()
  /** Il file poteva esserci quando la call è stata registrata e non esserci
   *  più adesso: spostato, cancellato, cartella su una chiavetta staccata. */
  const [rotta, setRotta] = useState(false)

  return (
    <div className="shot" data-t={s.t_ms}>
      <span className="shot__t num">{tempo(s.t_ms)}</span>
      <div>
        <button className="shot__frame" onClick={() => onApri(s.path)}>
          {/* L'immagine vera, non un segnaposto. Il file è sul disco e il CSP
              delle pagine ammette `file:` per le immagini: mostrare un
              rettangolo grigio dove c'è una slida vera vuol dire nascondere
              proprio quello che serve — e costringere ad aprire la cartella
              per sapere cosa si era condiviso.

              `contain` e non `cover`: una slide tagliata a metà non risponde
              alla domanda per cui la si guarda. Se il file non c'è più —
              spostato, cancellato — si torna al riquadro disegnato invece di
              lasciare l'icona di immagine rotta del browser. */}
          {rotta ? (
            <span className="shot__img shot__img--vuoto" />
          ) : (
            <img
              className="shot__img"
              src={urlFile(s.path)}
              alt={t('tra.scatto_alt', { t: tempo(s.t_ms) })}
              loading="lazy"
              onError={() => setRotta(true)}
            />
          )}
        </button>
        <span className="shot__cap">
          {rotta ? t('trascrizione.scatto_perso') : t('trascrizione.scatto')}
          {s.width && s.height && <span className="num">{s.width}×{s.height}</span>}
        </span>
      </div>
    </div>
  )
})

/**
 * Una voce trovata dalla diarizzazione e ancora senza nome vero: «Voce 2»,
 * «Voce 3»... Il campo compare qui, non altrove, perché è leggendo la
 * trascrizione — dove quell'etichetta provvisoria si vede davvero — che nasce
 * la domanda "chi è?". Una volta salvato il nome la riga sparisce da sola: il
 * nome si dà una volta, non si tiene un modulo aperto per sempre.
 */
const RigaVoceDaNominare = memo(function RigaVoceDaNominare({
  voce,
  onSalva,
}: {
  voce: Voce
  onSalva: (speakerId: number, nome: string) => Promise<boolean>
}) {
  const t = useT()
  const [nome, setNome] = useState('')
  const [salvando, setSalvando] = useState(false)

  const salva = useCallback(async () => {
    const pulito = nome.trim()
    if (!pulito || salvando) return
    setSalvando(true)
    const riuscito = await onSalva(voce.id, pulito)
    setSalvando(false)
    // Il campo si svuota solo se e' andata bene: se il core ha rifiutato il
    // nome resta li', pronto a riprovare senza doverlo riscrivere.
    if (riuscito) setNome('')
  }, [nome, salvando, onSalva, voce.id])


  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
      <span className="chip chip--quiet">{etichettaVoce(t, voce.numero ?? null, voce.label)}</span>
      {/* `--h-sm`, la stessa altezza del pulsante accanto. Aveva la classe
          intera (38px) più uno style inline con padding e corpo di un'altra
          misura, residuo del sistema vecchio: la classe vinceva sull'altezza e
          lo style sul resto, quindi usciva un campo alto dodici pixel più del
          suo pulsante e stretto dentro. */}
      <input
        className="textfield textfield--sm"
        type="text"
        placeholder={t('tra.ph_nome_vero')}
        value={nome}
        disabled={salvando}
        onChange={(e) => setNome(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            salva()
          }
        }}
        style={{ width: 130 }}
      />
      <button className="btn btn--primary btn--sm" onClick={salva} disabled={salvando || !nome.trim()}>
        {salvando ? '…' : 'Salva'}
      </button>
    </span>
  )
})

/** «12 ago»: il giorno da solo, senza l'ora. dataBreve() di tipi.ts la include
 * sempre, ma qui accanto ci va la durata della call, non l'orario di inizio. */
function giornoBreve(epochMs: number): string {
  const d = new Date(epochMs)
  const oggi = new Date()
  const stessoGiorno =
    d.getFullYear() === oggi.getFullYear() &&
    d.getMonth() === oggi.getMonth() &&
    d.getDate() === oggi.getDate()
  return stessoGiorno
    ? 'oggi'
    : d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' }).replace('.', '')
}

export const Trascrizione = forwardRef<
  TrascrizioneHandle,
  {
    sessione: Sessione | null
    segmenti: Segmento[]
    scatti: Scatto[]
    /** true quando questa e' proprio la call che si sta registrando adesso. */
    inDiretta: boolean
    /** i minuti (t_start_ms) citati dalla task aperta nel pannello analisi. */
    citate: number[]
    /** scorciatoia della striscia, gia' leggibile ("Alt + R"): solo per il suggerimento a finestra vuota. */
    scorciatoiaStriscia: string | null
    onRegistra: () => void
    onApriScatto: (percorso: string) => void
    /**
     * Salva il nome vero di una voce (PATCH .../voci/{id}) e, se riuscito,
     * aggiorna anche i segmenti di questa finestra: senza, il nome nuovo si
     * vedrebbe solo riaprendo la call, e il punto di questo comando e'
     * vederlo subito dove "Voce 2" si stava leggendo un momento prima.
     */
    onVoceRinominata: (speakerId: number, nome: string) => void
  }
>(function Trascrizione(props, ref) {
  const t = useT()
  const {
    sessione,
    segmenti,
    scatti,
    inDiretta,
    citate,
    scorciatoiaStriscia,
    onRegistra,
    onApriScatto,
    onVoceRinominata,
  } = props

  // Le voci trovate dalla diarizzazione, per sapere quali non hanno ancora un
  // nome vero. Vive qui e non nel pannello analisi perche' e' leggendo la
  // trascrizione che ci si accorge del problema ("Voce 2" al posto di un
  // nome), ed e' qui che deve trovarsi la soluzione.
  const [voci, setVoci] = useState<Voce[]>([])

  const ricaricaVoci = useCallback((id: number) => {
    window.scriba.get<Voce[]>(`/sessions/${id}/voci`).then((r) => {
      if (r.ok) setVoci(r.body)
    })
  }, [])

  useEffect(() => {
    if (!sessione) {
      setVoci([])
      return
    }
    ricaricaVoci(sessione.id)
  }, [sessione?.id, ricaricaVoci])

  // La diarizzazione la si avvia dal pannello analisi, ma l'esito (le voci
  // nuove) e un rinomino fatto altrove (un'altra finestra) devono arrivare
  // anche qui senza dover cambiare call e tornare indietro.
  useEffect(() => {
    if (!sessione) return
    const id = sessione.id
    return window.scriba.on('core:event', (ev: any) => {
      if (ev?.type !== 'diarizzazione' || ev.session_id !== id) return
      if (ev.stato === 'fatto' || ev.stato === 'voce_rinominata') ricaricaVoci(id)
    })
  }, [sessione, ricaricaVoci])

  const rinominaVoce = useCallback(
    async (speakerId: number, nome: string): Promise<boolean> => {
      const r = await window.scriba.patch<{ id: number; nome_reale: string }>(
        `/sessions/${sessione?.id}/voci/${speakerId}`,
        { nome_reale: nome },
      )
      if (r.ok) {
        setVoci((prec) => prec.map((v) => (v.id === speakerId ? { ...v, nome_reale: nome, confermato: true } : v)))
        onVoceRinominata(speakerId, nome)
      }
      return r.ok
    },
    [sessione?.id, onVoceRinominata],
  )

  // Solo le voci vere trovate dalla diarizzazione, non "altri" (il cestino
  // di chi non e' stato assegnato a nessun cluster: rinominarlo come se fosse
  // una persona sarebbe fuorviante) e non gia' battezzate.
  const vociDaNominare = useMemo(
    () => voci.filter((v) => v.numero != null && !v.nome_reale),
    [voci],
  )

  const corpo = useRef<HTMLDivElement>(null)
  const fine = useRef<HTMLDivElement>(null)
  const conteggioPrec = useRef(0)

  // L'inseguimento del parlato si sospende quando l'utente scorre indietro, e lo
  // riattiva solo il clic su ".jump": nessun altro evento lo fa, altrimenti si
  // strapperebbe la vista a chi sta rileggendo un punto passato.
  const seguiInFondo = useRef(true)
  const [sospesa, setSospesa] = useState(false)
  const [righeNuove, setRigheNuove] = useState(0)

  const citateSet = useMemo(() => new Set(citate), [citate])

  // Le righe in cui il microfono ha ripreso l'altoparlante restano nascoste,
  // ma si possono guardare. Sono gia' fuori da riassunto, note ed export: qui
  // non si decide niente, si da' modo di controllare che il giudizio fosse
  // giusto. Cancellarle e' l'unica cosa che non si fa — sono una riga su tre.
  const [mostraEco, setMostraEco] = useState(false)
  const quantiEco = useMemo(() => segmenti.filter((s) => s.eco).length, [segmenti])

  const righe = useMemo(() => {
    const parlato = mostraEco ? segmenti : segmenti.filter((s) => !s.eco)
    const elementi: Array<{ chiave: string; t: number; seg?: Segmento; scatto?: Scatto }> = [
      ...parlato.map((s) => ({ chiave: `s${s.id}`, t: s.t_start_ms, seg: s })),
      ...scatti.map((s) => ({ chiave: `i${s.id}`, t: s.t_ms, scatto: s })),
    ]
    return elementi.sort((a, b) => a.t - b.t)
  }, [segmenti, scatti, mostraEco])

  const vaiA = useCallback((t_ms: number) => {
    const el = corpo.current
    if (!el) return
    seguiInFondo.current = false
    setSospesa(true)
    const righeEl = Array.from(el.querySelectorAll<HTMLElement>('[data-t]'))
    const bersaglio = righeEl.find((r) => Number(r.dataset.t) >= t_ms) ?? righeEl[righeEl.length - 1]
    if (!bersaglio) return
    bersaglio.scrollIntoView({ block: 'center', behavior: 'smooth' })
    // Rimossa a fine animazione (flashLine, 1,1s): altrimenti un secondo clic
    // sulla stessa riga non lampeggia perche' la classe c'e' gia'.
    bersaglio.classList.add('is-flashing')
    window.setTimeout(() => bersaglio.classList.remove('is-flashing'), 1100)
  }, [])

  useImperativeHandle(ref, () => ({ vaiA }), [vaiA])

  const onClickMinuto = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      const t = (e.target as HTMLElement).closest('.line__t')
      if (!t) return
      const riga = t.closest<HTMLElement>('[data-t]')
      if (riga) vaiA(Number(riga.dataset.t))
    },
    [vaiA],
  )

  const onScroll = useCallback(() => {
    if (!seguiInFondo.current) return // gia' sospeso: si riattiva solo dal pulsante
    const el = corpo.current
    if (!el) return
    const distanzaDalFondo = el.scrollHeight - el.scrollTop - el.clientHeight
    if (distanzaDalFondo > 48) {
      seguiInFondo.current = false
      setSospesa(true)
    }
  }, [])

  const tornaAlPresente = useCallback(() => {
    seguiInFondo.current = true
    setSospesa(false)
    setRigheNuove(0)
    fine.current?.scrollIntoView({ block: 'end' })
  }, [])

  // Cambiando call si riparte da capo: si insegue di nuovo il fondo (che per una
  // call gia' finita coincide con l'ultima riga) e si azzera il conteggio.
  useEffect(() => {
    seguiInFondo.current = true
    setSospesa(false)
    setRigheNuove(0)
    conteggioPrec.current = 0
  }, [sessione?.id])

  useEffect(() => {
    const delta = righe.length - conteggioPrec.current
    conteggioPrec.current = righe.length
    if (seguiInFondo.current) {
      // Istantaneo, non animato: durante una call arriva un evento al secondo
      // per traccia e le animazioni si accavallerebbero.
      fine.current?.scrollIntoView({ block: 'end' })
    } else if (delta > 0) {
      setRigheNuove((n) => n + delta)
    }
  }, [righe])

  if (!sessione) {
    return (
      <main className="transcript">
        <div className="transcript__head">
          <span className="transcript__title">{t('tra.nessuna_call')}</span>
        </div>
        <div className="state">
          <div className="state__ph" />
          <div>
            <p className="state__title">{t('tra.mai_registrato')}</p>
            <p className="state__body" style={{ marginTop: 'var(--sp-2)' }}>
              {t('tra.mai_registrato_nota')}
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-4)' }}>
            <button className="btn btn--rec" onClick={onRegistra}>
              {t('tra.registra')}
            </button>
            {scorciatoiaStriscia && (
              <span className="state__hint">{t('tra3.oppure_striscia', { tasto: scorciatoiaStriscia })}</span>
            )}
          </div>
        </div>
      </main>
    )
  }

  const titolo = sessione.titolo || `Call #${sessione.id}`
  const meta = inDiretta
    ? 'in corso'
    : `${giornoBreve(sessione.started_at)} · ${tempo(sessione.durata_ms ?? 0)}`

  return (
    <main className="transcript">
      <div className="transcript__head">
        <h1 className="transcript__title">{titolo}</h1>
        <span className="transcript__meta num">{meta}</span>
        <div className="legend">
          <span>
            <i />
            {t('tra.io')}
          </span>
          <span>
            <i className="is-other" />
            {t('tra.altri')}
          </span>
        </div>
      </div>

      {/* Compare solo finche' resta almeno una voce senza nome: una volta
          battezzate tutte, la striscia sparisce da sola — il nome si da'
          una volta, non e' un modulo che resta aperto per sempre. */}
      {vociDaNominare.length > 0 && (
        <div
          className="transcript__head"
          style={{ borderTop: 'none', flexWrap: 'wrap', rowGap: 'var(--sp-2)', paddingTop: 0 }}
        >
          <span className="label">{t('tra.nomina_voci')}</span>
          {vociDaNominare.map((v) => (
            <RigaVoceDaNominare key={v.id} voce={v} onSalva={rinominaVoce} />
          ))}
        </div>
      )}

      {righe.length === 0 && inDiretta ? (
        <div className="state">
          <div className="meter">
            {[8, 14, 6, 11, 5, 9, 13, 7, 10].map((h, i) => (
              <i key={i} style={{ height: h }} />
            ))}
          </div>
          <p style={{ fontSize: 'var(--fs-read)', color: 'var(--fg-body)' }}>
            {t('tra.in_ascolto')}
          </p>
        </div>
      ) : righe.length === 0 ? (
        <div className="state">
          <p className="state__body">{t('tra.nessuna_trascrizione')}</p>
        </div>
      ) : (
        <div className="transcript__body" ref={corpo} onScroll={onScroll} onClick={onClickMinuto}>
          {/* È una piega, non un pannello: una riga sola in cima al flusso
              (comportamento.md, 8). Aperta, le righe compaiono al loro posto
              cronologico dentro la trascrizione, non raccolte in fondo.
              Compare solo quando c'è qualcosa da mostrare: su una call senza
              eco un interruttore che non fa mai niente insegna a non
              guardarlo. */}
          {quantiEco > 0 && (
            <div className="echo">
              <button
                className="echo__toggle"
                aria-expanded={mostraEco}
                onClick={() => setMostraEco((v) => !v)}
              >
                <span className={`chev${mostraEco ? ' is-open' : ''}`} />
                <span>
                  <b className="num">{t(quantiEco === 1 ? 'tra3.riga_1' : 'tra3.righe_n', { n: quantiEco })}</b>{' '}
                  {t(quantiEco === 1 ? 'tra3.ripresa' : 'tra3.riprese')}
                </span>
                <span className="echo__hint">{t('tra.eco_nota')}</span>
              </button>
            </div>
          )}
          {righe.map((r) =>
            r.seg ? (
              <Riga key={r.chiave} s={r.seg} citata={citateSet.has(r.seg.t_start_ms)} />
            ) : (
              <RigaScatto key={r.chiave} s={r.scatto as Scatto} onApri={onApriScatto} />
            ),
          )}
          <div ref={fine} />
        </div>
      )}

      {/* Fratello del corpo, non figlio: `.jump` e' in posizione assoluta dentro
          `.transcript`, e messo dentro il contenitore che scorre verrebbe
          ritagliato dal suo overflow. Compare solo a inseguimento sospeso —
          questo clic e' l'unico modo per farlo ripartire. */}
      {sospesa && righe.length > 0 && (
        <div className="jump">
          <button className="btn" onClick={tornaAlPresente}>
            {/* Il pulsante esiste per dire quante righe sono arrivate: a zero
                quella frase non ha senso, quindi si tace il conteggio invece
                di dire "0 righe nuove". */}
            {righeNuove === 0
              ? t('tra3.torna')
              : `${t('tra3.torna')} · ${t(righeNuove === 1 ? 'tra3.nuova_1' : 'tra3.nuove_n', { n: righeNuove })}`}
          </button>
        </div>
      )}
    </main>
  )
})
