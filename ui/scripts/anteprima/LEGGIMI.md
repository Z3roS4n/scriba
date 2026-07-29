# Anteprima delle schermate senza Electron

Serve a una cosa sola: **mettere le schermate vere accanto alle pagine del handoff
e vedere se combaciano**, senza dover avviare Electron e il core Python.

Le pagine qui dentro caricano gli stessi bundle che finiscono nell'applicazione,
con un ponte finto verso il core (`ponte-finto.js`) che risponde con i dati delle
pagine di prova — stesse call, stesse frasi, stessi minuti. Un confronto fatto con
dati diversi non direbbe niente su quello che si vuole verificare.

```bash
npm run anteprima
```

Poi si serve la cartella `ui/` e si aprono `scripts/anteprima/index.html`,
`impostazioni.html`, `overlay.html`. Accanto, sotto `design/`, ci sono le pagine
del handoff: la configurazione in `.claude/launch.json` fa già entrambe le cose.

## Cosa non si può verificare qui

- **Il trascinamento e le zone `-webkit-app-region`**: esistono solo dentro una
  finestra Electron senza cornice. In un browser normale `getComputedStyle` le
  legge sempre come `no-drag`, quindi la misura non significa niente.
- **Le transizioni**, se il pannello del browser non sta componendo frame: le
  larghezze restano ferme al valore di partenza. Per misurare le colonne va
  disattivata la transizione, non aspettato il tempo dell'animazione.
- Tutto ciò che dipende dal core vero: audio, trascrizione, analisi, download.

Non fa parte del prodotto e non entra nella build.
