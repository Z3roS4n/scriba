"""La lingua dell'interfaccia arriva al core, e cambia solo quello che si legge.

Il rischio di questa funzione non è che non traduca: è che traduca **troppo**.
Un identificatore tradotto — `local` che diventa `local model`, `alta` che
diventa `high` in una richiesta — non si vede finché qualcosa non smette di
combaciare, e allora sembra un difetto di tutt'altro.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.i18n import errore, lingua_da_header, motore  # noqa: E402
from scriba_core.server import PROVIDERS_INFO  # noqa: E402


class TestQualeLingua:
    def test_le_forme_regionali_valgono(self) -> None:
        # `en-GB` è inglese. Rifiutarlo vorrebbe dire ripiegare sull'italiano
        # per un'interfaccia che la sua lingua l'aveva dichiarata.
        assert lingua_da_header("en-GB") == "en"
        assert lingua_da_header("it_IT") == "it"

    def test_si_prende_la_prima_conosciuta(self) -> None:
        assert lingua_da_header("de-DE,en;q=0.9,it;q=0.8") == "en"

    def test_senza_intestazione_resta_l_italiano(self) -> None:
        # Il comportamento di sempre: una richiesta che non dice niente non
        # deve cambiare quello che l'utente vedeva prima.
        assert lingua_da_header(None) == "it"
        assert lingua_da_header("") == "it"
        assert lingua_da_header("de,fr") == "it"


class TestMotori:
    def test_in_inglese_cambiano_i_tre_testi(self) -> None:
        info = motore(PROVIDERS_INFO["local"], "local", "en")
        assert info["etichetta"] == "Local model"
        assert "leaves the computer" in info["descrizione"]
        assert "Settings" in info["rimedio"]

    def test_gli_identificatori_non_si_traducono(self) -> None:
        """È il punto: si traduce dove si mostra, mai dove si confronta."""
        it = PROVIDERS_INFO["anthropic"]
        en = motore(it, "anthropic", "en")
        assert en["model"] == it["model"]
        assert en["esce_dal_computer"] == it["esce_dal_computer"]
        assert en["costo_ora_usd"] == it["costo_ora_usd"]
        assert en["minuti_per_ora"] == it["minuti_per_ora"]

    def test_l_italiano_resta_quello_di_prima(self) -> None:
        for id_, info in PROVIDERS_INFO.items():
            assert motore(info, id_, "it") == info

    def test_la_tabella_condivisa_non_viene_scritta(self) -> None:
        # Senza la copia, la prima richiesta in inglese lascerebbe la tabella
        # inglese per tutti — compreso chi guarda in italiano.
        prima = PROVIDERS_INFO["local"]["etichetta"]
        motore(PROVIDERS_INFO["local"], "local", "en")
        assert PROVIDERS_INFO["local"]["etichetta"] == prima

    def test_ogni_motore_ha_la_sua_traduzione(self) -> None:
        # Un motore aggiunto e non tradotto uscirebbe in italiano dentro
        # un'interfaccia inglese, e sembrerebbe una scelta.
        for id_, info in PROVIDERS_INFO.items():
            en = motore(info, id_, "en")
            assert en["etichetta"] != info["etichetta"], id_


class TestMessaggiDiErrore:
    """I messaggi d'errore, tradotti dove escono e non dove nascono.

    `ErroreSql` viene sollevato in fondo al modulo Postgres e diventa il
    `detail` di una risposta tre livelli più su: passargli la lingua vorrebbe
    dire cambiare la firma di mezza libreria per un testo. Il gestore delle
    eccezioni la richiesta ce l'ha, e vale per tutte le rotte — comprese
    quelle che nessuno ha ancora scritto.
    """

    def test_quello_esatto_si_traduce(self) -> None:
        assert errore("sessione inesistente", "en") == "no such call"

    def test_quello_col_valore_dentro_tiene_il_valore(self) -> None:
        # Il pezzo variabile è un identificatore: tradurlo sarebbe l'errore
        # opposto, e molto peggiore.
        assert errore("Tabella sconosciuta: call", "en") == "Unknown table: call"

    def test_in_italiano_non_si_tocca(self) -> None:
        assert errore("sessione inesistente", "it") == "sessione inesistente"

    def test_uno_che_non_conosciamo_resta_leggibile(self) -> None:
        # Meglio una frase italiana giusta di una chiave o di una casella vuota.
        assert errore("non l'ho mai visto", "en") == "non l'ho mai visto"


class TestErroriDalleRotte:
    """La prova che il gestore è davvero attaccato all'applicazione."""

    @pytest.fixture()
    def client(self, tmp_path: Path):
        from fastapi.testclient import TestClient

        from scriba_core.server import create_app

        app = create_app(db_path=tmp_path / "i.sqlite", token="t", engine_factory=lambda: None)
        with TestClient(app) as c:
            yield c

    def test_in_inglese_il_dettaglio_arriva_in_inglese(self, client) -> None:
        r = client.get("/sessions/9999/voci?token=t", headers={"Accept-Language": "en-GB"})
        assert r.status_code == 404
        assert r.json()["detail"] == "no such call"

    def test_senza_intestazione_resta_l_italiano(self, client) -> None:
        r = client.get("/sessions/9999/voci?token=t")
        assert r.status_code == 404
        assert r.json()["detail"] == "sessione inesistente"


class TestNessunMessaggioDimenticato:
    """Ogni messaggio scritto a mano nel core ha la sua riga inglese.

    Senza questo, un messaggio aggiunto domani esce in italiano dentro
    un'interfaccia inglese e non se ne accorge nessuno: nessun test fallisce,
    niente si rompe, e la frase la legge solo chi ha appena sbagliato qualcosa
    e non ha voglia di indovinare.
    """

    @staticmethod
    def _messaggi() -> list[tuple[str, str]]:
        import ast

        radice = Path(__file__).resolve().parents[1] / "scriba_core"
        fuori: list[tuple[str, str]] = []
        for percorso in radice.rglob("*.py"):
            albero = ast.parse(percorso.read_text(encoding="utf-8"))
            for nodo in ast.walk(albero):
                if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)):
                    continue
                if nodo.func.id not in ("HTTPException", "ErroreSql"):
                    continue
                candidati = [k.value for k in nodo.keywords if k.arg == "detail"] + list(nodo.args)
                for a in candidati:
                    # Le f-string non si confrontano: il testo lo compone il
                    # programma, e la riga inglese la trova `_ERRORI_MOTIVI`.
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) and len(a.value) > 3:
                        fuori.append((percorso.name, a.value))
        return fuori

    def test_ce_ne_sono(self) -> None:
        # Un controllo che non controlla niente dichiara successo per errore.
        assert len(self._messaggi()) > 20

    def test_ognuno_esce_in_inglese(self) -> None:
        dimenticati = [
            f"{file}: {testo}" for file, testo in self._messaggi() if errore(testo, "en") == testo
        ]
        assert not dimenticati, "\n".join(dimenticati)

class TestNoteDelleFasi:
    """Una nota di fase che è una frase deve viaggiare come gettone.

    Le fasi nascono nel thread dell'analisi e vanno sul websocket, dove
    `Accept-Language` non c'è: la lingua ce l'ha solo chi guarda. Una nota
    scritta come frase — «4 di 6 blocchi» — arriverebbe in italiano dentro
    un'interfaccia inglese, ed è successo (#91).

    Restano frasi le note che si leggono uguali in tutte le lingue: «67 s» è
    un numero e un'unità.
    """

    @staticmethod
    def _avvisi() -> list[tuple[int, bool, bool]]:
        """(riga, ha una nota, ha una nota_chiave) per ogni `_avvisa`."""
        import ast

        sorgente = (Path(__file__).resolve().parents[1] / "scriba_core/ai/analyze.py").read_text(
            encoding="utf-8"
        )
        fuori = []
        for nodo in ast.walk(ast.parse(sorgente)):
            if not isinstance(nodo, ast.Call):
                continue
            f = nodo.func
            if not (isinstance(f, ast.Attribute) and f.attr == "_avvisa"):
                continue
            # `_avvisa(chiave, stato, nota)`: la nota è il terzo posizionale.
            nota = nodo.args[2] if len(nodo.args) > 2 else None
            # «67 s» è un numero e un'unità: si legge uguale in tutte le
            # lingue. Si guarda l'ultimo pezzo costante della f-string, non il
            # sorgente: `ast.unparse` sceglie da sé che apici usare.
            coda = ""
            if isinstance(nota, ast.JoinedStr) and nota.values:
                ultimo = nota.values[-1]
                coda = ultimo.value if isinstance(ultimo, ast.Constant) else ""
            neutra = coda.strip() == "s"
            ha_nota = nota is not None and not (
                isinstance(nota, ast.Constant) and nota.value is None
            )
            chiave = any(k.arg == "nota_chiave" for k in nodo.keywords)
            fuori.append((nodo.lineno, ha_nota and not neutra, chiave))
        return fuori

    def test_ce_ne_sono(self) -> None:
        assert len(self._avvisi()) >= 6

    def test_ogni_frase_ha_il_suo_gettone(self) -> None:
        senza = [riga for riga, frase, chiave in self._avvisi() if frase and not chiave]
        assert not senza, f"_avvisa con una frase e senza nota_chiave, righe: {senza}"
