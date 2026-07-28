/**
 * Ponte fra l'interfaccia e il processo principale.
 *
 * Il renderer non riceve ne' Node ne' il token del core: puo' solo chiedere al
 * processo principale di inoltrare richieste. Cosi' una pagina compromessa non
 * ha modo di leggere il filesystem o di parlare direttamente col core.
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

  screenshot: (): Promise<void> => ipcRenderer.invoke('screenshot:capture'),

  overlay: {
    nascondi: (): Promise<void> => ipcRenderer.invoke('overlay:nascondi'),
    apriPrincipale: (): Promise<void> => ipcRenderer.invoke('overlay:apri-principale'),
  },

  /** Rilegge la combinazione dalle impostazioni. Restituisce quella attiva, o null. */
  registraScorciatoiaOverlay: (): Promise<string | null> =>
    ipcRenderer.invoke('overlay:registra-scorciatoia'),

  /** Apre la cartella di un file prodotto dall'app, con il file selezionato. */
  mostraFile: (percorso: string): Promise<void> =>
    ipcRenderer.invoke('file:mostra', percorso),

  /** Eventi in arrivo dal processo principale. Restituisce la funzione per disiscriversi. */
  on: (canale: string, callback: (payload: unknown) => void): (() => void) => {
    const consentiti = [
      'core:pronto',
      'core:event',
      'screenshot:saved',
      'screenshot:ignorato',
      'hotkey:stato',
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
