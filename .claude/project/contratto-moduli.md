# Contratto fra i moduli — lavoro in parallelo

Questo file esiste perché più persone stanno scrivendo pezzi che si incastrano
fra loro nello stesso momento. Chi implementa un modulo e chi lo usa scrivono
tutti e due contro quello che c'è qui, senza aspettarsi a vicenda.

**Se una firma qui sotto ti sembra sbagliata, dillo nel rapporto: non cambiarla.**
Cambiarla in silenzio rompe il lavoro di qualcun altro che è già partito.

---

## Note correnti durante la call

Modulo: `core/scriba_core/ai/note_correnti.py`

```python
class GestoreNote:
    def __init__(self, store, settings, publish) -> None: ...
    def avvia(self, session_id: int) -> None: ...
    def ferma(self) -> None: ...
    @property
    def attivo(self) -> bool: ...
```

`publish(payload: dict)` è il broadcaster del server. Gli eventi emessi:

```
{"type": "nota", "stato": "in_corso", "session_id": 12}
{"type": "nota", "stato": "fatta", "session_id": 12, "t_ms": 600000, "testo": "..."}
{"type": "nota", "stato": "errore", "session_id": 12, "dettaglio": "..."}
```

`server.py` chiama `avvia()` all'inizio della registrazione e `ferma()` alla
fine, solo quando `settings` ha `note_incrementali` a vero. `ferma()` deve
essere sicuro anche se non è mai partito niente.

## Diarizzazione

Modulo: `core/scriba_core/stt/diarizzazione.py`

```python
class Diarizzatore:
    def disponibile(self) -> bool: ...
    def assegna(self, session_id: int, store, *, avanzamento=None) -> dict: ...
```

Gira **a call finita, sull'audio salvato**, e scrive `speakers` e
`transcript_segments.speaker_id`. Non tocca `speaker_raw`, che è verità di
campo: dice da quale traccia è entrato il suono, e nessun modello lo può
smentire. Restituisce `{"voci": 3, "segmenti_assegnati": 412}`.

`avanzamento(frazione: float, nota: str)` è facoltativo.

## Export

Modulo: `core/scriba_core/export/__init__.py`

```python
def esporta(session_id: int, store, *, formato: str, destinazione: Path | None) -> Path
```

`formato` ∈ `markdown` | `testo` | `json`. Se `destinazione` è `None` si usa
`export.cartella` dalle impostazioni, e se manca anche quella `dati/export`.

Connettori: `export/notion.py`, `export/http_generico.py`, entrambi con

```python
def invia(session_id: int, store, config: dict) -> dict   # {"url": "...", "creati": 3}
```

---

## Forme condivise con l'interfaccia

`ui/renderer/tipi.ts` **è la definizione**. Chi tocca il JSON del core aggiorna
lì, e chi tocca l'interfaccia legge da lì.

Aggiunte di questo giro:

```ts
interface Segmento {
  // ...quello che c'è già...
  /** Chi ha parlato, quando la diarizzazione è stata eseguita. Altrimenti null. */
  speaker?: { id: number; label: string; nome_reale: string | null } | null
}
```

`GET /sessions/{id}/segments` porta `speaker` a null finché nessuno ha
diarizzato quella call: l'interfaccia deve continuare a funzionare con «Io» e
«Altri», che restano l'unica cosa certa.

## Impostazioni: chi legge cosa

Ogni riga qui è un interruttore che oggi si sposta senza produrre effetti. Chi
la prende in carico la fa funzionare **davvero**, e lo dimostra con un test.

| Chiave | Chi la deve leggere |
|---|---|
| `stt.microfono_id`, `stt.loopback_id` | `recorder.py` all'apertura dei device |
| `stt.filtro_eco` | `stt/eco.py`, soglia per livello |
| `analisi_automatica` | `server.py`, a fine registrazione |
| `note_incrementali` | `server.py`, avvia `GestoreNote` |
| `rilevamento.avvio_automatico` | `server.py` |
| `export.cartella`, `export.formato` | `export/__init__.py` |

### Il consenso non si salta, nemmeno avviando da soli

`rilevamento.avvio_automatico` **non** fa partire la registrazione senza
conferma. Il design è esplicito: «Anche avviando da sola, il consenso resta
obbligatorio: la registrazione parte solo dopo la spunta». Quello che cambia è
l'insistenza — invece di una proposta che si può ignorare, si apre la finestra
con il consenso già davanti. Chi implementa questa chiave e la fa registrare in
autonomia sta scrivendo un difetto, non una funzione.
