"""Controllo del database all'avvio, e backup a rotazione.

Nasce da un guasto vero, non da prudenza generica: un database si è presentato
con l'immagine malformata, il core ha continuato a scriverci dentro per ore, e a
quel punto l'unica copia della trascrizione di una call di due ore era il file
Markdown che l'utente aveva esportato a mano.

Due regole, entrambe imparate lì:

1. **Un database che non si legge non si usa.** Si mette da parte con tutto il
   suo WAL e si riparte dal backup più recente. Scriverci dentro non lo aggiusta
   e rende irrecuperabile quello che ancora si poteva salvare.
2. **Un backup si fa quando c'è qualcosa da salvare**, non a un orario. Ai due
   momenti in cui il lavoro di una call diventa definitivo — all'avvio (lo stato
   lasciato dalla volta prima) e a registrazione finita — il costo è una copia
   di pochi MB e il guadagno è non perdere mai più di una call.

`VACUUM INTO` e non una copia dei file: produce un database compatto e
consistente in un file solo, senza WAL a parte, quindi un backup non può
soffrire dello stesso disallineamento che ha causato il guasto.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

NOME_CARTELLA_BACKUP = "backup"
QUANTI_BACKUP = 5
_PREFISSO = "scriba-"


def _compagni(db_path: Path) -> list[Path]:
    """Il database e i file che gli appartengono. Vanno spostati insieme: un
    `-wal` lasciato indietro verrebbe riapplicato al database sbagliato."""
    return [db_path, *(db_path.with_name(db_path.name + suffisso) for suffisso in ("-wal", "-shm"))]


def _leggibile(db_path: Path) -> tuple[bool, str]:
    try:
        conn = sqlite3.connect(db_path)
        try:
            esito = [r[0] for r in conn.execute("PRAGMA quick_check")]
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return False, str(exc)
    if esito[:1] == ["ok"]:
        return True, "ok"
    return False, "; ".join(esito[:3])


def controlla(db_path: Path | str) -> dict[str, str] | None:
    """Verifica il database prima che il core cominci a usarlo.

    Se non è leggibile lo mette da parte e rimette al suo posto il backup più
    recente, quando c'è. Restituisce cosa è stato fatto (per i log e per
    l'interfaccia), oppure None se non c'era niente da fare.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return None

    ok, motivo = _leggibile(db_path)
    if ok:
        return None

    quarantena = db_path.parent / f"danneggiato-{datetime.now():%Y-%m-%d-%H%M%S}"
    quarantena.mkdir(parents=True, exist_ok=True)
    for percorso in _compagni(db_path):
        if percorso.exists():
            shutil.move(str(percorso), quarantena / percorso.name)

    esito = {"motivo": motivo, "quarantena": str(quarantena), "ripristinato": ""}
    ultimo = ultimo_backup(db_path)
    if ultimo is not None:
        shutil.copy2(ultimo, db_path)
        esito["ripristinato"] = str(ultimo)
        log.error(
            "Database illeggibile (%s): messo da parte in %s, ripristinato il backup %s",
            motivo, quarantena.name, ultimo.name,
        )
    else:
        log.error(
            "Database illeggibile (%s): messo da parte in %s. Nessun backup disponibile: "
            "si ricomincia da vuoto, i file messi da parte non vanno cancellati.",
            motivo, quarantena.name,
        )
    return esito


def cartella_backup(db_path: Path | str) -> Path:
    return Path(db_path).parent / NOME_CARTELLA_BACKUP


def backup_esistenti(db_path: Path | str) -> list[Path]:
    cartella = cartella_backup(db_path)
    if not cartella.exists():
        return []
    return sorted(cartella.glob(f"{_PREFISSO}*.sqlite"))


def ultimo_backup(db_path: Path | str) -> Path | None:
    esistenti = backup_esistenti(db_path)
    return esistenti[-1] if esistenti else None


def backup(store, *, quanti: int = QUANTI_BACKUP) -> Path | None:
    """Una copia compatta del database, tenendone le ultime `quanti`.

    Non solleva: un backup che non riesce è un peccato, fermare una
    registrazione perché non si è potuto fare è un danno peggiore.
    """
    db_path = Path(store.path)
    cartella = cartella_backup(db_path)
    cartella.mkdir(parents=True, exist_ok=True)
    # Fino ai microsecondi: due backup nello stesso secondo — succede a fine
    # registrazione seguita da un'analisi veloce — non devono sovrascriversi.
    # Il formato resta ordinabile come testo, ed è così che si trova l'ultimo.
    destinazione = cartella / f"{_PREFISSO}{datetime.now():%Y-%m-%d-%H%M%S-%f}.sqlite"

    try:
        if destinazione.exists():
            destinazione.unlink()
        # Il percorso va dentro la stringa SQL: si raddoppiano gli apici, che è
        # l'unico modo di scriverlo qui (un parametro non è ammesso in VACUUM).
        store.conn.execute(f"VACUUM INTO '{str(destinazione).replace(chr(39), chr(39) * 2)}'")
    except sqlite3.Error as exc:
        log.warning("Backup del database non riuscito: %s", exc)
        return None

    for vecchio in backup_esistenti(db_path)[:-quanti]:
        try:
            vecchio.unlink()
        except OSError:
            pass
    return destinazione
