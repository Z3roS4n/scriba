"""Nessun modulo del core usa un nome che non esiste.

Nasce da un difetto vero (#102). Traducendo il database remoto, una chiamata è
stata scritta come se la funzione avesse un parametro `lingua` che non ha mai
ricevuto:

    colonna_sql(t.chiave, c.chiave, c.etichetta, c.descrizione, lingua)

Python non se ne accorge fino a quando quella riga non viene eseguita, e quella
riga si esegue solo dopo essersi collegati a un PostgreSQL vero. Risultato: la
mappatura su tabelle esistenti non funzionava del tutto, per due rilasci, e
l'unico test che la copre si salta da solo quando un server non c'è.

Niente di quello che avevamo poteva vederlo. L'import no — il difetto è dentro
il corpo di una funzione. `tsc` guarda l'interfaccia. I due cancelli sulle
stringhe guardano le stringhe, non il codice che le usa. Il test che la
chiamava era `skip`.

Un nome inesistente si trova senza eseguire niente: basta risolvere gli scope,
ed è quello che fa pyflakes. Qui si tiene **solo** quella famiglia di
segnalazioni: un import inutilizzato è una questione di stile, e i pochi che ci
sono nel core sono voluti (si importa `winsdk...ocr` per sapere se c'è). Un
nome che non esiste non è mai voluto.
"""

from __future__ import annotations

import ast
from pathlib import Path

# Importato senza rete di salvataggio, e apposta: `importorskip` qui
# trasformerebbe «pyflakes non c'è» in un verde. Un cancello che si spegne da
# solo quando manca il suo strumento è indistinguibile da un cancello che
# passa, ed è il modo in cui questi controlli muoiono. Sta in
# `requirements-dev.txt`, accanto a pytest: chi può eseguire questo file ce
# l'ha già.
from pyflakes import messages as segnalazioni
from pyflakes.checker import Checker

CORE = Path(__file__).resolve().parents[1]

#: Le tre famiglie che dicono «questo nome, qui, non c'è».
INESISTENTI = (
    segnalazioni.UndefinedName,
    segnalazioni.UndefinedLocal,
    segnalazioni.UndefinedExport,
)


def _moduli() -> list[Path]:
    return sorted(
        p
        for cartella in ("scriba_core", "tests")
        for p in (CORE / cartella).rglob("*.py")
        if "__pycache__" not in p.parts
    )


def test_nessun_nome_inesistente() -> None:
    trovati: list[str] = []
    for percorso in _moduli():
        sorgente = percorso.read_text(encoding="utf-8")
        albero = ast.parse(sorgente, filename=str(percorso))
        for msg in Checker(albero, filename=str(percorso)).messages:
            if isinstance(msg, INESISTENTI):
                relativo = percorso.relative_to(CORE)
                trovati.append(f"{relativo}:{msg.lineno} {msg.message % msg.message_args}")

    assert not trovati, "Nomi che non esistono:\n" + "\n".join("   " + t for t in trovati)


def test_il_controllo_guarda_davvero_i_moduli() -> None:
    """Zero moduli letti darebbe verde senza aver guardato niente."""
    moduli = _moduli()
    assert len(moduli) > 50, f"solo {len(moduli)} moduli trovati: il percorso è sbagliato"
    assert any(p.name == "__init__.py" and p.parent.name == "sql" for p in moduli)


def test_il_controllo_prende_il_difetto_che_lo_ha_fatto_scrivere() -> None:
    """La stessa forma di #102, scritta apposta: se non la vede, non serve a niente."""
    difetto = "def f(a):\n    return g(a, lingua)\n"
    msgs = Checker(ast.parse(difetto), filename="finto.py").messages
    assert [m for m in msgs if isinstance(m, INESISTENTI)]
