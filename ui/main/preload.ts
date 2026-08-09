/**
 * Ponte fra l'interfaccia e il processo principale.
 *
 * Il renderer non riceve ne' Node ne' il token del core: puo' solo chiedere al
 * processo principale di inoltrare richieste. Cosi' una pagina compromessa non
 * ha modo di leggere il filesystem o di parlare direttamente col core.
 *
 * Lo stesso preload serve alla finestra principale, alle impostazioni e
 * all'overlay: sono processi diversi ma la superficie che possono toccare deve
 * restare identica, altrimenti si finisce con tre ponti leggermente diversi da
 * mantenere allineati a mano.
 */

import { contextBridge, ipcRenderer } from 'electron'

type Risposta<T = unknown> = { ok: boolean; status: number; body: T }

/** Uno schermo su cui si puo' catturare. Rispecchia `Schermo` in main/index.ts. */
type Schermo = {
  id: string
  etichetta: string
  larghezza: number
  altezza: number
  principale: boolean
}

/**
 * Il tema salvato, letto prima che la pagina esista.
 *
 * Sincrono di proposito, ed e' l'unica cosa sincrona di questo ponte: passare
 * da `GET /settings` significherebbe aspettare che il core sia partito, e nel
 * frattempo la finestra sarebbe gia' visibile con il tema sbagliato. Il
 * processo principale lo legge da `settings.json`, che sta su disco e non
 * dipende da nessun processo.
 */
const temaIniziale: string = ipcRenderer.sendSync('tema:iniziale')
/** Idem per la lingua: serve prima che ci sia qualcosa da scrivere. */
const linguaIniziale: string = ipcRenderer.sendSync('lingua:iniziale')

// Applicato qui e non nel bundle React: la CSP delle pagine vieta gli script
// inline (`script-src 'self'`), quindi non si puo' mettere una riga nel
// `<head>`, e il preload e' l'unico posto che gira prima del documento. Le
// finestre nascono comunque con `show: false`, quindi anche arrivando tardi
// non ci sarebbe un lampo: questo serve a non farlo dipendere da quel dettaglio.
{
  const applica = () => document.documentElement?.setAttribute(
    'data-theme',
    temaIniziale === 'chiaro' ||
      (temaIniziale === 'sistema' &&
        window.matchMedia('(prefers-color-scheme: light)').matches)
      ? 'light'
      : 'dark',
  )
  if (document.documentElement) applica()
  else document.addEventListener('DOMContentLoaded', applica, { once: true })
}

const api = {
  /** Il tema salvato ('sistema' | 'chiaro' | 'scuro'), gia' disponibile all'avvio. */
  temaIniziale,

  /** Dice a tutte le finestre che il tema e' cambiato. Le altre lo applicano. */
  annunciaTema: (tema: string): Promise<void> => ipcRenderer.invoke('tema:annuncia', tema),

  /** La lingua salvata ('sistema' | 'it' | 'en'), gia' disponibile all'avvio. */
  linguaIniziale,

  /** Dice a tutte le finestre che la lingua e' cambiata. */
  annunciaLingua: (lingua: string): Promise<void> =>
    ipcRenderer.invoke('lingua:annuncia', lingua),

  /** Stato del core: presente solo dopo che si e' avviato. Senza token, di proposito. */
  endpoint: (): Promise<{ port: number } | null> => ipcRenderer.invoke('core:endpoint'),

  paths: (): Promise<{ dataDir: string; screenshotDir: string }> => ipcRenderer.invoke('app:paths'),
  /** Versione, commit e data della build: serve a distinguere due installazioni. */
  versione: (): Promise<{
    versione: string
    commit: string | null
    pulito: boolean | null
    costruito_il: string | null
  }> => ipcRenderer.invoke('app:versione'),

  get: <T>(path: string): Promise<Risposta<T>> => ipcRenderer.invoke('core:request', path),

  post: <T>(path: string, body?: unknown): Promise<Risposta<T>> =>
    ipcRenderer.invoke('core:request', path, {
      method: 'POST',
      body: JSON.stringify(body ?? {}),
    }),

  // Serve a una sola rotta oggi (rinominare una voce dopo la diarizzazione,
  // PATCH /sessions/{id}/voci/{speaker_id}): senza, quella rotta del core
  // resterebbe irraggiungibile dal renderer, che non riceve mai il token per
  // parlare col core direttamente. Rispecchia `post` a uno a uno.
  patch: <T>(path: string, body?: unknown): Promise<Risposta<T>> =>
    ipcRenderer.invoke('core:request', path, {
      method: 'PATCH',
      body: JSON.stringify(body ?? {}),
    }),

  /** Senza id cattura lo schermo principale, come fa la scorciatoia globale. */
  screenshot: (idSchermo?: string): Promise<void> =>
    ipcRenderer.invoke('screenshot:capture', idSchermo),

  /** Gli schermi collegati adesso. Cambia mentre l'app gira: vedi 'schermi:cambiati'. */
  schermi: (): Promise<Schermo[]> => ipcRenderer.invoke('schermi:elenco'),

  /** Apre la cartella di un file prodotto dall'app, con il file selezionato. */
  mostraFile: (percorso: string): Promise<void> => ipcRenderer.invoke('file:mostra', percorso),

  /** Apre una cartella nell'esplora risorse. Solo percorsi dentro i dati dell'app. */
  apriCartella: (percorso: string): Promise<void> => ipcRenderer.invoke('cartella:apri', percorso),

  /** Chiede una cartella all'utente. Null se annulla. */
  scegliCartella: (): Promise<string | null> => ipcRenderer.invoke('cartella:scegli'),

  finestra: {
    riduci: (): Promise<void> => ipcRenderer.invoke('finestra:riduci'),
    ingrandisci: (): Promise<void> => ipcRenderer.invoke('finestra:ingrandisci'),
    chiudi: (): Promise<void> => ipcRenderer.invoke('finestra:chiudi'),
  },

  /** Apre la finestra delle impostazioni, o la porta davanti se e' gia' aperta. */
  apriImpostazioni: (): Promise<void> => ipcRenderer.invoke('impostazioni:apri'),

  overlay: {
    nascondi: (): Promise<void> => ipcRenderer.invoke('overlay:nascondi'),
    apriPrincipale: (): Promise<void> => ipcRenderer.invoke('overlay:apri-principale'),
    /** Passa fra striscia intera e variante ridotta. Restituisce lo stato nuovo. */
    alternaRidotto: (): Promise<boolean> => ipcRenderer.invoke('overlay:alterna-ridotto'),
  },

  /** Rilegge le combinazioni dalle impostazioni e le registra. */
  registraScorciatoie: (): Promise<{ overlay: string | null; screenshot: string | null }> =>
    ipcRenderer.invoke('scorciatoie:registra'),

  /**
   * Prova a registrare una combinazione senza salvarla.
   *
   * Serve al campo che cattura i tasti: Windows rifiuta in silenzio una
   * combinazione gia' presa, e senza provarla prima si finirebbe a premere un
   * tasto che non fa niente.
   */
  provaScorciatoia: (combinazione: string): Promise<boolean> =>
    ipcRenderer.invoke('scorciatoie:prova', combinazione),

  /** Eventi in arrivo dal processo principale. Restituisce la funzione per disiscriversi. */
  on: (canale: string, callback: (payload: unknown) => void): (() => void) => {
    const consentiti = [
      'core:pronto',
      'core:event',
      'screenshot:saved',
      'screenshot:ignorato',
      'scorciatoie:stato',
      'schermi:cambiati',
      'tema:cambiato',
      'lingua:cambiata',
    ]
    if (!consentiti.includes(canale)) {
      throw new Error(`Canale non consentito: ${canale}`)
    }
    const listener = (_event: unknown, payload: unknown) => callback(payload)
    ipcRenderer.on(canale, listener)
    return () => ipcRenderer.removeListener(canale, listener)
  },
}

contextBridge.exposeInMainWorld('scriba', api)

export type ScribaApi = typeof api
