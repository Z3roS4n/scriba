# Scriba — finestra principale, note di comportamento

Varianti scelte: **1a** (finestra principale), **2b** (rassegna task), **3a** (overlay), **4a** (impostazioni), più tutti i dialoghi.
File: `tokens.css` (variabili), `app.css` (componenti), una pagina HTML per stato, `demo.js` (solo ponteggio della demo).
Nessun framework, nessun font di rete, nessun controllo di form nativo.

## Regole che il codice deve rispettare

1. **Il testo provvisorio si distingue dal definitivo.**
   `.line__text.is-provisional` = colore `--fg3` + opacità .55, dritto. Niente corsivo: rallenta la lettura periferica proprio quando serve leggere di sfuggita. Il cursore `.caret` lampeggia a 1,15 s. Alla chiusura della frase si toglie la classe e il testo torna pieno: **non** si smonta e rimonta la riga, altrimenti la lista salta.

2. **Lo scorrimento automatico si sospende, non si spegne.**
   Insegue il parlato finché l'utente è a fondo lista (soglia consigliata: 48 px). Appena scorre indietro, l'inseguimento si ferma e compare `.jump` con il numero di righe arrivate. Un clic torna al presente e riattiva l'inseguimento. Nessun altro evento lo riattiva.

3. **Ogni campo di una task mostra da dove viene.**
   `.task__ev` apre il pannello `.evidence`. Il pannello si prende la larghezza dell'elenco call, che passa a `.calls--rail` (46 px): la trascrizione non si restringe mai, perché è lì che si verifica la prova.

4. **Il minuto è sempre un salto.**
   `.line__t`, `.ev__t`, `.ref` e i minuti dei punti salienti portano alla riga corrispondente: scroll + classe `.is-flashing` (animazione `flashLine`, 1,1 s, una volta). Rimuovere la classe a fine animazione, altrimenti il secondo clic sulla stessa riga non lampeggia.

5. **Confermare è un ritmo.**
   C conferma, X scarta, J/K scorrono, Invio apre le prove, Esc chiude. Gli stessi comandi esistono come pulsanti. Ogni azione è annullabile dalla riga stessa (`.task__settled` con "annulla"): niente conferme modali.
   Le scorciatoie valgono solo quando il pannello task è visibile e il fuoco non è in un campo di testo.

6. **Quando i dati escono dal computer va detto.**
   `.callout` non è un errore: è la conseguenza, e resta visibile anche quando il motore è già stato scelto. Non nasconderlo dopo la prima volta, non trasformarlo in un tooltip.

7. **Un'operazione lunga si può abbandonare.**
   Durante l'analisi la finestra si chiude senza fermare il lavoro. Le fasi (`.stage`) sono quattro e vanno aggiornate davvero, non simulate. Chiudendo e riaprendo si ritrova lo stato corrente, non l'inizio.

8. **La finestra si adatta da sola al momento d'uso.**
   In registrazione: `.analysis` passa a `.analysis--muted` (250 px), la trascrizione si allarga, l'elenco call mostra in cima la call in corso. A call finita torna a 392 px. La transizione è di 180 ms, solo sulla larghezza: durante una call un movimento ampio ruba attenzione.

9. **Sotto i 1100 px** il pannello analisi si nasconde e diventa raggiungibile dalla barra. Sotto i 900 px si nasconde anche l'elenco call. La trascrizione non sparisce mai.

10. **Nessun controllo nativo.** Su Windows ignorano il tema scuro. Tutto ciò che sembra un controllo è `<button>` o `<div>` stilizzato; niente `<select>`, `<input type="checkbox">`, `<progress>`.

## Uso del colore

- **Rosso `--red` (#E2231A)**: solo registrazione in corso e conseguenze (dati che escono, cancellazioni, priorità critica). Se compare altrove ha perso significato.
- **Parlanti**: nessun secondo colore. "Io" ha la regola in inchiostro (`--pri`), "Altri" in grigio (`--other-rule`), più le fasce `--me-band` / `--other-band`.
- **Ambra `--warn`**: solo "da confermare", priorità alta, scadenza detta a voce e non risolta.
- **Verde `--ok`**: solo esiti positivi (analizzata, confermata) e il pannello prove.

## Tipografia

Segoe UI, perché l'app è offline e Montserrat non può viaggiare con il pacchetto. Il carattere del brand si ritrova nelle maiuscolette spaziate (`.label`, `letter-spacing: .11em`) e nel filetto rosso. Il testo della trascrizione non scende mai sotto 13,5 px.

## Rassegna task (2b)

- Si entra dal pulsante «N prove» e si esce con Esc, tornando alla lista **sulla task da cui si è entrati**.
- Conferma e Scarta avanzano alla successiva: la passata è un ritmo, non una serie di decisioni isolate.
- La trascrizione a sinistra è già ferma sulle righe citate, con `.is-cited`. Non si ricarica cambiando task: si sposta.
- Un campo senza prova (tipicamente la priorità) usa `.field__quote.is-empty` e dice che è stato dedotto. **Non** si inventa una citazione plausibile.

## Overlay (3a)

- Colori fissi, non i token: sotto la striscia può esserci qualunque cosa e il vetro resta scuro anche a tema chiaro.
- Non prende il fuoco quando compare. Durante una call la tastiera serve alla riunione.
- Nessuna animazione di entrata o uscita: solo una dissolvenza di 120 ms. Le righe nuove appaiono, non scorrono.
- Le più vecchie sfumano (`nth-last-child`): l'occhio cade sull'ultima senza cercarla.
- Barra trascinabile ovunque (`-webkit-app-region: drag`), con i comandi esclusi (`no-drag`) e quasi invisibili finché non ci si passa sopra.
- Posizione e dimensione si ricordano per schermo. La variante ridotta è una preferenza, non uno stato: si ricorda anche quella.
- Resta sopra le applicazioni a schermo intero, non sopra le finestre di sistema.

## Impostazioni (4a)

- Due tipi di impostazione, distinti visivamente: preferenza normale (`.row`) e impostazione con conseguenze (`.row--risk`, filetto rosso + la conseguenza scritta).
- Il download di un modello si sospende e riprende dal punto in cui era, anche dopo aver chiuso l'applicazione. Lo spazio si controlla **prima** di iniziare, non a metà.
- La verifica di integrità è uno stato visibile, non un passaggio silenzioso.
- Le scorciatoie si catturano premendole (`.keycap.is-capturing`), non si scrivono. Un conflitto va detto subito: Windows rifiuta la registrazione in silenzio.

## Dialoghi (5)

- Il consenso è l'unico modale, e il pulsante resta `disabled` finché la spunta non c'è. Vale anche quando la call è stata rilevata automaticamente.
- «Call rilevata» compare in basso a destra, mai al centro: arriva mentre si sta entrando in riunione. «No grazie» dimentica solo quella proposta.
- Gli errori hanno quattro livelli: barra in alto (non impedisce niente), riquadro nel pannello (blocca una funzione), riquadro prima di cominciare (cambierebbe il risultato senza dirlo), riquadro nel punto in cui si è premuto. Nessuno di questi è modale.

## Cosa manca ancora

Il salvataggio delle preferenze, la finestra di conferma scritta per la cancellazione totale, e la vista sotto i 900 px.
