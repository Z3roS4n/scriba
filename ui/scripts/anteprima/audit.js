/**
 * «I pulsanti devono avere le stesse dimensioni» non è una cosa da
 * guardare: è una cosa da misurare. Questa pagina chiede al browser
 * l'altezza, il corpo, il raggio e il bordo di OGNI controllo sullo
 * schermo, li raggruppa per firma, e mette in cima quelli rari — perché
 * un controllo che appare una volta sola con misure sue è quasi sempre
 * uno che è sfuggito al sistema.
 *
 * La scala dichiarata dal design (tokens.css) è:
 *   --h-sm 26px · --h-md 30px · --h-lg 34px · --h-xl 38px
 * Tutto ciò che non cade lì sopra è fuori sistema, e va detto.
 */
const SCALA = [26, 30, 34, 38]

/**
 * La scala vale per i **pulsanti**, cioè per ciò che porta `.btn`. Non per le
 * schede, non per i minuti cliccabili dentro una citazione, non per i comandi
 * della finestra — quelli il design li fa alti quanto la barra, di proposito,
 * come fa Windows.
 *
 * La prima versione di questo file misurava tutto con lo stesso metro e
 * segnalava i comandi finestra come sbagliati: se li avessi «corretti» avrei
 * peggiorato l'interfaccia dandomi ragione da solo. Un audit che grida al lupo
 * si smette di leggere, ed è più dannoso di nessun audit.
 */
const soggettoAllaScala = (el) => el.classList.contains('btn')

window.__audit = () => {
  const controlli = [...document.querySelectorAll('button, input, select, textarea')]
    .filter((e) => e.offsetParent !== null || e.getClientRects().length)
  const gruppi = new Map()
  for (const el of controlli) {
    const s = getComputedStyle(el)
    const r = el.getBoundingClientRect()
    const h = Math.round(r.height)
    const firma = [
      el.tagName.toLowerCase(),
      `h${h}`,
      `fs${s.fontSize}`,
      `r${s.borderRadius}`,
      `w${s.fontWeight}`,
      s.borderStyle === 'none' ? 'senza bordo' : 'bordo',
    ].join(' · ')
    if (!gruppi.has(firma)) gruppi.set(firma, { n: 0, h, scala: soggettoAllaScala(el), classi: new Set(), testi: [] })
    const g = gruppi.get(firma)
    g.n++
    g.classi.add(el.className || '(senza classe)')
    if (g.testi.length < 3) g.testi.push((el.textContent || el.placeholder || '').trim().slice(0, 24))
  }
  const righe = [...gruppi.entries()].sort((a, b) => a[1].n - b[1].n)
  return {
    totale: controlli.length,
    firme: gruppi.size,
    // Solo i .btn: il resto ha misure sue, ed e' giusto che le abbia.
    pulsanti: righe.filter(([, g]) => g.scala).reduce((n, [, g]) => n + g.n, 0),
    pulsantiFuoriScala: righe.filter(([, g]) => g.scala && !SCALA.includes(g.h)).reduce((n, [, g]) => n + g.n, 0),
    elenco: righe.map(([f, g]) => ({
      firma: f,
      volte: g.n,
      esito: !g.scala ? 'non e un .btn' : SCALA.includes(g.h) ? 'in scala' : 'FUORI SCALA',
      classi: [...g.classi].slice(0, 3),
      esempi: g.testi,
    })),
  }
}

/** Le classi presenti nel DOM che nessuna regola stila. */
window.__scoperte = () => {
  const inCss = new Set()
  for (const f of document.styleSheets) {
    let rr
    try { rr = f.cssRules } catch { continue }
    const g = (l) => {
      for (const r of l) {
        if (r.selectorText) for (const m of r.selectorText.matchAll(/\.([a-zA-Z][\w-]*)/g)) inCss.add(m[1])
        if (r.cssRules) g(r.cssRules)
      }
    }
    g(rr)
  }
  const dom = new Map()
  for (const el of document.querySelectorAll('*')) for (const c of el.classList) dom.set(c, (dom.get(c) || 0) + 1)
  return [...dom.entries()].filter(([c]) => !inCss.has(c)).sort((a, b) => b[1] - a[1]).map(([c, n]) => `${c} ×${n}`)
}
