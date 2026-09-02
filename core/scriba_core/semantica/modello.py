"""Il modello che trasforma il parlato in vettori confrontabili.

Sta in locale, come l'analisi e per lo stesso motivo scritto in `llm/base.py`:
una call di lavoro contiene nomi, cifre e questioni che non c'è motivo di
mandare fuori. Qui la ragione pesa di più che altrove — indicizzare vuol dire
spedire **l'archivio intero**, non una call — e non c'è nemmeno la via di
mezzo: Anthropic non espone un'API di embedding, quindi «come per l'analisi,
scegli il provider» non sarebbe nemmeno vero.

Il modello è `multilingual-e5-small`: 384 dimensioni, circa 100 lingue, e su
CPU indicizza un'ora di parlato in una manciata di secondi. Gira con
onnxruntime, che l'applicazione si porta già dietro per la trascrizione: la
ricerca semantica non aggiunge quindi un motore, aggiunge dei pesi.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import numpy as np

# E5 vuole sapere se sta leggendo una domanda o del materiale, e lo si dice con
# un prefisso nel testo. Non è un dettaglio estetico: senza, le domande finiscono
# in una zona dello spazio diversa da quella dei passaggi e la somiglianza
# misurata è sistematicamente più bassa di quella vera.
PREFISSI = {"passaggio": "passage: ", "domanda": "query: "}

# Quanti caratteri del passaggio arrivano davvero al modello. Il modello ne
# legge 512 token; il taglio qui è una difesa contro un passaggio anomalo, non
# il limite normale (vedi spezza.CARATTERI).
TAGLIO = 2000


class ErroreSemantica(RuntimeError):
    """Il modello non c'è, non si carica, o non ha prodotto vettori."""


class Embedder(Protocol):
    """Tutto quello che l'indice pretende da un modello.

    Poco di proposito: un `Embedder` finto in un test deve poter essere venti
    righe, altrimenti i test dell'indice diventano test del modello — lenti,
    e verdi o rossi per il motivo sbagliato.
    """

    id: str
    dim: int

    def vettori(self, testi: list[str], *, come: str) -> np.ndarray:
        """Una matrice (n, dim) di vettori normalizzati a lunghezza 1."""
        ...


class EmbedderE5:
    """`multilingual-e5-small` dietro onnxruntime."""

    id = "multilingual-e5-small"
    dim = 384

    def __init__(self, modello: Path, tokenizer: Path, *, lotto: int = 16) -> None:
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:  # pragma: no cover - dipende dall'installazione
            raise ErroreSemantica(f"Manca una libreria per la ricerca semantica: {exc}") from exc

        opzioni = ort.SessionOptions()
        # Metà dei core, non tutti. L'indicizzazione dell'archivio è un lavoro
        # di sottofondo che può durare minuti: prendersi la macchina intera
        # mentre qualcuno la sta usando è il modo di far sembrare rotta una
        # funzione che sta solo lavorando.
        opzioni.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
        try:
            self._sessione = ort.InferenceSession(
                str(modello), opzioni, providers=["CPUExecutionProvider"]
            )
            self._tokenizer = Tokenizer.from_file(str(tokenizer))
        except Exception as exc:
            raise ErroreSemantica(f"Il modello per la ricerca semantica non si carica: {exc}") from exc

        self._tokenizer.enable_truncation(max_length=512)
        pad = self._tokenizer.token_to_id("<pad>")
        self._tokenizer.enable_padding(pad_id=pad if pad is not None else 1, pad_token="<pad>")
        # I nomi degli ingressi si leggono dal grafo invece di scriverli a mano:
        # una conversione ONNX diversa può chiamarli in un altro modo, e un
        # KeyError a metà indicizzazione è peggio di un errore all'avvio.
        self._ingressi = {i.name for i in self._sessione.get_inputs()}
        self._lotto = lotto

    def vettori(self, testi: list[str], *, come: str) -> np.ndarray:
        if come not in PREFISSI:
            raise ErroreSemantica(f"Non so cosa sia un testo di tipo «{come}».")
        if not testi:
            return np.zeros((0, self.dim), dtype=np.float32)

        prefisso = PREFISSI[come]
        fuori = []
        for i in range(0, len(testi), self._lotto):
            pezzo = [prefisso + t[:TAGLIO] for t in testi[i : i + self._lotto]]
            fuori.append(self._lotto_di(pezzo))
        return np.vstack(fuori)

    def _lotto_di(self, testi: list[str]) -> np.ndarray:
        codifiche = self._tokenizer.encode_batch(testi)
        ids = np.array([c.ids for c in codifiche], dtype=np.int64)
        maschera = np.array([c.attention_mask for c in codifiche], dtype=np.int64)

        ingressi = {"input_ids": ids, "attention_mask": maschera}
        if "token_type_ids" in self._ingressi:
            ingressi["token_type_ids"] = np.zeros_like(ids)
        uscita = self._sessione.run(None, {k: v for k, v in ingressi.items() if k in self._ingressi})
        stati = np.asarray(uscita[0], dtype=np.float32)

        # Media sui token veri, non su tutti: i token di riempimento sono lì
        # per far quadrare la matrice e includerli sposterebbe ogni vettore
        # verso il vettore del riempimento, tanto più quanto il testo è corto.
        peso = maschera.astype(np.float32)[:, :, None]
        somma = (stati * peso).sum(axis=1)
        quanti = np.clip(peso.sum(axis=1), 1e-9, None)
        return _normalizza(somma / quanti)


def _normalizza(v: np.ndarray) -> np.ndarray:
    """Porta ogni riga a lunghezza 1, così il coseno è un prodotto scalare.

    Fatto una volta qui invece che a ogni ricerca: i vettori si scrivono nel
    database già normalizzati e cercare diventa una moltiplicazione di matrici
    e niente altro.
    """
    lunghezze = np.linalg.norm(v, axis=1, keepdims=True)
    return (v / np.clip(lunghezze, 1e-9, None)).astype(np.float32)


# Il repo su Hugging Face, pinnato al commit come tutti gli altri modelli:
# «main» può cambiare fra il momento in cui si scarica e quello in cui si
# verifica, e i pesi di un modello non sono una cosa che debba cambiare da sé.
REPO = "intfloat/multilingual-e5-small"
COMMIT = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILE_MODELLO = "onnx/model.onnx"
FILE_TOKENIZER = "tokenizer.json"


def scarica() -> tuple[Path, Path]:
    """Prende i due file dal repo e li lascia nella cache di Hugging Face.

    La stessa cache in cui stanno Parakeet e Canary: è già gestita, sa
    riprendere un download interrotto, e `models_manager` sa già guardarci
    dentro per dire se un modello è installato.
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:  # pragma: no cover - dipende dall'installazione
        raise ErroreSemantica(f"Manca huggingface_hub: {exc}") from exc

    percorsi = [
        Path(hf_hub_download(REPO, f, revision=COMMIT)) for f in (FILE_MODELLO, FILE_TOKENIZER)
    ]
    return percorsi[0], percorsi[1]


def carica() -> EmbedderE5:
    """Il modello pronto all'uso, scaricandolo se non c'è ancora.

    Chi chiama deve essersi già assicurato che scaricare vada bene adesso: qui
    dentro non c'è modo di distinguere «manca» da «è la prima volta», e
    trecento megabyte che partono da soli in mezzo a una ricerca non sono una
    sorpresa gradita.
    """
    modello, tokenizer = scarica()
    return EmbedderE5(modello, tokenizer)


def installato() -> bool:
    """I pesi ci sono già sul disco, senza toccare la rete."""
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:  # pragma: no cover - dipende dall'installazione
        return False
    return all(
        isinstance(try_to_load_from_cache(REPO, f, revision=COMMIT), str)
        for f in (FILE_MODELLO, FILE_TOKENIZER)
    )
