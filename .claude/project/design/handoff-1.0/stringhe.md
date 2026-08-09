# Scriba — catalogo delle stringhe

Una riga per stringa dell'interfaccia, in italiano e in inglese. È da qui che
nasce il catalogo delle traduzioni: ricavare le chiavi a posteriori da dodici
file HTML è lavoro che nessuno fa bene.

**Convenzioni**

- `{n}`, `{min}`, `{motore}` sono segnaposto, non testo.
- La colonna **id** segnala le stringhe che sono **etichette di un valore**
  salvato nel database o nello schema dei prompt. Si traducono dove si
  mostrano, **mai** dove si confrontano: `mic`, `loopback`, `bassa`, `media`,
  `alta`, `critica`, `titolo`, `assignee`, `due_date` restano quei valori lì.
- Date, ore e numeri seguono la **lingua dell'interfaccia**. Le durate restano
  `mm:ss` in entrambe: è un minutaggio, non un orario.

Schermate coperte: finestra principale (analizzata e in registrazione),
rassegna, impostazioni, overlay, dialoghi, archivio.

---

## Barra in alto

| chiave | italiano | inglese | id |
|---|---|---|---|
| `app.nome` | Scriba | Scriba | |
| `stato.pronto` | Pronto | Ready | |
| `stato.avvio_core` | Avvio | Starting | |
| `stato.carico_modello` | Carico il modello | Loading the model | |
| `stato.registrazione` | Registrazione | Recording | |
| `stato.modello_assente` | Modello non disponibile | Model unavailable | |
| `azione.screenshot` | Scatta | Capture | |
| `azione.esporta` | Esporta | Export | |
| `azione.archivio` | Archivio | Archive | |
| `azione.impostazioni` | Impostazioni | Settings | |
| `azione.registra` | Registra | Record | |
| `azione.ferma` | Ferma | Stop | |
| `schermo.n` | Schermo {n} | Screen {n} | |
| `finestra.riduci` | Riduci a icona | Minimise | |
| `finestra.ingrandisci` | Ingrandisci | Maximise | |
| `finestra.chiudi` | Chiudi | Close | |

## Elenco call

| chiave | italiano | inglese | id |
|---|---|---|---|
| `call.sezione` | Call | Calls | |
| `call.senza_titolo` | Call #{n} | Call #{n} | |
| `call.senza_cliente` | Senza cliente | No client | |
| `call.stato.registrata` | Registrata | Recorded | |
| `call.stato.analizzata` | Analizzata | Analysed | |
| `call.stato.in_analisi` | Analisi in corso | Analysing | |
| `call.stato.non_riuscita` | Analisi non riuscita | Analysis failed | |
| `call.stato.in_corso` | In registrazione | Recording | |
| `call.n_task` | {n} task | {n} tasks | |
| `call.n_da_confermare` | {n} da confermare | {n} to confirm | |

## Trascrizione

| chiave | italiano | inglese | id |
|---|---|---|---|
| `trascrizione.n_righe` | {n} righe | {n} lines | |
| `trascrizione.parlante.mic` | Io | Me | ● etichetta di `mic` |
| `trascrizione.parlante.loopback` | Altri | Others | ● etichetta di `loopback` |
| `eco.conteggio` | {n} righe riprese dall'altoparlante | {n} lines your mic caught from the speakers | |
| `eco.nota` | tenute fuori da riassunto, note ed export | kept out of the summary, notes and exports | |
| `eco.etichetta_riga` | ripresa | echo | |
| `eco.sensibilita` | Sensibilità del filtro | Filter strength | |
| `eco.sensibilita.bassa` | Bassa | Low | ● etichetta di `basso` |
| `eco.sensibilita.media` | Media | Medium | ● etichetta di `medio` |
| `eco.sensibilita.alta` | Alta | High | ● etichetta di `alto` |
| `scatto.preso_a` | Scatto | Screenshot | |
| `voci.dai_un_nome` | Dai un nome alle voci | Name the speakers | |
| `scorrimento.torna_al_presente` | {n} righe nuove | {n} new lines | |

## Pannello analisi

| chiave | italiano | inglese | id |
|---|---|---|---|
| `analisi.sezione` | Analisi | Analysis | |
| `analisi.avvia` | Analizza la call | Analyse the call | |
| `analisi.in_corso` | Analisi in corso… | Analysing… | |
| `analisi.rianalizza` | Rianalizza | Re-analyse | |
| `analisi.tab.riassunto` | Riassunto | Summary | |
| `analisi.tab.salienti` | Punti salienti | Highlights | |
| `analisi.tab.task` | Task | Tasks | |
| `analisi.esce_dal_computer` | La trascrizione di {min} minuti è uscita da questo computer ed è stata inviata a {motore}. | The transcript of those {min} minutes left this computer and was sent to {motore}. | |
| `analisi.esce_prima` | La trascrizione di {min} minuti esce da questo computer e viene inviata a {motore}. | The transcript of these {min} minutes will leave this computer and be sent to {motore}. | |
| `nota_lavoro.sezione` | Nota di lavoro | Note so far | ⚠ da confermare — vedi in fondo |
| `nota_lavoro.aggiornata` | aggiornata alle {ora} | updated at {ora} | |
| `nota_lavoro.precedenti` | {n} note precedenti | {n} earlier notes | |

## Task e prove

| chiave | italiano | inglese | id |
|---|---|---|---|
| `rassegna.n_da_confermare` | task da confermare | tasks to confirm | |
| `rassegna.entra` | Passa in rassegna | Start the review | |
| `task.campo.titolo` | titolo | title | ● etichetta di `titolo` |
| `task.campo.assignee` | chi | who | ● etichetta di `assignee` |
| `task.campo.due_date` | entro | by | ● etichetta di `due_date` |
| `task.campo.priorita` | priorità | priority | ● etichetta di `priorita` |
| `task.campo.descrizione` | descrizione | description | |
| `task.non_detto` | non detto | not stated | |
| `task.scadenza_non_detta` | non detta | not stated | |
| `task.prove.sezione` | Da dove viene | Where this comes from | |
| `task.prove.n` | {n} prove | {n} sources | |
| `task.prove.nascondi` | Nascondi | Hide | |
| `task.prove.dedotta` | Dedotta. Nessuna frase della riunione la sostiene. | Inferred. No sentence in the meeting supports it. | |
| `task.conferma` | Conferma | Confirm | |
| `task.scarta` | Scarta | Discard | |
| `task.modifica` | Modifica | Edit | |
| `task.confermata` | Confermata | Confirmed | |
| `task.scartata` | Scartata | Discarded | |
| `task.annulla` | Annulla | Undo | |
| `task.confidenza` | confidenza {n} | confidence {n} | |
| `priorita.bassa` | bassa | low | ● etichetta di `bassa` |
| `priorita.media` | media | medium | ● etichetta di `media` |
| `priorita.alta` | alta | high | ● etichetta di `alta` |
| `priorita.critica` | critica | critical | ● etichetta di `critica` |

## Rifinitura

| chiave | italiano | inglese | id |
|---|---|---|---|
| `rifinitura.titolo` | Rifai la trascrizione | Redo the transcript | |
| `rifinitura.nota` | Canary, più preciso sui nomi · circa {n} min | Canary, better with names · about {n} min | |
| `rifinitura.avvia` | Avvia | Start | |
| `rifinitura.interrompi` | Interrompi | Stop | |
| `rifinitura.esito.rifinita` | Rifinita | Redone | |
| `rifinitura.esito.non_allineata` | Non allineata | Out of sync | |
| `rifinitura.esito.assente` | Audio assente | No audio | |
| `rifinitura.esito.vuota` | Traccia vuota | Empty track | |


## Registrazione dal vivo

| chiave | italiano | inglese | id |
|---|---|---|---|
| `call.in_corso` | Call in corso | Current call | |
| `call.stato.in_registrazione` | in registrazione | recording | |
| `side.durante` | Durante la call | While recording | |
| `side.analisi_dopo` | L'analisi si avvia quando fermi la registrazione. | The analysis starts when you stop recording. | |
| `scatti.sezione` | Scatti | Screenshots | |
| `audio.sezione` | Audio | Audio | |
| `audio.microfono` | Microfono | Microphone | |
| `audio.uscita` | Uscita | Output | |
| `audio.cambia` | Cambia | Change | |
| `overlay.sezione` | Overlay | Overlay | |
| `overlay.mostra` | Mostra | Show | |
| `avviso.scorciatoia_occupata` | {tasto} è già usata da un'altra applicazione: la scorciatoia dell'overlay non risponde. | {tasto} is already taken by another application: the overlay shortcut does nothing. | |
| `avviso.cambia_scorciatoia` | Cambia scorciatoia | Change the shortcut | |

## Rassegna

| chiave | italiano | inglese | id |
|---|---|---|---|
| `rassegna.sezione` | Rassegna | Review | |
| `rassegna.posizione` | {n} di {tot} | {n} of {tot} | |
| `rassegna.task_n` | Task {n} di {tot} | Task {n} of {tot} | |
| `rassegna.esci` | torna alla lista | back to the list | |
| `trascrizione.ferma_su_citate` | ferma sulle righe citate | held on the quoted lines | |
| `task.campo.titolo_esteso` | Titolo | Title | ● etichetta di `titolo` |
| `task.campo.responsabile` | Responsabile | Owner | ● etichetta di `assignee` |
| `task.campo.scadenza` | Scadenza | Due | ● etichetta di `due_date` |
| `task.nessun_responsabile` | nessun responsabile | no owner | |
| `task.nessuna_scadenza` | nessuna scadenza | no due date | |
| `task.nessuna_priorita` | nessuna priorità | no priority | |
| `task.solo_a_voce` | solo a voce: «{testo}» | said out loud only: “{testo}” | |
| `tasti.conferma` | conferma | confirm | |
| `tasti.scarta` | scarta | discard | |
| `tasti.scorri` | scorri | move | |

## Impostazioni

| chiave | italiano | inglese | id |
|---|---|---|---|
| `imp.sezione` | Impostazioni | Settings | |
| `imp.esci` | torna alla call | back to the call | |
| `imp.nav.motore` | Motore di analisi | Analysis engine | |
| `imp.nav.modelli` | Modelli locali | Local models | |
| `imp.nav.trascrizione` | Trascrizione | Transcription | |
| `imp.nav.rilevamento` | Rilevamento call | Call detection | |
| `imp.nav.scorciatoie` | Scorciatoie | Shortcuts | |
| `imp.nav.aspetto` | Aspetto | Appearance | |
| `imp.nav.analisi` | Analisi | Analysis | |
| `imp.nav.clienti` | Clienti | Clients | |
| `imp.nav.database` | Database remoto | Remote database | |
| `imp.nav.dati` | Dati e privacy | Data and privacy | |
| `imp.nav.export` | Export | Export | |
| `motore.intro` | Chi legge la trascrizione e ne ricava riassunto, punti salienti e task. Se ne può usare uno solo alla volta. | What reads the transcript and turns it into a summary, highlights and tasks. Only one at a time. | |
| `motore.velocita` | circa {n} min per un'ora di call | about {n} min per hour of call | |
| `motore.stato.in_uso` | In uso | In use | |
| `motore.stato.pronto` | Pronto | Ready | |
| `motore.stato.in_avvio` | In avvio… | Starting… | |
| `motore.stato.chiave_mancante` | Chiave mancante | Key missing | |
| `motore.stato.non_disponibile` | Non disponibile | Unavailable | |
| `motore.esce` | La trascrizione esce da questo computer e viene inviata a {dove}. | The transcript leaves this computer and is sent to {dove}. | |
| `motore.chiave` | Chiave API | API key | |
| `modelli.spazio` | Spazio su disco | Disk space | |
| `modelli.liberi_di` | {liberi} liberi di {totale} | {liberi} free of {totale} | |
| `modelli.apri_cartella` | Apri la cartella | Open the folder | |
| `modelli.stato.non_installato` | non installato | not installed | ● `non_installato` |
| `modelli.stato.in_download` | in download | downloading | ● `in_download` |
| `modelli.stato.in_pausa` | in pausa | paused | ● `in_pausa` |
| `modelli.stato.in_verifica` | in verifica | verifying | ● `in_verifica` |
| `modelli.stato.installato` | installato | installed | ● `installato` |
| `modelli.stato.in_uso` | in uso | in use | ● `in_uso` |
| `modelli.stato.spazio` | spazio insufficiente | not enough space | ● `spazio_insufficiente` |
| `modelli.rimanenti_min` | {n} min rimanenti | {n} min left | |
| `modelli.rimanenti_sec` | {n} s rimanenti | {n} s left | |
| `modelli.sospendi` | Sospendi | Pause | |
| `modelli.riprendi` | Riprendi | Resume | |
| `modelli.mancano` | Mancano {spazio}. Libera spazio o scegli un modello più piccolo. | {spazio} short. Free up space or pick a smaller model. | |
| `modelli.verifica_in_corso` | Scaricato. Controllo del file in corso. | Downloaded. Checking the file. | |
| `modelli.elimina_tutti` | Elimina tutti i modelli scaricati | Delete every downloaded model | |

## Overlay

| chiave | italiano | inglese | id |
|---|---|---|---|
| `overlay.salvato` | Salvato nella trascrizione | Saved to the transcript | |
| `overlay.apri` | Apri Scriba | Open Scriba | |
| `overlay.scatta` | Scatta | Capture | |
| `overlay.ferma` | Ferma | Stop | |
| `overlay.riduci` | Riduci la striscia | Shrink the strip | |
| `overlay.ingrandisci` | Ingrandisci la striscia | Grow the strip | |
| `overlay.nascondi` | Nascondi | Hide | |
| `overlay.tasto_mostra` | mostra e nasconde la striscia | shows and hides the strip | |
| `overlay.tasto_scatta` | scatta | takes a screenshot | |

## Dialoghi

| chiave | italiano | inglese | id |
|---|---|---|---|
| `consenso.titolo` | Registrare questa call | Record this call | |
| `consenso.sotto` | Verranno registrati il tuo microfono e l'audio del computer. | Your microphone and the computer's audio will both be recorded. | |
| `consenso.titolo_call` | Titolo (facoltativo) | Title (optional) | |
| `consenso.spunta` | Ho avvisato le persone in call che sto registrando. | I have told the people on this call that I am recording. | |
| `consenso.nota` | Registrare gli altri significa trattare i loro dati personali. Questa spunta viene annotata nella sessione, ma non sostituisce l'averglielo detto. | Recording other people means processing their personal data. This tick is stored with the session, but it is not a substitute for having told them. | |
| `consenso.senza` | Senza la conferma non si registra. | No recording without the confirmation. | |
| `consenso.invio` | Invio per registrare | Enter to record | |
| `rilevata.titolo` | Sembra che tu sia in una call su {app} | Looks like you are on a call in {app} | |
| `rilevata.sotto` | Posso registrarla. Include l'audio degli altri partecipanti, non solo la tua voce. | I can record it. That includes the other people's audio, not just your voice. | |
| `rilevata.no` | No grazie | No thanks | |
| `rilevata.nota` | torna alla prossima call | comes back on the next call | |
| `errore.modello_non_risponde` | Il modello locale non risponde | The local model is not responding | |
| `errore.riavvia_modello` | Riavvia il modello | Restart the model | |
| `errore.altro_motore` | Usa un altro motore | Use another engine | |
| `errore.microfono` | Il microfono non è quello che pensi | The microphone is not the one you think | |
| `errore.scegli_microfono` | Scegli un microfono | Pick a microphone | |
| `errore.solo_computer` | Registra solo l'audio del computer | Record the computer's audio only | |
| `errore.export` | Export non riuscito | Export failed | |
| `errore.altra_cartella` | Scegli un'altra cartella | Pick another folder | |
| `errore.riprova` | Riprova | Try again | |

## Archivio

| chiave | italiano | inglese | id |
|---|---|---|---|
| `archivio.sezione` | Archivio | Archive | |
| `archivio.riepilogo` | {n} call · {ore} ore registrate | {n} calls · {ore} hours recorded | |
| `archivio.cerca` | Cerca nel parlato | Search what was said | |
| `archivio.stato_qualsiasi` | Qualsiasi stato | Any status | |
| `archivio.periodo.sempre` | Sempre | All time | |
| `archivio.periodo.30` | Ultimi 30 giorni | Last 30 days | |
| `archivio.periodo.90` | Ultimi 3 mesi | Last 3 months | |
| `archivio.periodo.365` | Ultimo anno | Last year | |
| `archivio.raggruppa` | Raggruppa per cliente | Group by client | |
| `archivio.con_termine` | {n} con «{testo}» | {n} with “{testo}” | |
| `archivio.da_analizzare` | da analizzare | not analysed | |
| `ia.titolo` | {n} call in un documento solo | {n} calls in a single document | |
| `ia.sotto` | Ogni citazione accanto a ciò che sostiene, e detto chiaro quali impegni una fonte non ce l'hanno. | Every quote next to what it supports, and said plainly which commitments have no source. | |
| `ia.integrale` | Trascrizione integrale | Full transcript | |
| `ia.peso` | ~{n} token | ~{n} tokens | |

---

## Rese inglesi che restano da confermare

Le due che avevi segnato, con la proposta nuova e l'alternativa scartata.

**`nota_lavoro.sezione` — «Nota di lavoro» → «Note so far».**
Dice le due cose che servono: è una nota, e copre fino a adesso — che è
esattamente ciò che la distingue dal riassunto finale. «Running note» dice che
è continua ma non che è cumulativa, e in inglese suona più da diario che da
riassunto. Alternativa tenuta di scorta: «Interim note».

**`eco.conteggio` — «riprese dall'altoparlante» → «{n} lines your mic caught
from the speakers».** «Picked up from speakers» è ambiguo in inglese: *speaker*
è anche chi parla, e in una schermata che distingue i parlanti quella è
l'ambiguità peggiore possibile. Nominare il microfono la toglie. L'etichetta
sulla riga resta corta: `echo`.

## Date e ore in inglese

Nella pagina EN ho tenuto l'orologio a 24 ore (`12 Nov · 15:00`). L'alternativa
è `12 Nov · 3:00 PM`. Non è una scelta di design: dipende da chi lo userà.
Dimmi quale e la applico ovunque — le durate restano `mm:ss` in ogni caso.
