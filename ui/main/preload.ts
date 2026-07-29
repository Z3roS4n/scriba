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

const api = {
  /** Stato del core: presente solo dopo che si e' avviato. Senza token, di proposito. */
  endpoint: (): Promise<{ port: number } | null> => ipcRenderer.invoke('core:endpoint'),

  paths: (): Promise<{ dataDir: string; screenshotDir: string }> => ipcRenderer.invoke('app:paths'),

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

  screenshot: (): Promise<void> => ipcRenderer.invoke('screenshot:capture'),

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
