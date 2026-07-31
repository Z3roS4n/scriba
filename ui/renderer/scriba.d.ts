/**
 * Cosa il processo principale mette a disposizione delle pagine.
 *
 * Dichiarato una volta sola e condiviso: finestra principale, impostazioni e
 * overlay usano lo stesso ponte, e tenerne tre descrizioni separate significa
 * vederle divergere.
 */

export interface RispostaCore<T = unknown> {
  ok: boolean
  status: number
  body: T
}

/** Uno schermo su cui si può catturare. Lo costruisce `main/index.ts`. */
export interface Schermo {
  id: string
  /** 'Schermo 1', 'Schermo 2'. Costruita da noi: quella di Windows è inservibile. */
  etichetta: string
  larghezza: number
  altezza: number
  principale: boolean
}

export interface ScribaApi {
  /** Stato del core. Senza token, di proposito. */
  endpoint(): Promise<{ port: number } | null>
  paths(): Promise<{ dataDir: string; screenshotDir: string }>

  get<T>(path: string): Promise<RispostaCore<T>>
  post<T>(path: string, body?: unknown): Promise<RispostaCore<T>>
  /**
   * Solo per dare un nome a una voce (`PATCH /sessions/{id}/voci/{speaker_id}`):
   * è l'unica rotta del core che non è né una lettura né una creazione. Rispecchia
   * `post` a uno a uno, cambia solo il metodo.
   */
  patch<T>(path: string, body?: unknown): Promise<RispostaCore<T>>

  /** Senza id cattura lo schermo principale, come fa la scorciatoia globale. */
  screenshot(idSchermo?: string): Promise<void>
  /**
   * Gli schermi collegati adesso.
   *
   * Cambia mentre l'app gira — una dock, un proiettore — quindi va riletto
   * anche sull'evento `schermi:cambiati`, non solo all'avvio.
   */
  schermi(): Promise<Schermo[]>
  mostraFile(percorso: string): Promise<void>
  /** Apre una cartella nell'esplora risorse. Solo percorsi dentro i dati dell'app. */
  apriCartella(percorso: string): Promise<void>
  /** Chiede una cartella all'utente. Null se annulla. */
  scegliCartella(): Promise<string | null>

  /**
   * Comandi della barra del titolo.
   *
   * Le finestre sono senza cornice — la barra in alto la disegniamo noi, perché
   * quella di Windows ignora il tema scuro — quindi ridurre, ingrandire e
   * chiudere vanno rifatti a mano.
   */
  finestra: {
    riduci(): Promise<void>
    ingrandisci(): Promise<void>
    chiudi(): Promise<void>
  }

  /** Apre la finestra delle impostazioni, o la porta davanti se è già aperta. */
  apriImpostazioni(): Promise<void>

  overlay: {
    nascondi(): Promise<void>
    apriPrincipale(): Promise<void>
    /** Passa fra striscia intera e variante ridotta. Restituisce lo stato nuovo. */
    alternaRidotto(): Promise<boolean>
  }

  /** Rilegge le combinazioni dalle impostazioni e le registra. */
  registraScorciatoie(): Promise<{ overlay: string | null; screenshot: string | null }>
  /**
   * Prova a registrare una combinazione senza salvarla.
   *
   * Serve al campo che cattura i tasti: Windows rifiuta in silenzio una
   * combinazione già presa, e senza provarla prima si finirebbe a premere un
   * tasto che non fa niente.
   */
  provaScorciatoia(combinazione: string): Promise<boolean>

  /** Eventi dal processo principale. Restituisce la funzione per disiscriversi. */
  on(canale: string, callback: (payload: any) => void): () => void
}

declare global {
  interface Window {
    scriba: ScribaApi
  }
}
