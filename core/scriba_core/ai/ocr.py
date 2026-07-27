"""Legge il testo dagli screenshot presi durante la call.

Uno screenshot senza testo estratto è un file su disco: l'analisi non può
tenerne conto. Con il testo, invece, la slide che qualcuno stava condividendo
entra nel contesto insieme a quello che si diceva in quel momento.

Si usa il motore OCR incorporato in Windows: nessun modello da scaricare,
nessuna dipendenza nativa da compilare, e funziona offline come il resto
dell'applicazione. Su una slide di prova con testo italiano ha restituito il
contenuto senza errori.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Sotto questa soglia il risultato è probabilmente rumore: bordi di finestre,
# icone, frammenti di menu. Mandarlo all'analisi confonde e basta.
MIN_CARATTERI = 12


def disponibile() -> bool:
    try:
        import winsdk.windows.media.ocr  # noqa: F401
    except Exception:
        return False
    return True


async def _leggi(percorso: str) -> str:
    import winsdk.windows.media.ocr as ocr
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.storage import FileAccessMode, StorageFile

    motore = ocr.OcrEngine.try_create_from_user_profile_languages()
    if motore is None:
        return ""

    file = await StorageFile.get_file_from_path_async(percorso)
    stream = await file.open_async(FileAccessMode.READ)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    risultato = await motore.recognize_async(bitmap)
    return risultato.text or ""


def leggi_testo(percorso: str | Path) -> str | None:
    """Restituisce il testo trovato nell'immagine, o None se non c'è o non si può.

    Non solleva: un OCR fallito non deve far saltare la registrazione in corso.
    Peggiora l'analisi, non la interrompe.
    """
    percorso = Path(percorso)
    if not percorso.exists():
        return None

    try:
        testo = asyncio.run(_leggi(str(percorso.resolve())))
    except Exception as exc:
        log.warning("OCR non riuscito su %s: %s", percorso.name, exc)
        return None

    testo = " ".join(testo.split())
    return testo if len(testo) >= MIN_CARATTERI else None
