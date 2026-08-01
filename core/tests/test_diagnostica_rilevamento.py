"""Test della diagnostica del rilevamento.

Non verifica *se* una riunione viene riconosciuta — quello lo fa
`test_detect_call.py` — ma se il rilevamento sa **dire perché** non l'ha
riconosciuta.

Il motivo per cui esiste: «non mi ha proposto di registrare» ha almeno cinque
cause possibili e dall'esterno sono indistinguibili. Ogni test qui sotto prende
una di quelle cause, la mette in scena, e pretende che la diagnostica la nomini.
Se domani il rilevamento cambia idea su un caso, questi test dicono quale.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.detect.call import RilevatoreCall  # noqa: E402


@pytest.fixture()
def rilevatore() -> RilevatoreCall:
    return RilevatoreCall(lambda _c: None, conferma_s=5.0)


def lettura(*voci: dict, riproducono: tuple[int, ...] = ()) -> dict:
    return {"microfono": list(voci), "riproducono": list(riproducono)}


def voce(pid: int, nome: str, picco: float = 0.01) -> dict:
    return {"pid": pid, "nome": nome, "picco": picco}


def riga(r: RilevatoreCall, pid: int) -> dict:
    trovate = [x for x in r.ultima_diagnosi if x["pid"] == pid]
    assert trovate, f"nessuna riga per il pid {pid}"
    return trovate[0]


def test_all_inizio_non_ha_visto_niente(rilevatore: RilevatoreCall) -> None:
    assert rilevatore.diagnostica()["processi"] == []


def test_un_processo_escluso_dice_di_esserlo(rilevatore: RilevatoreCall) -> None:
    rilevatore._giro(lettura(voce(10, "scriba.exe")))
    assert riga(rilevatore, 10)["esito"] == "escluso"
    assert "ignorare" in riga(rilevatore, 10)["perche"]


def test_microfono_senza_segnale(rilevatore: RilevatoreCall) -> None:
    """Il caso più insidioso: la sessione c'è, ma è vecchia."""
    rilevatore._giro(lettura(voce(11, "chrome.exe", picco=0.0), riproducono=(11,)))
    r = riga(rilevatore, 11)
    assert r["esito"] == "escluso"
    assert "mai dato segnale" in r["perche"]


def test_microfono_ma_nessuno_parla(rilevatore: RilevatoreCall) -> None:
    """Microfono acceso e nessun audio in uscita: dettatura, non riunione."""
    rilevatore._giro(lettura(voce(12, "chrome.exe")))
    r = riga(rilevatore, 12)
    assert r["esito"] == "in attesa"
    assert "riprodurre audio" in r["perche"]
    assert r["riproduce"] is False


def test_in_conferma_dice_quanto_manca(rilevatore: RilevatoreCall) -> None:
    rilevatore._giro(lettura(voce(13, "zoom.exe"), riproducono=(13,)))
    r = riga(rilevatore, 13)
    assert r["esito"] == "in conferma"
    # Il primo giro non consuma attesa: manca ancora tutta.
    assert r["mancano_s"] == pytest.approx(5.0, abs=0.2)


def test_quando_diventa_riunione_lo_dice(rilevatore: RilevatoreCall) -> None:
    rilevatore.conferma_s = 0.0
    rilevatore._giro(lettura(voce(14, "zoom.exe"), riproducono=(14,)))
    assert riga(rilevatore, 14)["esito"] == "riunione"


def test_dopo_la_proposta_non_ripete(rilevatore: RilevatoreCall) -> None:
    rilevatore.conferma_s = 0.0
    rilevatore._giro(lettura(voce(15, "zoom.exe"), riproducono=(15,)))
    rilevatore._giro(lettura(voce(15, "zoom.exe"), riproducono=(15,)))
    assert riga(rilevatore, 15)["esito"] == "già proposta"


def test_il_picco_si_riporta_come_lo_riferisce_la_sonda(rilevatore: RilevatoreCall) -> None:
    """È il numero su cui si decide: va mostrato, non riassunto in un sì/no."""
    rilevatore._giro(lettura(voce(16, "teams.exe", picco=0.037)))
    assert riga(rilevatore, 16)["picco"] == pytest.approx(0.037)


def test_la_diagnostica_dice_chi_riproduce(rilevatore: RilevatoreCall) -> None:
    """Serve a capire un 'riproduce un figlio': l'audio esce da un altro pid."""
    rilevatore._giro(lettura(voce(17, "chrome.exe"), riproducono=(999,)))
    assert rilevatore.diagnostica()["riproducono"] == [999]


def test_l_audio_da_un_figlio_e_segnalato(
    rilevatore: RilevatoreCall, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Il caso di Meet nel browser: microfono a un processo, audio a un altro.

    È anche il caso che dipende da `psutil`: senza, questa strada non si
    percorre e una riunione nel browser non viene mai riconosciuta.
    """
    monkeypatch.setattr(
        RilevatoreCall, "_figlio_riproduce", staticmethod(lambda pid, riproducono: True)
    )
    rilevatore.conferma_s = 0.0
    rilevatore._giro(lettura(voce(18, "chrome.exe"), riproducono=(4242,)))
    r = riga(rilevatore, 18)
    assert r["riproduce"] is False
    assert r["riproduce_un_figlio"] is True
    assert r["esito"] == "riunione"


def test_la_diagnosi_e_quella_dell_ultimo_giro(rilevatore: RilevatoreCall) -> None:
    """Non si accumula: quello che conta è cosa si vede adesso."""
    rilevatore._giro(lettura(voce(19, "zoom.exe")))
    rilevatore._giro(lettura(voce(20, "teams.exe")))
    assert [r["pid"] for r in rilevatore.ultima_diagnosi] == [20]


def test_dice_da_quanto_non_arriva_una_lettura(rilevatore: RilevatoreCall) -> None:
    """Una sonda morta e una stanza silenziosa danno lo stesso elenco vuoto."""
    assert rilevatore.diagnostica()["sonda"]["ultima_lettura_fa_s"] is None
    rilevatore._giro(lettura(voce(21, "zoom.exe")))
    eta = rilevatore.diagnostica()["sonda"]["ultima_lettura_fa_s"]
    assert eta is not None and eta < 1.0


def test_dice_se_ha_rinunciato(rilevatore: RilevatoreCall) -> None:
    """Dopo troppe ripartenze il rilevamento si spegne, e finora in silenzio."""
    assert rilevatore.diagnostica()["sonda"]["rinunciato"] is False
    rilevatore._cadute = RilevatoreCall.CADUTE_CONSECUTIVE_MAX
    assert rilevatore.diagnostica()["sonda"]["rinunciato"] is True


def test_le_ripartenze_totali_non_si_azzerano(rilevatore: RilevatoreCall) -> None:
    """`_cadute` conta quelle ravvicinate e si azzera; per capire com'è andata
    la giornata serve il totale."""
    assert rilevatore.diagnostica()["sonda"]["ripartenze"] == 0
