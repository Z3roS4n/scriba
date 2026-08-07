"""Test del rilevamento delle call.

La logica sta tutta nelle regole anti-falso-positivo: qui si verificano quelle,
con l'enumerazione audio sostituita. Il giro vero contro Windows si prova con
`spikes/prova_rilevamento.py`, che richiede di entrare davvero in una riunione.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.detect import call as rilevamento  # noqa: E402
from scriba_core.detect.call import PIATTAFORME, Call, RilevatoreCall  # noqa: E402


class FintaSonda:
    """Prende il posto del processo che osserva l'audio.

    Emette le letture che il test decide, nello stesso formato in cui le
    produce la sonda vera: una riga JSON per giro.
    """

    def __init__(self, stato: dict) -> None:
        self.stato = stato
        self.stdout = self
        self.stderr = None
        self.ucciso = False

    def poll(self) -> int | None:
        return 0 if self.ucciso else None

    def __iter__(self):
        while not self.ucciso:
            yield json.dumps(
                {
                    "microfono": [
                        {"pid": p, "nome": n, "picco": self.stato.get("picchi", {}).get(p, 0.01)}
                        for p, n in self.stato["microfono"]
                    ],
                    "riproducono": list(self.stato["riproduce"]),
                }
            )
            time.sleep(0.01)

    def kill(self) -> None:
        self.ucciso = True


@pytest.fixture()
def finto_ambiente(monkeypatch):
    """Controlla cosa 'sta usando il microfono' e cosa 'sta riproducendo'."""
    stato = {"microfono": [], "riproduce": set()}
    monkeypatch.setattr(
        RilevatoreCall, "_avvia_sonda", lambda self: FintaSonda(stato)
    )
    monkeypatch.setattr(RilevatoreCall, "_figlio_riproduce", staticmethod(lambda pid, r: False))
    return stato


def attendi(condizione, timeout: float = 3.0) -> bool:
    scadenza = time.time() + timeout
    while time.time() < scadenza:
        if condizione():
            return True
        time.sleep(0.02)
    return False


class TestRegole:
    def test_una_call_viene_segnalata(self, finto_ambiente) -> None:
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.05)
        r.start()
        try:
            assert attendi(lambda: viste)
        finally:
            r.stop()

        assert viste[0].piattaforma == "Zoom"
        assert viste[0].pid == 100

    def test_il_microfono_da_solo_non_basta(self, finto_ambiente) -> None:
        # Dettatura, messaggio vocale, prova audio: il microfono si accende
        # spesso senza che ci sia una riunione.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = set()

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.05)
        r.start()
        try:
            time.sleep(0.3)
        finally:
            r.stop()
        assert viste == []

    def test_una_situazione_lampo_non_conta(self, finto_ambiente) -> None:
        # La schermata di prova audio prima di entrare accende tutto per un
        # attimo: senza attesa si verrebbe interrotti ogni volta.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=30.0)
        r.start()
        try:
            time.sleep(0.2)
        finally:
            r.stop()
        assert viste == []

    def test_si_avvisa_una_volta_sola(self, finto_ambiente) -> None:
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: viste)
            time.sleep(0.3)
        finally:
            r.stop()
        assert len(viste) == 1

    def test_finita_una_call_la_successiva_viene_segnalata(self, finto_ambiente) -> None:
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: len(viste) == 1)
            finto_ambiente["microfono"] = []          # riunione finita
            finto_ambiente["riproduce"] = set()
            time.sleep(0.1)
            finto_ambiente["microfono"] = [(100, "zoom.exe")]  # riunione nuova
            finto_ambiente["riproduce"] = {100}
            assert attendi(lambda: len(viste) == 2)
        finally:
            r.stop()

    def test_dimentica_fa_riproporre(self, finto_ambiente) -> None:
        # Se l'utente ha detto di no e poi cambia idea, deve poter essere
        # richiesto di nuovo senza uscire dalla riunione.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        finto_ambiente["riproduce"] = {100}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: len(viste) == 1)
            r.dimentica(100)
            assert attendi(lambda: len(viste) == 2)
        finally:
            r.stop()

    def test_un_applicazione_sconosciuta_viene_comunque_rilevata(self, finto_ambiente) -> None:
        # Il rilevamento non dipende da un elenco di nomi: quello serve solo a
        # dire all'utente cosa si e' riconosciuto.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(7, "riunioni-del-futuro.exe")]
        finto_ambiente["riproduce"] = {7}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: viste)
        finally:
            r.stop()
        assert viste[0].piattaforma == "riunioni-del-futuro"


class TestSessioniVecchie:
    """Il caso emerso provando su una macchina vera.

    Le sessioni di cattura non si chiudono quando l'applicazione smette di
    registrare: restano lì a tempo indeterminato. Senza distinguere, un
    programma che ha usato il microfono un'ora fa e adesso fa uscire audio
    viene scambiato per una riunione.
    """

    def test_una_sessione_senza_segnale_non_e_una_call(self, finto_ambiente) -> None:
        # Il caso reale: Steam aveva una sessione microfono ferma a zero.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(10384, "steam.exe")]
        finto_ambiente["riproduce"] = {10384}
        finto_ambiente["picchi"] = {10384: 0.0}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.05)
        r.start()
        try:
            time.sleep(0.3)
        finally:
            r.stop()
        assert viste == []

    def test_con_segnale_sul_microfono_e_una_call(self, finto_ambiente) -> None:
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(22356, "msedge.exe")]
        finto_ambiente["riproduce"] = {22356}
        finto_ambiente["picchi"] = {22356: 0.018}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: viste)
        finally:
            r.stop()

    def test_un_istante_di_silenzio_non_annulla_la_call(self, finto_ambiente) -> None:
        # Chi registra puo' avere un momento di silenzio assoluto: una volta
        # visto il segnale, non si torna indietro finche' la sessione resta.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(50, "zoom.exe")]
        finto_ambiente["riproduce"] = {50}
        finto_ambiente["picchi"] = {50: 0.02}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.5)
        r.start()
        try:
            time.sleep(0.15)
            finto_ambiente["picchi"] = {50: 0.0}  # silenzio improvviso
            assert attendi(lambda: viste, timeout=3)
        finally:
            r.stop()

    def test_senza_misuratore_non_si_esclude_nulla(self, finto_ambiente) -> None:
        # Se il livello non e' leggibile, decide il resto della regola: meglio
        # una proposta in piu' che una funzione che non scatta mai.
        viste: list[Call] = []
        finto_ambiente["microfono"] = [(60, "zoom.exe")]
        finto_ambiente["riproduce"] = {60}
        finto_ambiente["picchi"] = {60: -1.0}

        r = RilevatoreCall(viste.append, intervallo_s=0.01, conferma_s=0.02)
        r.start()
        try:
            assert attendi(lambda: viste)
        finally:
            r.stop()


class TestRipartenze:
    """La sonda ogni tanto si ferma da sola.

    La libreria COM sottostante ha un difetto noto: solleva "COM method call
    without VTable" mentre libera un oggetto, e quando capita l'output si chiude
    anche se il processo e' vivo. Non e' una causa che si possa togliere, quindi
    il rilevatore deve conviverci.
    """

    def test_una_sonda_che_si_ferma_viene_riavviata(self, finto_ambiente) -> None:
        avvii = []
        originale = RilevatoreCall._avvia_sonda

        def conta(self):
            avvii.append(1)
            sonda = originale(self)
            # Si ferma da sola dopo poche letture, come capita nella realta'.
            threading.Timer(0.15, sonda.kill).start()
            return sonda

        RilevatoreCall._avvia_sonda = conta
        try:
            r = RilevatoreCall(lambda c: None, intervallo_s=0.01, conferma_s=10)
            r.start()
            try:
                assert attendi(lambda: len(avvii) >= 2, timeout=8)
            finally:
                r.stop()
        finally:
            RilevatoreCall._avvia_sonda = originale

    def test_si_rinuncia_solo_se_non_riesce_a_partire(self, finto_ambiente) -> None:
        # Una ripartenza ogni tanto durante una giornata non deve spegnere la
        # funzione: si rinuncia solo davanti a fallimenti ravvicinati.
        assert RilevatoreCall.CADUTE_CONSECUTIVE_MAX >= 10
        assert RilevatoreCall.RIPRESA_RIUSCITA_S >= 30


class TestChiusura:
    def test_fermarsi_e_immediato(self, finto_ambiente) -> None:
        # Il ciclo e' fermo in lettura sulla sonda, che e' un'attesa bloccante:
        # senza chiuderla per prima, non si accorge dello stop e chiudere
        # l'applicazione costa secondi di attesa a vuoto.
        finto_ambiente["microfono"] = [(100, "zoom.exe")]
        r = RilevatoreCall(lambda c: None, intervallo_s=0.01, conferma_s=10)
        r.start()
        time.sleep(0.1)

        inizio = time.time()
        r.stop()
        assert time.time() - inizio < 1.0


class TestSistemaVero:
    """Contro le API di Windows, non contro il finto ambiente."""

    def test_la_sonda_vera_non_fa_terminare_il_processo(self) -> None:
        # Le API COM interrogate a ripetizione facevano terminare bruscamente il
        # processo, portandosi dietro la registrazione in corso. Ora stanno in
        # un processo a parte: questo test gira il rilevatore vero, senza
        # sostituzioni, e verifica che chi lo ospita sopravviva.
        r = RilevatoreCall(lambda call: None, intervallo_s=0.2, conferma_s=0.2)
        r.start()
        try:
            time.sleep(2.5)
            assert r._thread is not None and r._thread.is_alive()
            assert r._cadute == 0, "la sonda e' caduta"
        finally:
            r.stop()

    def test_la_sonda_produce_letture_valide(self) -> None:
        """La sonda risponde con una lettura utilizzabile.

        Salta dove non c'e' una scheda audio: su un runner di CI le API COM
        rispondono «Element not found», che non e' un difetto della sonda ma
        l'assenza di hardware. Si distingue guardando cosa risponde, non
        indovinando dall'ambiente.
        """
        import subprocess
        from pathlib import Path

        core = Path(rilevamento.__file__).resolve().parents[2]
        p = subprocess.Popen(
            [sys.executable, "-m", "scriba_core.detect.probe", "0.05"],
            cwd=str(core),
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            riga = p.stdout.readline()
            lettura = json.loads(riga)
            if "Element not found" in str(lettura.get("errore", "")):
                pytest.skip("nessun dispositivo audio: niente da leggere")
            assert "microfono" in lettura and "riproducono" in lettura
            assert isinstance(lettura["microfono"], list)
        finally:
            p.kill()


class TestNomi:
    def test_il_browser_si_annuncia_in_modo_comprensibile(self) -> None:
        c = Call(pid=1, processo="chrome.exe", piattaforma="browser", dal_ms=0)
        assert c.nome == "una riunione nel browser"

    def test_le_piattaforme_note_usano_il_proprio_nome(self) -> None:
        c = Call(pid=1, processo="zoom.exe", piattaforma="Zoom", dal_ms=0)
        assert c.nome == "Zoom"

    def test_teams_e_riconosciuto(self) -> None:
        assert PIATTAFORME["ms-teams.exe"] == "Teams"

    def test_scriba_non_rileva_se_stesso(self) -> None:
        assert "python.exe" in rilevamento.IGNORATE
