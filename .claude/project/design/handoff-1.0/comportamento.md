# Scriba — finestra principale, note di comportamento

Regole che il codice deve rispettare. Aggiorna e sostituisce il file omonimo
del design precedente per le parti qui coperte.

File: `tokens.css` · `app.css` · `stringhe.md`, più una pagina per schermata —
`principale-analizzata.html` (+ `-en`), `principale-registrazione.html`,
`rassegna.html`, `impostazioni.html`, `archivio.html`,
`overlay-e-dialoghi.html`.
Nessun framework, nessun controllo di form nativo, nessun font di rete.

---

## Densità

0-bis. **Lo spazio da solo non toglie il disordine.** Una schermata affollata a
    cui si aggiunge padding diventa una schermata affollata e alta. Ogni volta
    che qualcosa sembra confuso si agisce su due leve insieme: più spazio, e
    **meno elementi**. Quattro cose tolte in questa passata, tutte per lo
    stesso motivo — dicevano qualcosa che era già scritto altrove:

    - **«Analizzata» nell'elenco call.** Ripetuto in colonna sei volte non
      informa nessuno. Informa il numero di task, e informa il guasto. La riga
      di stato è sparita: la terza riga porta il cliente a sinistra e il
      conteggio a destra, e le call passano da quattro righe a tre.
    - **La confidenza su ogni task.** `confidenza 0,82` stampato su quindici
      righe è una colonna di numeri che nessuno legge. Si scrive **solo sotto
      0,80**, dove cambia una decisione.
    - **La cornice del `.callout`.** Stessa frase dentro un riquadro, sopra un
      secondo riquadro: due scatole in fila all'apertura del pannello. Bastano
      il filo rosso e una linea sotto.
    - **La riga di «Rianalizza».** Sta sulla riga dell'etichetta. Una banda in
      meno prima della prima task, e il pannello si apre sul contenuto invece
      che sui comandi.

0-ter. **Il minuto e il parlante sono un margine solo, non due colonne.**
    Accostati fra loro (8px) e staccati dal testo (24px) smettono di leggersi
    come due incolonnamenti di metadati che corrono lungo tutta la pagina. Lo
    scatto si allinea al testo, non al margine.

0-quater. **Sotto i 250px di colonna una citazione non si mette in griglia.**
    Nel pannello da 404px tre colonne lasciavano alla citazione 114px — venti
    caratteri per riga. Minuto e campo stanno sopra, la citazione prende tutta
    la larghezza: è la parte che va letta.

## Impianto

1. **La finestra ha due configurazioni, non una.**
   La colonna destra non si chiama «Analisi» finché un'analisi non c'è.
   `.side--rec` (280 px) durante la registrazione — nota di lavoro, scatti,
   dispositivi audio; `.side` (400 px) a riposo — le tre schede. La transizione
   è di 160 ms **sulla sola larghezza**: durante una call un movimento ampio
   ruba attenzione a una conversazione in corso.

2. **Il corpo della trascrizione sale in registrazione**, non scende.
   `--fs-read` 15 px a riposo, `--fs-read-rec` 16 px con `.is-recording` sul
   contenitore. È la risposta diretta alla lettura periferica, ed è l'unica
   variazione di scala ammessa nella finestra.

3. **Le soglie sono `@container`, non `@media`.**
   In Electron la finestra è il viewport e i due modi coinciderebbero, ma così
   la pagina di handoff si comporta come la finestra vera dentro un browser di
   qualunque larghezza: una sola verità sulle soglie. Sotto 1100 px si chiude
   `.side`, sotto 900 px anche `.calls`, e restano raggiungibili dalla barra
   (`.is-forced` finché la finestra resta stretta). **La trascrizione non
   sparisce mai**, e sotto 900 px non torna a 15 px: resta a 16, perché una
   finestra stretta è una finestra tenuta di lato.

## Trascrizione

4. **Il testo provvisorio si distingue dal definitivo.**
   `.line__text.is-provisional` = `--fg-4`, dritto. Niente corsivo: rallenta la
   lettura periferica proprio quando serve leggere di sfuggita. `.caret`
   lampeggia a 1,15 s. Alla chiusura della frase si toglie la classe e il testo
   torna pieno: **non** si smonta e rimonta la riga, altrimenti la lista salta.

5. **I due parlanti si distinguono senza leggere l'etichetta, e senza un
   secondo colore.** «Io» = filetto Ink da 2 px sulla riga (`.line--me`) più la
   fascia `--band-me`; «Altri» = nessun filetto. Il peso dell'etichetta segue.
   Non aggiungere un colore per il parlante: il rosso è occupato e un terzo
   colore renderebbe la lista una tabella colorata.

6. **Lo scorrimento automatico si sospende, non si spegne.**
   Insegue il parlato finché l'utente è a fondo lista (soglia 48 px). Appena
   scorre indietro l'inseguimento si ferma e compare il richiamo con il numero
   di righe arrivate. Un clic torna al presente e riattiva l'inseguimento.
   Nessun altro evento lo riattiva.

7. **Il minuto è sempre un salto.** `.line__t`, `.ev__t` e i minuti dei punti
   salienti portano alla riga: scroll + `.is-flashing` (`flashLine`, 1,1 s, una
   volta). Togliere la classe a fine animazione, altrimenti il secondo clic
   sulla stessa riga non lampeggia.

## Righe di eco

8. **È una piega, non un pannello.** `.echo` è una riga sola in cima al flusso.
   Aperta, le righe compaiono **al loro posto cronologico** dentro la
   trascrizione (`.line--echo`), sbiadite, con `.echo__tag` «ripresa».

9. **Una riga di eco non è mai attribuita a «Io»**, qualunque cosa dica la
   traccia: è audio dell'altro rientrato dal microfono, e attribuirlo a chi
   ascolta è il modo più veloce per far diffidare di tutta la trascrizione.

10. **Riconosciute, non cancellate.** Restano fuori da riassunto, note ed
    export; restano dentro la trascrizione. Chi legge deve poter verificare che
    il filtro non abbia buttato via una frase vera — succede, ed è il motivo per
    cui la sensibilità è regolabile.

11. **La sensibilità del filtro si regola dalla piega**, non dalle
    impostazioni. È l'unico posto da cui si capisce se sta sbagliando: te ne
    accorgi leggendo, e leggendo devi poterla cambiare.

## Task e prove

12. **Ogni campo mostra da quale frase viene.** `.evidence` è la prova, non un
    dettaglio: minuto, campo, citazione esatta fra caporali. Il minuto salta
    alla riga.

13. **Un campo senza prova lo dice.** `.ev--empty` — «Dedotta. Nessuna frase
    della riunione la sostiene.» **Non** si inventa una citazione plausibile e
    **non** si lascia il campo muto, che si legge come «verificato».

14. **Fino a cinque task da confermare si lavora in riga.** Sopra, in cima al
    pannello compare `.review` con il numero e l'ingresso alla rassegna a tutta
    finestra: nel pannello da 400 px quel ritmo non ci sta, e servirlo male è
    peggio che non servirlo. L'invito è sopra la lista, non dentro una task.

15. **Confermare è un ritmo.** C conferma, X scarta, J/K scorrono, Invio apre le
    prove, Esc chiude. Gli stessi comandi esistono come pulsanti. Ogni azione è
    annullabile dalla riga (`.task__settled` con «Annulla»): niente conferme
    modali. Le scorciatoie valgono solo con il pannello task visibile e il fuoco
    fuori da un campo di testo.

16. **Nessun verde, nessuna ambra.** Il sistema ha Ink, rosso, Slate e la linea.
    «Da confermare» si trova col filetto Ink (`.task.is-todo`), col peso del
    titolo e col conteggio in cima — non con un colore. Tre colori di stato in
    più su un pannello da 400 px sono rumore, e il rosso perderebbe il
    significato che ha.

## Colore

16-bis. **Un grigio che porta informazione sta sopra 4,5:1.**
    Il sistema ha due grigi aggiunti e sono due categorie, non due sfumature:
    `--slate-soft` (#6E7174, 4,9:1) per tutto ciò che va letto anche se va
    letto dopo — metadati, minuti, etichette di campo, note, righe di eco,
    testo provvisorio; `--slate-faint` (#96999B, 2,9:1) **solo** per ciò che non
    dice niente — comandi disabilitati, separatori, il segnaposto «—». Se una
    frase è scritta in `--slate-faint`, è nel token sbagliato.
    E **non si sommano mai colore e `opacity`**: i due effetti si moltiplicano,
    e quello che resta non si può più leggere. Una cosa sola, sempre.

17. **Il rosso ha cinque usi e nessun altro**: registrazione in corso · dati che
    escono dal computer · azione distruttiva · guasto che blocca una funzione ·
    priorità critica. **Non è il colore della CTA**: l'azione primaria è Ink
    pieno. Se «Analizza la call» fosse rossa, il pallino della registrazione
    smetterebbe di significare qualcosa.

18. **Quando i dati escono dal computer va detto.** `.callout` non è un errore:
    è la conseguenza, e resta visibile anche quando il motore è già stato
    scelto. Non nasconderlo dopo la prima volta, non trasformarlo in un
    tooltip.

## Superfici e forma

19. **Nessuna ombra, in nessun punto del sistema.** Le superfici che galleggiano
    sopra il contenuto — modale, popover, menu, avviso «call rilevata», overlay
    — si staccano con `.scrim` (il contenuto sotto si scurisce del 12%) e
    restano bordate e piatte. `--ms-shadow` esiste per dire esplicitamente
    `none`.

20. **Radius 0 ovunque, 2 px solo su ciò che si clicca.** In hover cambia il
    **bordo** (linea → Ink) o il **fondo**, mai l'opacità e mai la scala.
    Nessun `transform: scale` sugli interattivi.

21. **Nessun controllo di form nativo.** Su Windows `<select>`, checkbox e
    `<progress>` ignorano il tema dell'app e aprono popup di sistema chiari su
    un'app scura. Tutto ciò che sembra un controllo è `<button>` o `<div>`.

22. **Il chevron e il punto elenco non sono icone.** Chevron = due bordi da
    2 px ruotati di 45° (`.chev`); punto elenco e segno di stato = quadrato da
    7 px (`.sq`). Le icone Lucide restano per il chrome, inline, `stroke-width`
    1.75, `stroke-linecap="square"`, 16 px nella barra e 18 px nei pannelli.

## Lingua

23. **Lingua dell'interfaccia e lingua della call sono due assi indipendenti.**
    `principale-analizzata-en.html` lo mostra: chrome in inglese, trascrizione,
    citazioni e titoli delle task in italiano. Se il layout cede, cede lì —
    niente larghezze fisse tarate su una stringa italiana.

24. **Date, ore e numeri seguono la lingua dell'interfaccia**; le durate restano
    `mm:ss` in entrambe. `mic`, `loopback`, `bassa`, `media`, `alta`, `critica`,
    `titolo`, `assignee`, `due_date` si traducono dove si mostrano e mai dove si
    confrontano — la colonna **id** di `stringhe.md` li segnala uno per uno.

## Movimento

25. **Una curva sola** — `cubic-bezier(.2,.7,.2,1)` — e due durate in questa
    schermata: 160 ms per gli stati e la larghezza del pannello, 240 ms per le
    apparizioni. Niente parallax, niente contatori che salgono, niente ingressi
    laterali. Con `prefers-reduced-motion: reduce` è tutto fermo e tutto
    visibile.

---

## Rassegna task

26. **Si entra dalla proposta, non da una singola task.** In cima al pannello:
    `15 task · 6 da confermare · [Passa in rassegna]`. Fino a cinque da
    confermare si lavora in riga, senza cambiare piano. Si esce con Esc,
    tornando alla lista **sulla task da cui si è entrati**.

27. **Conferma e Scarta avanzano alla successiva.** La passata è un ritmo, non
    una serie di decisioni isolate. C / X / ← / →, e gli stessi comandi come
    pulsanti.

28. **La trascrizione a sinistra non si ricarica cambiando task: si sposta.**
    Restano montate le stesse righe, cambiano solo `.is-cited` e la posizione.
    Smontare e rimontare la lista la farebbe saltare, vanificando la prova
    sotto gli occhi.

29. **La barra di avanzamento è una traccia da 2px e un riempimento Ink**, senza
    raggio e senza percentuale scritta: il numero esatto è già in testata
    (`4 di 15`).

## Impostazioni

30. **È un piano dentro la finestra principale, non una finestra separata.**
    Si esce con Esc e si è di nuovo sulla call, al punto in cui si era. La voce
    del tray apre la finestra principale su questo piano. Due processi che
    tengono lo stesso stato lo fanno divergere — è il difetto già visto con i
    clienti creati dalla finestra impostazioni.

31. **Il piano sta SOTTO la barra in alto.** In una finestra senza cornice
    quella barra porta i comandi della finestra: coprirli lascia senza chiudi.
    Vale per Impostazioni, Archivio e Rassegna.

32. **Due tipi di impostazione, distinti a vista.** Preferenza normale = `.row`.
    Impostazione con conseguenze = `.row--risk`: filo rosso **e** la conseguenza
    scritta per esteso. Il filo rosso qui non decora, dice «questo manda dati
    fuori, scarica gigabyte, o cancella».

33. **La conseguenza resta scritta anche sul motore già in uso.** È quella che
    si dimentica per prima. Non si nasconde dopo la prima volta e non diventa
    un tooltip.

34. **Lo spazio si controlla prima di iniziare, non a metà.** Un modello che non
    ci sta mostra quanto manca (`Mancano 18,6 GB`) e ha il pulsante spento.

35. **Un download si sospende e riprende dal punto in cui era**, anche dopo aver
    chiuso l'applicazione. La verifica di integrità è uno stato visibile
    (`in verifica`), non un passaggio silenzioso.

36. **Le scorciatoie si catturano premendole** (`.key.is-capturing`), non si
    scrivono. Un conflitto va detto subito: Windows rifiuta la registrazione in
    silenzio.

## Overlay

37. **Colori fissi, non i token.** Sotto la striscia può esserci qualunque cosa,
    quindi il vetro resta scuro anche a tema chiaro. Sono i valori «su fondo
    nero» di msworks (`--ov-*`), che è esattamente il trattamento per una
    superficie sovrapposta a contenuto arbitrario.

38. **Non prende il fuoco quando compare.** Durante una call la tastiera serve
    alla riunione.

39. **Nessuna animazione di entrata o uscita**, solo una dissolvenza di 120 ms.
    Le righe nuove appaiono, non scorrono. Le più vecchie sfumano
    (`nth-last-child`): l'occhio cade sull'ultima senza cercarla.

40. **Barra trascinabile ovunque** (`-webkit-app-region: drag`), con i comandi
    esclusi (`no-drag`) e quasi invisibili finché non ci si passa sopra.
    Posizione, dimensione e variante ridotta si ricordano per schermo: la
    ridotta è una preferenza, non uno stato.

41. **Dall'overlay non si salta il consenso.** «Apri Scriba» porta alla finestra
    grande, dove la conferma c'è. Registrare altre persone non è un gesto da un
    clic dentro una striscia senza cornice.

## Dialoghi

42. **Il consenso è l'unico modale dell'app**, e il pulsante resta spento finché
    la spunta non c'è — anche quando la call è stata rilevata da sola. Si stacca
    con lo scrim al 12%, non con un'ombra.

43. **«Call rilevata» compare in basso a destra, mai al centro**: arriva mentre
    si sta entrando in riunione. «No grazie» dimentica solo quella proposta, non
    il rilevamento — per questo la nota accanto ai pulsanti.

44. **Gli errori hanno quattro livelli, e nessuno è modale.** Il livello dipende
    da quanto impedisce, non da quanto è grave in astratto:
    **1** barra in alto (non impedisce niente) ·
    **2** riquadro nel pannello (blocca una funzione) ·
    **3** riquadro prima di cominciare (cambierebbe il risultato senza dirlo —
    filo rosso) ·
    **4** riquadro nel punto in cui si è premuto.

45. **I comandi che risolvono l'errore stanno dentro il riquadro dell'errore**,
    non in Impostazioni. Il pannello risolve il problema che ha appena
    descritto.

## Archivio

46. **Risponde a un'altra domanda rispetto alla colonna call.** La colonna dice
    «cos'ho fatto oggi»; l'archivio dice «cosa ci siamo detti con questo
    cliente». Da qui la ricerca dentro il parlato e il raggruppamento.

47. **La ricerca parte quando si smette di scrivere** (250 ms), non a ogni
    tasto: i risultati che ballano sotto le dita non si leggono.

48. **Il risultato mostra la frase, non solo il titolo.** La parola cercata è
    marcata con l'evidenziatore Ink di msworks (`mark`), che qui trova un
    mestiere invece di decorare un titolo.

49. **Il cliente si assegna da qui, riga per riga.** È il posto in cui uno ha
    davanti le call non attribuite tutte insieme; farlo call per call dalla
    scheda significherebbe non farlo mai.

50. **Il peso dell'export si mostra prima.** Il contesto di un modello è finito,
    e scoprire che il documento non ci sta quando è già stato incollato da
    qualche parte è tardi. Per lo stesso motivo la trascrizione integrale è una
    spunta e non il comportamento predefinito.

## Cosa serve dal core

- **`Segmento.is_eco: boolean`** e, per rendere la piega verificabile,
  **`eco_di: segment_id`** — la riga dell'altro di cui quella è l'eco. Oggi
  `stt.filtro_eco` esiste solo come preferenza e all'interfaccia non arriva
  niente: senza questi due campi la striscia non si può disegnare.
- **`aspetto.lingua: 'it' | 'en' | 'sistema'`**, con la stessa propagazione
  immediata a tre finestre già risolta dal tema.
- **Il costo è in USD** (`meta.costo_usd`) e l'interfaccia mostra euro. O c'è un
  cambio vero, o si mostra USD: convertire con un tasso inventato è un numero
  finto in una schermata che vive di numeri veri.
