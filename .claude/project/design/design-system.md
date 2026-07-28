# Design system — Scriba

> Guida di stile e convenzioni per il redesign/nuovo design UI. Fonte di verità per implementare
> qualsiasi schermata nuova o rifinire una esistente, senza dover ririsalire al design originale o
> al contesto di una conversazione passata. **Aggiornare questo file ogni volta che si stabilisce
> una nuova convenzione trasversale** — non lasciarla solo nella chat.

## Commenti nel codice (vale anche qui, non solo per la UI)
Vedi `06-code-style.md`: commentare solo dove strettamente necessario a capire il codice per uno
sviluppatore anche senza AI; se il codice è chiaro da sé, non commentarlo. Vale per ogni
componente/servizio toccato durante il redesign.

## Scope attuale
<Quali modalità/piattaforme si implementano ORA (es. solo desktop, o desktop+mobile) e cosa è
rinviato/solo esplorazione. Essere espliciti: un design ricevuto spesso include più varianti
(es. una versione "densa/pro" completa e una "guidata/onboarding" solo abbozzata) — non
implementare la variante non richiesta finché non arriva conferma esplicita.>

## Palette — token
<Tabella con i valori esatti (hex/oklch) del design, per ogni tema se previsto light/dark. Mappare
sempre sul design system già in uso nel progetto (token semantici tipo shadcn: background,
foreground, primary, ecc.) PIÙ i token specifici del design che non hanno un semantic-token
equivalente — esporli come utility dirette così ogni sezione li riusa senza reinventarli.>

| Token design | Utility / variabile | Valore tema 1 | Valore tema 2 |
|---|---|---|---|
| <...> | <...> | <...> | <...> |

**Attenzione ai bianchi/neri "caldi"**: molti design usano un nero/bianco leggermente desaturato
verso un colore (beige, blu...), non `#fff`/`#000` puri — copiare i valori esatti, non arrotondare.

## Tipografia
<Font usati (display/corpo/mono), pesi, tracking. Se il design usa un font diverso per titoli e
corpo, generarli entrambi via il meccanismo di font-loading del framework (es. `next/font`), non
approssimare con un font di sistema.>

**Regola sui numeri**: se il design mostra i valori numerici (importi, date, codici, percentuali,
conteggi) in un font monospazio dedicato, applicarla **sempre, senza eccezioni** — è una scelta di
leggibilità del design, non estetica opzionale.

## Forma & elevazione
<Radius per card/tabelle/input/bottoni, spessore e colore bordi, uso di ombre (spesso minimo su
temi scuri), densità (compatta desktop vs ariosa mobile).>

## Icone
<Se il mockup usa una libreria icone diversa da quella del progetto (es. Material Symbols in un
prototipo HTML vs `lucide-react`/altro nel codice reale), costruire QUI la tabella di mappatura
completa, così ogni sezione futura la riusa invece di scegliere icone ad-hoc e disallineate.>

## Localizzazione
<Formato valuta, separatori migliaia/decimali, formato data, lingua — e se ci sono termini di
dominio che vanno sempre lasciati nella lingua originale (termini tecnici/normativi intraducibili).>

## Convenzioni di componente

### Controlli di form — SEMPRE primitive stilizzate, MAI native
I controlli nativi del browser (`<select>`, checkbox/radio nativi) renderizzano popup e stili
propri del sistema operativo, **ignorando il tema dell'app** (tipicamente si vede un popup chiaro
su un'app in tema scuro). Regola fissa, verificata più volte su più progetti:
- Usare sempre le primitive stilizzate del design system in uso (es. shadcn/ui, Radix, base-ui...),
  mai l'elemento HTML nativo direttamente in una schermata utente.
- Se manca la primitiva (es. non esiste ancora un componente Checkbox/Switch/Select stilizzato nel
  progetto), **crearla prima** seguendo lo stile delle primitive già presenti — non bypassarla con
  l'elemento nativo "per ora".
- **Preservare sempre la semantica dei form** durante la conversione: se un native `<select>`/
  checkbox era dentro un form con `name`/FormData letto da un'azione server, la primitiva stilizzata
  deve continuare a sottomettere le stesse chiavi/valori (quasi tutte le librerie di componenti
  supportano un prop `name` che renderizza un input nascosto per questo). Non cambiare mai i dati
  che un'azione server riceve durante un semplice re-skin.

### Stato disabilitato / funzione non supportata
Quando il design mostra una funzione senza backend che la supporti (vedi `da-implementare.md`):
**non inventare mai dati finti**. Convenzione: elemento visibile ma disabilitato, con
tooltip/etichetta tipo "Presto disponibile". Mai wired a un'azione che darebbe errore o a dati mock
fuori da un harness di anteprima esplicitamente dev-only.

### Stati da coprire sempre
Vuoto, caricamento, errore, scaduto/warning — con i colori/varianti già definiti nella palette
sopra, non improvvisati caso per caso.

## Pattern architetturale per sezione
Per ogni schermata/sezione:
1. **Componente presentazionale** (`<sezione>/<nome>-view.*` o equivalente) — riceve solo props
   tipizzate, nessun fetch/logica di business dentro, responsive nello stesso componente.
   Sotto-pezzi in file separati nella stessa cartella.
2. **Pagina/route reale** — fa il fetch dei dati (servizi/API esistenti), preserva i filtri/URL
   esistenti, passa i dati al componente presentazionale.
3. **Harness di anteprima** (vedi sotto) — monta la view con dati mock realistici, senza auth.

Per sezioni con logica business esistente e complessa (form grandi, editor, wizard...), **ri-skinnare
in place** preservando ogni state/handler/azione — non riscrivere la logica durante un re-skin.

## Harness di anteprima (per verificare senza login)
Necessario quando le schermate da ri-disegnare sono dietro autenticazione e non è possibile (né
consentito) autenticarsi con credenziali per conto dell'utente, nemmeno di test. Pattern:
- Una route dev-only che monta i componenti presentazionali con dati mock, con un gate che la
  disattiva in produzione (es. `if (process.env.NODE_ENV === "production") return notFound()`).
  **Rimuoverla prima del deploy**, o assicurarsi che il gate sia davvero irraggiungibile in prod.
- **Attenzione ai framework con routing basato su file/cartelle** (es. Next.js App Router): alcune
  convenzioni escludono dal routing le cartelle con un prefisso speciale (in Next.js, `_qualcosa` è
  una "private folder" e non genera MAI una route) — verificarlo nella documentazione del framework
  prima di scegliere il nome della cartella harness, per non perdere tempo a debuggare un 404 fantasma.
- Verifica: aprire la schermata sia a larghezza desktop sia a larghezza mobile, controllare i colori
  effettivi via computed style (non fidarsi solo del codice sorgente — un token può essere sbagliato
  a monte), controllare l'assenza di overflow orizzontale, controllare che non ci siano errori in
  console, controllare che lo switch responsive (mostra/nascondi chrome desktop vs mobile) avvenga
  davvero al breakpoint previsto.

## Responsive
<Stessa route/pagina per desktop e mobile con reflow via breakpoint (preferibile, evita di
duplicare la logica di business), oppure viste separate solo per le schermate che sono
strutturalmente diverse (es. un flusso di creazione che su mobile è un bottom-sheet e su desktop è
una pagina intera) — deciderlo esplicitamente per il progetto e scriverlo qui.>

## Shell (riferimento rapido)
<Descrizione breve della shell dell'app per ogni piattaforma: navigazione principale, dove vive la
ricerca/comando globale, dove vive un eventuale assistente/chat, elementi persistenti.>
