/**
 * Cosa il processo principale mette a disposizione delle pagine.
 *
 * Dichiarato una volta sola e condiviso: finestra principale e overlay usano lo
 * stesso ponte, e tenerne due descrizioni separate significa vederle divergere.
 */

export interface RispostaCore<T = unknown> {
  ok: boolean
  status: number
  body: T
}

export interface ScribaApi {
  /** Stato del core. Senza token, di proposito. */
  endpoint(): Promise<{ port: number } | null>
  paths(): Promise<{ dataDir: string; screenshotDir: string }>

  get<T>(path: string): Promise<RispostaCore<T>>
  post<T>(path: string, body?: unknown): Promise<RispostaCore<T>>

  screenshot(): Promise<void>
  mostraFile(percorso: string): Promise<void>

  overlay: {
    nascondi(): Promise<void>
    apriPrincipale(): Promise<void>
  }

  /** Rilegge la combinazione dalle impostazioni. Restituisce quella attiva, o null. */
  registraScorciatoiaOverlay(): Promise<string | null>

  /** Eventi dal processo principale. Restituisce la funzione per disiscriversi. */
  on(canale: string, callback: (payload: any) => void): () => void
}

declare global {
  interface Window {
    scriba: ScribaApi
  }
}
