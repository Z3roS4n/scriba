# SignPath Foundation — firma del codice

**Stato: da chiedere.** Il codice è pronto; la domanda va presentata da chi ha
titolo per farlo, e va accolta.

## Perché questa strada

L'installer non è firmato e Windows 11 con Smart App Control attivo lo
**blocca** — non lo segnala, lo rifiuta (vedi
[#57](https://github.com/Z3roS4n/scriba/issues/57) per la misura). Delle quattro
strade possibili, SignPath Foundation è l'unica gratuita che non richiede una
società: firma progetti open source con un certificato OV, a spese della
fondazione.

Cosa **non** risolve, e va detto adesso invece di scoprirlo dopo: la firma non
elimina gli avvisi da subito. Dà un'identità stabile su cui la reputazione si
accumula; i primi utenti l'avviso lo vedono comunque. L'unica strada che porta a
zero avvisi resta il Microsoft Store con un pacchetto MSIX, dove è Microsoft a
rifirmare.

## Le condizioni, e come ci stiamo dentro

| condizione | Scriba |
|---|---|
| licenza open source approvata OSI, senza doppia licenza commerciale | MIT |
| repository pubblico | [Z3roS4n/scriba](https://github.com/Z3roS4n/scriba) |
| nessun componente proprietario | da verificare voce per voce prima di chiedere |
| già rilasciato nella forma da firmare | [v0.5.0](https://github.com/Z3roS4n/scriba/releases/tag/v0.5.0), con l'installer allegato |
| **artefatti costruiti in CI** | `.github/workflows/costruisci-installer.yml` |

L'ultima riga è quella che ha fatto scrivere il workflow. SignPath firma **solo
artefatti prodotti da una pipeline**: è così che verifica che il binario venga
davvero dal repository dichiarato e non dal disco di qualcuno. Un installer
costruito in locale, per loro, non esiste.

Il punto da guardare prima di presentare la domanda è «nessun componente
proprietario». Scriba scarica a runtime modelli e motore di analisi, che quindi
non sono dentro il pacchetto; ma le dipendenze impacchettate vanno elencate con
la loro licenza, non date per buone.

## Cosa manca, e chi lo fa

1. **Presentare la domanda** su <https://signpath.org/apply>. Serve chi ha
   titolo a rappresentare il progetto: non è un passaggio automatizzabile e non
   va fatto da un agente.
2. **Ad approvazione ottenuta**, SignPath fornisce l'identificativo
   dell'organizzazione, quello del progetto e un token API. Vanno messi nei
   segreti del repository, non nel codice.
3. **Aggiungere il passo di firma al workflow**, dopo la costruzione
   dell'installer e prima del caricamento dell'artefatto.

Il passo 3 è l'unico che si scrive qui, e ha senso scriverlo solo quando i primi
due sono fatti: un passo di firma che punta a un progetto inesistente fallirebbe
a ogni build, e un workflow che fallisce sempre è un workflow che si smette di
guardare.

## Come firmerà, quando ci sarà

SignPath ha un'azione ufficiale per GitHub Actions
(`signpath/github-action-submit-signing-request`). Il pezzo da aggiungere sta
fra «Installer» e il caricamento dell'artefatto, e prende l'`.exe` prodotto,
lo manda a firmare e riscarica quello firmato al suo posto.

Due cose da non sbagliare quando si arriverà lì:

- **Il segreto non va mai in un workflow che gira su PR da fork.** Il trigger
  `pull_request` di questo workflow serve a verificare che la build non si
  rompa, e in quel caso deve restare **senza** firma: i segreti non vengono
  esposti a codice che arriva da fuori.
- **La verifica dopo la firma va fatta sul file**, non sull'esito del comando:
  `Get-AuthenticodeSignature` sull'installer deve dire `Valid`. Un passo che
  «riesce» senza aver firmato è esattamente il modo in cui si pubblica un
  eseguibile che verrà bloccato.
