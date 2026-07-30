"""Test di quello che tiene al sicuro i dati di una call.

Scritti dopo un guasto vero: il database si era fermato allo stato di due giorni
prima, una giornata di lavoro era rimasta dentro un file `-wal` da 4 MB che
nessuno consolidava, e quel WAL è finito disallineato dal database. Della call di
due ore si è salvato solo l'export Markdown fatto a mano.

Ogni test qui sotto verifica una delle tre cose che dovevano esserci:

1. quando una call finisce, quello che ha scritto sta **nel database**, non solo
   nel WAL — cioè sopravvive a un core ucciso male;
2. un database illeggibile viene messo da parte, non usato;
3. un backup c'è, ed è quello giusto.
"""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriba_core.db import manutenzione  # noqa: E402
from scriba_core.db.store import Store  # noqa: E402


def _con_una_call(store: Store) -> int:
    sid = store.create_session(1_785_000_000_000, titolo="Call con Andrea")
    store.add_segment(sid, "loopback", 0, 4_000, "prima frase", is_final=True)
    store.add_segment(sid, "mic", 4_000, 8_000, "seconda frase", is_final=True)
    store.end_session(sid, 1_785_000_008_000)
    return sid


def _solo_file_principale(store: Store, dove: Path) -> sqlite3.Connection:
    """Apre una copia del **solo** `.sqlite`, senza WAL.

    È il modo di rispondere alla domanda che conta: se il WAL sparisse adesso,
    questi dati ci sarebbero ancora? Copiare anche il `-wal` renderebbe il test
    incapace di distinguere i due casi, che è esattamente l'errore che ha
    lasciato passare il guasto.
    """
    copia = dove / "solo-principale.sqlite"
    shutil.copyfile(store.path, copia)
    return sqlite3.connect(copia)


class TestConsolidamento:
    def test_senza_consolidare_i_dati_stanno_solo_nel_wal(self, tmp_path: Path) -> None:
        store = Store(tmp_path / "p.sqlite")
        _con_una_call(store)

        wal = Path(store.path).with_name("p.sqlite-wal")
        assert wal.exists() and wal.stat().st_size > 0

        # Senza il WAL non c'è la call, e nemmeno lo schema: appena creato, un
        # database in modalità WAL è un file vuoto con tutto il resto di fianco.
        solo = _solo_file_principale(store, tmp_path)
        with pytest.raises(sqlite3.OperationalError, match="transcript_segments"):
            solo.execute("SELECT COUNT(*) FROM transcript_segments")

    def test_dopo_consolida_i_dati_sono_nel_database(self, tmp_path: Path) -> None:
        store = Store(tmp_path / "p.sqlite")
        _con_una_call(store)

        assert store.consolida() is True

        # La domanda vera: se il WAL sparisse adesso, la call ci sarebbe ancora?
        solo = _solo_file_principale(store, tmp_path)
        assert solo.execute("SELECT COUNT(*) FROM transcript_segments").fetchone()[0] == 2
        assert solo.execute("SELECT titolo FROM sessions").fetchone()[0] == "Call con Andrea"

    def test_consolidare_azzera_il_wal(self, tmp_path: Path) -> None:
        store = Store(tmp_path / "p.sqlite")
        _con_una_call(store)
        store.consolida()

        wal = Path(store.path).with_name("p.sqlite-wal")
        # TRUNCATE, non PASSIVE: il file resta ma vuoto. Un WAL che cresce senza
        # mai svuotarsi è il sintomo che si era visto (4 MB per 24 ore).
        assert not wal.exists() or wal.stat().st_size == 0

    def test_si_puo_continuare_a_scrivere_dopo(self, tmp_path: Path) -> None:
        store = Store(tmp_path / "p.sqlite")
        sid = _con_una_call(store)
        store.consolida()

        store.add_segment(sid, "mic", 8_000, 9_000, "dopo il consolidamento", is_final=True)
        assert store.conn.execute("SELECT COUNT(*) FROM transcript_segments").fetchone()[0] == 3


class TestControlloAllAvvio:
    def test_un_database_sano_non_viene_toccato(self, tmp_path: Path) -> None:
        store = Store(tmp_path / "p.sqlite")
        _con_una_call(store)
        store.consolida()
        store.close()

        assert manutenzione.controlla(tmp_path / "p.sqlite") is None
        assert not list(tmp_path.glob("danneggiato-*"))

    def test_un_database_illeggibile_viene_messo_da_parte(self, tmp_path: Path) -> None:
        percorso = tmp_path / "p.sqlite"
        store = Store(percorso)
        _con_una_call(store)
        store.consolida()
        store.close()

        # Si rovina il contenuto lasciando intatta l'intestazione: è la forma in
        # cui il guasto si è presentato davvero — il file si apre, e le pagine
        # dentro non tornano.
        dati = bytearray(percorso.read_bytes())
        for posizione in range(4096, min(len(dati), 20_480)):
            dati[posizione] = 0x5A
        percorso.write_bytes(bytes(dati))

        esito = manutenzione.controlla(percorso)
        assert esito is not None
        quarantena = Path(esito["quarantena"])
        assert (quarantena / "p.sqlite").exists()

    def test_col_backup_si_riparte_da_quello(self, tmp_path: Path) -> None:
        percorso = tmp_path / "p.sqlite"
        store = Store(percorso)
        _con_una_call(store)
        store.consolida()
        assert manutenzione.backup(store) is not None
        store.close()

        dati = bytearray(percorso.read_bytes())
        for posizione in range(4096, min(len(dati), 20_480)):
            dati[posizione] = 0x5A
        percorso.write_bytes(bytes(dati))

        esito = manutenzione.controlla(percorso)
        assert esito and esito["ripristinato"]

        # E il ripristino serve solo se la call è ancora là dentro.
        conn = sqlite3.connect(percorso)
        assert conn.execute("SELECT COUNT(*) FROM transcript_segments").fetchone()[0] == 2
        assert [r[0] for r in conn.execute("PRAGMA quick_check")] == ["ok"]

    def test_senza_backup_non_si_perde_il_file_rotto(self, tmp_path: Path) -> None:
        percorso = tmp_path / "p.sqlite"
        store = Store(percorso)
        _con_una_call(store)
        store.consolida()
        store.close()
        dati = bytearray(percorso.read_bytes())
        for posizione in range(4096, min(len(dati), 20_480)):
            dati[posizione] = 0x5A
        percorso.write_bytes(bytes(dati))

        esito = manutenzione.controlla(percorso)
        assert esito and esito["ripristinato"] == ""
        # Nessun backup da cui ripartire non è una scusa per cancellare: quello
        # che resta del file rotto è l'unica speranza di recuperare qualcosa.
        assert (Path(esito["quarantena"]) / "p.sqlite").exists()

    def test_il_wal_segue_il_database_in_quarantena(self, tmp_path: Path) -> None:
        percorso = tmp_path / "p.sqlite"
        store = Store(percorso)
        _con_una_call(store)  # niente consolida: resta un WAL con dei dati
        store.close()

        dati = bytearray(percorso.read_bytes())
        for posizione in range(4096, min(len(dati), 20_480)):
            dati[posizione] = 0x5A
        percorso.write_bytes(bytes(dati))

        esito = manutenzione.controlla(percorso)
        assert esito is not None
        # Un `-wal` lasciato indietro verrebbe riapplicato al database
        # ripristinato, che è di un'altra generazione: è così che nasce un
        # «database disk image is malformed».
        assert not percorso.with_name("p.sqlite-wal").exists()


class TestBackup:
    def test_il_backup_e_leggibile_e_completo(self, tmp_path: Path) -> None:
        store = Store(tmp_path / "p.sqlite")
        _con_una_call(store)

        copia = manutenzione.backup(store)
        assert copia is not None

        conn = sqlite3.connect(copia)
        assert conn.execute("SELECT COUNT(*) FROM transcript_segments").fetchone()[0] == 2
        # VACUUM INTO produce un file solo: un backup non può soffrire dello
        # stesso disallineamento fra database e WAL che ha causato il guasto.
        assert not copia.with_name(copia.name + "-wal").exists()

    def test_ne_restano_gli_ultimi_n(self, tmp_path: Path) -> None:
        store = Store(tmp_path / "p.sqlite")
        _con_una_call(store)

        for _ in range(7):
            manutenzione.backup(store, quanti=3)

        esistenti = manutenzione.backup_esistenti(store.path)
        assert len(esistenti) == 3
        assert manutenzione.ultimo_backup(store.path) == esistenti[-1]

    def test_un_backup_che_non_riesce_non_solleva(self, tmp_path: Path) -> None:
        class ConnessioneRotta:
            def execute(self, *_a, **_k):
                raise sqlite3.OperationalError("disco pieno")

        class StoreFinto:
            path = tmp_path / "p.sqlite"
            conn = ConnessioneRotta()

        # Fermare una registrazione perché non si è potuto fare un backup
        # sarebbe un danno peggiore di non averlo.
        assert manutenzione.backup(StoreFinto()) is None


@pytest.mark.parametrize("mancante", ["p.sqlite", "altro.sqlite"])
def test_un_database_che_non_esiste_ancora_va_bene(tmp_path: Path, mancante: str) -> None:
    assert manutenzione.controlla(tmp_path / mancante) is None


class TestConsolidamentoPeriodico:
    """Una call dura un'ora: aspettare la fine per mettere al sicuro il lavoro
    lascia scoperta tutta la registrazione.

    Non è prudenza teorica. Provato: quando l'applicazione Electron muore di
    colpo, il sistema operativo porta con sé anche il core — il Job Object di
    Electron non gli lascia il tempo di consolidare, per quanta grazia gli si
    conceda nel codice. L'unica difesa che regge è aver già travasato.
    """

    @staticmethod
    def _stato(registrando: bool) -> dict:
        class Recorder:
            is_recording = registrando

        return {"recorder": Recorder()}

    @staticmethod
    def _gira_un_poco(stato: dict, store: Store) -> None:
        """Fa girare la guardia per qualche giro e la ferma.

        `asyncio.run` invece di un test asincrono: pytest-asyncio non è fra le
        dipendenze del progetto, e aggiungerla per due test sarebbe sproporzionato.
        """
        import scriba_core.server as srv

        async def gira() -> None:
            compito = asyncio.create_task(srv._consolida_mentre_registra(stato, store))
            await asyncio.sleep(0.25)
            compito.cancel()

        asyncio.run(gira())

    def test_mentre_registra_consolida(self, tmp_path: Path, monkeypatch) -> None:
        import scriba_core.server as srv

        store = Store(tmp_path / "p.sqlite")
        _con_una_call(store)
        monkeypatch.setattr(srv, "INTERVALLO_CONSOLIDAMENTO_S", 0.05)

        self._gira_un_poco(self._stato(True), store)

        solo = _solo_file_principale(store, tmp_path)
        assert solo.execute("SELECT COUNT(*) FROM transcript_segments").fetchone()[0] == 2

    def test_fuori_da_una_registrazione_non_tocca_niente(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import scriba_core.server as srv

        store = Store(tmp_path / "p.sqlite")
        _con_una_call(store)
        monkeypatch.setattr(srv, "INTERVALLO_CONSOLIDAMENTO_S", 0.05)

        self._gira_un_poco(self._stato(False), store)

        # Niente di nuovo da mettere al sicuro: un checkpoint a vuoto ogni due
        # minuti sarebbe solo rumore su disco.
        with pytest.raises(sqlite3.OperationalError):
            _solo_file_principale(store, tmp_path).execute(
                "SELECT COUNT(*) FROM transcript_segments"
            )
