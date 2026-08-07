# Scriba — Modello dati

> Fonte di verità: [`core/scriba_core/db/schema.sql`](../../core/scriba_core/db/schema.sql)
> e le migrazioni in [`db/store.py`](../../core/scriba_core/db/store.py).
> Qui si spiega l'intento: perché una tabella è fatta così e cosa deve restare vero.
> Ultimo aggiornamento: 2026-08-02.

SQLite in modalità WAL. Due vincoli hanno guidato quasi tutte le scelte: durante
una call ci sono **due scrittori** (le due tracce) e almeno un lettore (la UI che
mostra il testo mentre si parla); e **ogni task deve poter dimostrare da dove
viene**, anche dopo che il segmento da cui viene è stato rifinito.

## Entità principali

### `clients` — i clienti
- Chiave: `id`. `uuid` per export e sync. `nome_norm` **unique**.
- `nome_norm` è il nome ridotto a forma confrontabile (minuscolo, spazi
  normalizzati): è lì che si decide se due righe di un CSV importato sono lo
  stesso cliente, e va deciso una volta sola invece che a ogni confronto.
- `archiviato` invece dell'eliminazione: un cliente con cui non si lavora più
  sparisce dagli elenchi, ma le sue call restano attribuite a qualcuno.

### `sessions` — le call
- `uuid` è l'identità stabile, e l'unica che vale fuori da questo file.
- `audio_mic_path` / `audio_loop_path` separati: consentono di ri-trascrivere una
  sola sorgente senza rifare tutto.
- `consenso_confermato_at` annota che l'utente ha confermato di aver avvisato
  gli altri, e quando. Registrare altre persone è una responsabilità.
- `client_id` → `clients`. Sui database creati prima dei clienti arriva da un
  `ALTER TABLE`, che in SQLite **non può portarsi dietro la chiave esterna**: là
  è un intero e basta. Perché la differenza non si veda da nessuna parte, a
  ripulire i riferimenti pensa `Store.elimina_cliente`, non il vincolo.

### `transcript_segments` — la trascrizione
- `source` (`mic` | `loopback`) viene dalla traccia da cui il suono è entrato: è
  esatto per costruzione e **non va mai sovrascritto da un'inferenza**. I nomi
  dei parlanti sono un livello a parte (`speakers`, `speaker_id`).
- Un segmento provvisorio viene **aggiornato**, non cancellato e reinserito:
  `revision` cresce, l'`id` resta. È ciò che tiene valide le prove che puntano lì.
- `testo_originale` (aggiunto per migrazione) conserva com'era la frase **prima di
  ogni ritocco automatico**: il glossario che rimette a posto i nomi propri
  (`stt/glossario.py`) e la passata di rifinitura che la ritrascrive con un altro
  modello (`stt/rifinitura.py`). NULL quando non è stato toccato niente, che è il
  caso normale. Si scrive con `COALESCE`, quindi resta la **prima** versione, non
  l'ultima: quella dal vivo è l'unica che nessun automatismo ha già riscritto.
  Senza, la correzione non sarebbe né verificabile né annullabile — e l'app sta
  mettendo in bocca a qualcuno parole che il modello non ha sentito.
- `eco` (aggiunto per migrazione) segna le righe in cui il microfono ha ripreso
  l'altoparlante: le stesse parole ci sono già sull'altra traccia, dette da chi le
  ha dette. **Non si cancellano**, sono una riga su tre e un giudizio sbagliato
  deve restare guardabile (D-020). A tenerle fuori è `Store.segments()`, che le
  esclude se non le si chiede: analisi, note, export, rifinitura e diarizzazione
  passano tutte di lì e non filtrano niente per conto loro. Le chiede solo la
  schermata della trascrizione, per mostrarle sbiadite e mai attribuite a «Io».
  Nasce a 0 su tutto ciò che è già stato trascritto — quelle righe di eco ci sono
  davvero, e dire di no sarebbe un valore di comodo.
- `t_start_ms` / `t_end_ms` sono l'orologio della **call**, e da #45 il file audio lo
  rispetta: i buchi di consegna vengono riempiti di silenzio, quindi il secondo 900
  del file è il secondo 900 della call. Resta uno scarto proporzionale di ~0.2% —
  la scheda audio non campiona esattamente alla frequenza dichiarata — che si
  corregge confrontando la lunghezza del file con `sessions.durata_ms`. **Sulle call
  registrate prima non vale**, e nel file non c'è l'informazione per rimediare: chi
  torna sull'audio da questi numeri lo verifica (vedi `stt/rifinitura.py`), non lo dà
  per buono.
- `segments_fts` è un indice FTS5 esterno tenuto allineato da tre trigger. Indicizza
  `testo`, cioè la **versione corretta**: cercare «Clotilde» deve trovare la call
  in cui il modello aveva scritto *Cotilde*, che è il punto di tutto il glossario.

### `tasks` — gli impegni estratti
- `uuid` (indice unico parziale, aggiunto per migrazione): `tasks.id` è un
  contatore di **questo** file, quindi due installazioni si sovrascriverebbero a
  vicenda su un database condiviso, e ricostruire il database locale — è già
  successo — rimescolerebbe ogni riferimento.
- `export_status` / `export_target` / `export_ref` ne reggono **una sola**
  destinazione, e oggi se le prende Notion. Chi aggiunge un'altra destinazione
  non deve scriverci dentro: vedi `sync_remoto`.

### `task_evidence` — da dove viene ogni campo
La tabella che risolve il problema centrale del progetto. In una call vera il
lavoro si nomina al minuto 5, la scadenza si concorda al 32 e il responsabile si
decide al 48: la granularità è quindi **per campo** (`supports`), non per task,
altrimenti non si può mostrare «questa scadenza viene da qui». `quote` è una
copia del testo al momento dell'estrazione, duplicata di proposito — se il
segmento viene poi rifinito, la citazione già mostrata non cambia sotto gli occhi.

### `ai_outputs` — riassunti e salienti
Le rigenerazioni non cancellano le precedenti (`is_current`, `version`): servono
a confrontare le versioni di prompt fra loro. Indice unico parziale su
`(session_id, kind, scope)` per `is_current = 1`.

### `screenshots`
Metadati e `ocr_text`. Se l'OCR copre già il contenuto si evita di mandare
l'immagine al modello. `phash` per non ripetere due volte la stessa slide.

### `sync_remoto` — esito della sincronizzazione remota
Una riga per sessione, con `esito` e `errore`. **Una tabella sua e non le colonne
`export_*` di `tasks`**: quelle ne reggono una destinazione sola, e scriverci
dentro anche il database remoto farebbe sì che esportare verso uno dei due
azzeri il riferimento dell'altro — e la volta dopo le task verrebbero create di
nuovo, in silenzio, dentro il sistema di lavoro di qualcuno.

### `analysis_meta`
Esito dell'ultimo tentativo di analisi. `session_id` come chiave primaria
permette un UPSERT senza cercare prima. `errore` si aggiorna indipendentemente
dal resto: una call già analizzata con successo deve continuare a mostrare quel
risultato anche se un «Rianalizza» successivo fallisce.

## Macchine a stati

### Sessione — `sessions.stato`
```
recording → transcribing → ready → analyzed
     │                       │        │
     └───────────────────────┴────────┴──→ error
```
Verso l'interfaccia gli stati sono cinque e diversi: `recording`, `recorded`,
`analyzing`, `analyzed`, `failed`. `analyzing` **non è persistito** — vive solo
nello stato del processo — e `ready`/`transcribing` diventano entrambi
«registrata». La traduzione sta in `api/__init__.py` e la usano sia l'elenco
delle call sia l'archivio: la stessa call non deve risultare in due stati diversi
a seconda della schermata.

### Task — `tasks.stato`
```
proposed → confirmed → done
   │  └──→ merged (in un'altra task, via merged_into_id)
   └─────→ rejected
```
`needs_review` è indipendente dallo stato: dice se un umano deve ancora guardarla.

## Regole di integrità

- **`source` non si inventa.** Nessun percorso di codice può cambiare la traccia
  di un segmento sulla base di un'inferenza.
- **Le citazioni non si accettano da chi chiama.** `add_task` legge il testo dal
  segmento indicato, non dal parametro: è la garanzia che una prova non possa
  essere inventata da un modello.
- **Ogni tabella sincronizzata ha una chiave naturale.** Senza, risincronizzare
  duplica; ed è coperto da un test che gira su tutte le tabelle del modello.
- **Eliminare un cliente non elimina le sue call.**

## Migrazioni

Non c'è un sistema di migrazione versionate: `_migrate()` esegue `schema.sql`
(tutto `CREATE ... IF NOT EXISTS`), poi `_SCHEMA_EXTRA`, poi una funzione per
colonna aggiunta dopo. Le regole che ne derivano, e che sono state pagate:

1. **`CREATE TABLE IF NOT EXISTS` non aggiunge colonne** a una tabella che
   esiste già. Ogni colonna nuova vuole la sua funzione di migrazione.
2. **`schema.sql` gira _prima_ delle migrazioni.** Un indice su una colonna
   aggiunta per migrazione, messo in `schema.sql`, fa fallire l'avvio su ogni
   database esistente. Va creato dentro la funzione, dopo l'`ALTER`.
3. **Le chiavi esterne non si aggiungono con `ALTER TABLE`** in SQLite. Se il
   vincolo serve, il comportamento va garantito dal codice, uguale sui database
   vecchi e su quelli nuovi.
