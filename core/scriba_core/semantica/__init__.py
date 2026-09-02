"""Ricerca per significato: l'indice, il modello che lo produce, le catene.

L'indice FTS5 che c'era già sa dire dove compare una parola. Qui c'è l'altra
metà — dove si è parlato di una cosa — e il pezzo su cui si appoggia la
ricerca contestuale (`ai/contesto.py`), che di questo materiale fa una
risposta.
"""

from .catene import Catena, catene
from .indice import MARGINE, MARGINE_LARGO, Indice, IndiceVuoto, Riepilogo, Trovato
from .modello import Embedder, ErroreSemantica, EmbedderE5, carica, installato
from .spezza import Passaggio, in_passaggi

__all__ = [
    "MARGINE",
    "MARGINE_LARGO",
    "Catena",
    "Embedder",
    "EmbedderE5",
    "ErroreSemantica",
    "Indice",
    "IndiceVuoto",
    "Passaggio",
    "Riepilogo",
    "Trovato",
    "carica",
    "catene",
    "in_passaggi",
    "installato",
]
