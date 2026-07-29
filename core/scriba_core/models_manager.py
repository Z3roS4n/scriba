"""Scarica e avvia il modello di analisi locale.

Si spedisce `llama-server` come binario invece di dipendere da Ollama o LM
Studio installati dall'utente: la versione del motore la controlliamo noi, e si
ha accesso diretto alla generazione vincolata da schema, che è ciò che rende
affidabile l'estrazione delle task.

Su questa classe di hardware (Radeon, niente CUDA) il backend è Vulkan, che su
RDNA2 va anche meglio di ROCm — e ROCm su Windows non supporta ufficialmente
queste schede.

I download sono da 5 a 17 GB su connessioni domestiche: durano, si interrompono
e vanno ripresi. Per questo ogni operazione lunga vive in un thread proprio,
con uno stato per-modello che sopravvive al riavvio dell'applicazione perché è
letto dal filesystem, non da una variabile in memoria che si perde riavviando.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

HF_API = "https://huggingface.co/api/models"
GH_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases"

# Build fissata invece di "l'ultima": llama.cpp pubblica piu' release al giorno e
# un aggiornamento silenzioso puo' cambiare il comportamento del modello fra due
# analisi della stessa call.
LLAMA_BUILD = "b10151"


class _Sospeso(Exception):
    """Il download è stato interrotto volontariamente (sospendi), non da un errore.

    Distinguerlo da un'eccezione vera evita di marcare come "errore" un
    modello che l'utente ha semplicemente messo in pausa: il parziale resta
    buono e la ripresa deve ripartire da lì, non da zero.
    """


@dataclass(frozen=True)
class ModelloDisponibile:
    id: str
    repo: str
    # Pinnato al commit, non a "main": altrimenti l'hash atteso richiesto a
    # Hugging Face può cambiare sotto i piedi fra il momento in cui si avvia
    # il download e quello in cui lo si verifica.
    commit: str
    file: str
    etichetta: str
    descrizione: str
    size_bytes: int
    uso: str = "analisi"  # 'trascrizione' | 'analisi'
    # Solo per i test: bypassano rispettivamente la costruzione dell'URL verso
    # Hugging Face e la richiesta dell'hash atteso, cosi' un modello finto puo'
    # puntare a un server locale invece che alla rete.
    url_override: str | None = None
    sha256: str | None = None

    @property
    def url(self) -> str:
        if self.url_override:
            return self.url_override
        return f"https://huggingface.co/{self.repo}/resolve/{self.commit}/{self.file}?download=true"

    @property
    def nota(self) -> str:
        return self.descrizione


CATALOGO: list[ModelloDisponibile] = [
    ModelloDisponibile(
        id="gemma-4-12b",
        # Conversione ufficiale di Google, non una di terze parti. Quella di
        # unsloth (UD-Q4_K_XL) e' stata provata e non funziona: llama.cpp
        # segnala i suoi token di controllo come malformati e il modello, non
        # appena gli si applica un template di chat, produce una sequenza
        # infinita di <unused49>. Il file era integro, l'hash corrispondeva:
        # e' proprio la conversione a essere difettosa.
        # QAT vuol dire quantizzato durante l'addestramento: a parita' di
        # dimensione rende meglio di una quantizzazione fatta dopo.
        repo="google/gemma-4-12B-it-qat-q4_0-gguf",
        commit="29d097773436b69ff9feafd636ab4cf873786537",
        file="gemma-4-12b-it-qat-q4_0.gguf",
        etichetta="Gemma 4 12B",
        descrizione="Predefinito. Conversione ufficiale Google, quantizzazione QAT.",
        size_bytes=6_975_879_296,
    ),
    ModelloDisponibile(
        id="qwen3.5-9b",
        repo="unsloth/Qwen3.5-9B-MTP-GGUF",
        commit="9716a636ee4bddc3fed678220b7a33dd2a4160ae",
        file="Qwen3.5-9B-Q4_0.gguf",
        etichetta="Qwen 3.5 9B",
        descrizione="Più veloce e più leggero. Segue meglio le istruzioni, ma "
        "l'architettura è recente: va verificato che la build lo supporti.",
        size_bytes=5_551_599_968,
    ),
    ModelloDisponibile(
        id="gemma-4-26b-a4b",
        repo="unsloth/gemma-4-26B-A4B-it-GGUF",
        commit="c099eb48e663fd284577b04978a94ffccb261841",
        # Non "...it-Q4_K_M.gguf": nel repo il file sta sotto il prefisso UD
        # (Unsloth Dynamic quant). Il nome senza prefisso non esiste nel repo
        # e il primo download vero avrebbe fallito con un 404.
        file="gemma-4-26B-A4B-it-UD-Q4_K_M.gguf",
        etichetta="Gemma 4 26B (MoE)",
        descrizione="Qualità migliore, molto più lento. Solo 3,8 miliardi di parametri "
        "attivi per token: sta in 10 GB di VRAM tenendo gli esperti in RAM.",
        size_bytes=16_947_541_728,
    ),
]


@dataclass
class Progresso:
    fase: str
    scaricati: int = 0
    totale: int = 0
    messaggio: str = ""

    @property
    def percentuale(self) -> float:
        return (self.scaricati / self.totale * 100) if self.totale else 0.0


@dataclass
class _StatoRuntime:
    """Ciò che solo la memoria sa, per un modello: il resto si legge dal disco.

    `stato` è `None` quando non c'è niente di attivo in questo processo: in
    quel caso `descrivi()` deriva lo stato dai file sul disco, che è come un
    download sospeso torna a essere visibile come `in_pausa` anche dopo che
    l'applicazione è stata chiusa e riaperta.
    """

    stato: str | None = None
    scaricati_bytes: int = 0
    velocita_bps: float | None = None
    secondi_rimanenti: float | None = None
    errore: str | None = None
    thread: threading.Thread | None = None
    annulla: threading.Event = field(default_factory=threading.Event)


# --------------------------------------------------------- vita del processo figlio
#
# Se il core muore — crash compreso, non solo uscita pulita — llama-server non
# deve restare in memoria a tenersi 6-17 GB di RAM senza che nessuno lo possa
# più fermare dall'interfaccia. Un `atexit` non basta: non scatta su un crash.
# Un Job Object di Windows sì, perché è il sistema operativo a chiuderlo
# insieme all'ultimo handle del processo padre, qualunque sia la causa.

_JOB_HANDLES: list[int] = []  # tenuti vivi finché vive il core: chiuderli vanificherebbe la garanzia


def _lega_al_processo_padre(processo: subprocess.Popen) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        JOBOBJECTINFOCLASS_EXTENDED_LIMIT = 9
        PROCESS_TERMINATE = 0x0001
        PROCESS_SET_QUOTA = 0x0100

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                (nome, ctypes.c_uint64)
                for nome in (
                    "ReadOperationCount",
                    "WriteOperationCount",
                    "OtherOperationCount",
                    "ReadTransferCount",
                    "WriteTransferCount",
                    "OtherTransferCount",
                )
            ]

        class _BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimitInformation),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return
        info = _ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(
            job, JOBOBJECTINFOCLASS_EXTENDED_LIMIT, ctypes.byref(info), ctypes.sizeof(info)
        )

        handle_processo = kernel32.OpenProcess(
            PROCESS_TERMINATE | PROCESS_SET_QUOTA, False, processo.pid
        )
        if handle_processo:
            kernel32.AssignProcessToJobObject(job, handle_processo)
        _JOB_HANDLES.append(job)
    except Exception:
        # Meglio rischiare un processo orfano nel caso peggiore che bloccare
        # l'avvio del core per un'API di Windows che si è comportata in modo
        # imprevisto su qualche configurazione.
        log.warning("Non sono riuscito a legare llama-server al ciclo di vita del core.")


def _ram_bytes(pid: int) -> int | None:
    """RAM davvero occupata dal processo, per mostrarla in interfaccia."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        PROCESS_QUERY_INFORMATION = 0x0400
        PROCESS_VM_READ = 0x0010

        class _ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_uint32),
                ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not handle:
            return None
        try:
            contatori = _ProcessMemoryCounters()
            contatori.cb = ctypes.sizeof(_ProcessMemoryCounters)
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(contatori), contatori.cb):
                return int(contatori.WorkingSetSize)
            return None
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


class ModelsManager:
    def __init__(
        self,
        dir_modelli: Path | str,
        *,
        catalogo: list[ModelloDisponibile] | None = None,
        on_evento: Callable[[dict], None] | None = None,
    ) -> None:
        self.dir = Path(dir_modelli)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dir_bin = self.dir / "llama.cpp"
        self.catalogo = catalogo if catalogo is not None else CATALOGO
        # Chiamabile da un thread di download per avvisare l'interfaccia:
        # tipicamente `ctx.publish` del server, ma nei test è un raccoglitore.
        self._on_evento = on_evento
        self._server: subprocess.Popen | None = None
        self._server_model_id: str | None = None
        self._porta: int = 8080
        self._lock = threading.Lock()
        self._runtime: dict[str, _StatoRuntime] = {}

    # ------------------------------------------------------------------ stato

    @property
    def server_exe(self) -> Path:
        return self.dir_bin / "llama-server.exe"

    def percorso(self, modello: ModelloDisponibile) -> Path:
        return self.dir / modello.file

    def installato(self, modello: ModelloDisponibile) -> bool:
        return self.percorso(modello).exists()

    @staticmethod
    def _parziale(percorso: Path) -> Path:
        return percorso.with_suffix(percorso.suffix + ".parziale")

    def _trova(self, model_id: str) -> ModelloDisponibile:
        for modello in self.catalogo:
            if modello.id == model_id:
                return modello
        raise ValueError(f"Modello sconosciuto: {model_id}")

    def descrivi(self, modello: ModelloDisponibile) -> dict:
        """Un `Modello` completo, nella forma esatta di `ui/renderer/tipi.ts`."""
        percorso = self.percorso(modello)
        parziale = self._parziale(percorso)
        rt = self._runtime.get(modello.id)

        installato = percorso.exists()
        parziale_esiste = parziale.exists()
        bytes_parziale = parziale.stat().st_size if parziale_esiste else 0

        endpoint: str | None = None
        ram_bytes: int | None = None

        if rt is not None and rt.stato is not None:
            # Un'operazione è attiva in questo processo: il suo stato vince su
            # quello che si leggerebbe dal disco.
            stato = rt.stato
            scaricati = rt.scaricati_bytes
        elif installato:
            server_vivo = (
                self._server_model_id == modello.id
                and self._server is not None
                and self._server.poll() is None
            )
            if server_vivo:
                stato = "in_uso"
                endpoint = f"http://127.0.0.1:{self._porta}"
                ram_bytes = _ram_bytes(self._server.pid)  # type: ignore[union-attr]
            else:
                if self._server_model_id == modello.id:
                    # Il processo è morto da solo (crash, kill esterno): non
                    # restiamo a dire "in uso" di un server che non c'è più.
                    self._server_model_id = None
                stato = "installato"
            scaricati = modello.size_bytes
        elif parziale_esiste:
            # Nessun thread attivo ma il parziale c'è: o non è mai partito in
            # questa esecuzione, o l'applicazione è stata chiusa e riaperta.
            # In entrambi i casi è "in pausa" con i byte già presi, mai
            # "non installato" — altrimenti un download da 14 GB si perde per
            # una chiusura accidentale. Vale anche a 0 byte (sospeso prima del
            # primo blocco): è comunque un download da riprendere, non uno
            # mai iniziato.
            stato = "in_pausa"
            scaricati = bytes_parziale
        else:
            stato = "non_installato"
            scaricati = 0

        return {
            "id": modello.id,
            "nome": modello.etichetta,
            "uso": modello.uso,
            "size_bytes": modello.size_bytes,
            "stato": stato,
            "scaricati_bytes": scaricati,
            "velocita_bps": rt.velocita_bps if rt else None,
            "secondi_rimanenti": rt.secondi_rimanenti if rt else None,
            "installato_at": int(percorso.stat().st_mtime * 1000) if installato else None,
            "nota": modello.nota,
            "errore": rt.errore if rt else None,
            "endpoint": endpoint,
            "ram_bytes": ram_bytes,
        }

    def elenco_modelli(self) -> list[dict]:
        return [self.descrivi(m) for m in self.catalogo]

    def modello(self, model_id: str) -> dict:
        """`Modello` completo per un id. Solleva `ValueError` se non esiste."""
        return self.descrivi(self._trova(model_id))

    def disco(self) -> dict:
        uso = shutil.disk_usage(self.dir)
        return {"cartella": str(self.dir), "libero_bytes": uso.free, "totale_bytes": uso.total}

    def _pubblica(self, modello: ModelloDisponibile) -> None:
        if self._on_evento is not None:
            self._on_evento({"type": "modello_locale", "modello": self.descrivi(modello)})

    # -------------------------------------------------------------- download

    def _controllo_spazio(self, modello: ModelloDisponibile) -> tuple[bool, float, int]:
        """(basta, GB mancanti, byte già presenti nel parziale)."""
        percorso = self.percorso(modello)
        parziale = self._parziale(percorso)
        gia_presenti = parziale.stat().st_size if parziale.exists() else 0
        mancano_byte = max(0, modello.size_bytes - gia_presenti)
        libero = shutil.disk_usage(self.dir).free
        # Margine del 2%: l'ultimo pezzo di un file da 17 GB non deve fermarsi
        # per differenze fra la dimensione annunciata e quella davvero scritta.
        margine = mancano_byte * 1.02
        basta = libero >= margine
        mancano_gb = max(0.0, (margine - libero) / 1e9)
        return basta, mancano_gb, gia_presenti

    def _scarica(
        self,
        url: str,
        destinazione: Path,
        *,
        sha256: str | None = None,
        on_progress: Callable[[Progresso], None] | None = None,
        fase: str = "download",
        annulla: threading.Event | None = None,
    ) -> Path:
        """Scarica riprendendo da dove si era interrotto e verificando l'integrità.

        Sette gigabyte di download si interrompono: senza ripresa, chi ha una
        connessione instabile non arriva mai in fondo. E un file troncato che
        sembra completo produce errori incomprensibili al primo avvio, quindi si
        controlla l'hash prima di considerarlo buono — calcolato mentre i byte
        arrivano, non rileggendo tutto il file a scaricamento finito.
        """
        parziale = self._parziale(destinazione)
        gia_presenti = parziale.stat().st_size if parziale.exists() else 0
        headers = {"Range": f"bytes={gia_presenti}-"} if gia_presenti else {}

        digest = hashlib.sha256()
        if gia_presenti:
            # Riprendere il digest da dove si era fermato è l'unica rilettura
            # che facciamo: senza, l'hash finale non corrisponderebbe mai. È
            # anche l'occasione in cui uno stato "in verifica" reale può
            # durare secondi veri, non un istante — quindi si pubblica
            # progresso anche qui, non solo durante lo scaricamento.
            with parziale.open("rb") as f:
                letti = 0
                for blocco in iter(lambda: f.read(1024 * 1024), b""):
                    if annulla is not None and annulla.is_set():
                        raise _Sospeso()
                    digest.update(blocco)
                    letti += len(blocco)
                    if on_progress:
                        on_progress(Progresso("verifica", letti, gia_presenti, destinazione.name))

        with httpx.stream(
            "GET", url, headers=headers, follow_redirects=True, timeout=httpx.Timeout(60.0)
        ) as r:
            if r.status_code == 416:  # il server dice che l'abbiamo già tutto
                gia_presenti = parziale.stat().st_size
            else:
                r.raise_for_status()
                if r.status_code == 200 and gia_presenti:
                    # Il server ha ignorato bytes=<n>-: sta mandando tutto da
                    # capo. Continuare a scrivere in coda al parziale
                    # produrrebbe un file corrotto che sembra completo. Meglio
                    # ripartire da zero che consegnare un GGUF rotto.
                    gia_presenti, digest = 0, hashlib.sha256()

                totale = int(r.headers.get("content-length", 0)) + gia_presenti
                with parziale.open("ab" if gia_presenti else "wb") as f:
                    for blocco in r.iter_bytes(1024 * 1024):
                        if annulla is not None and annulla.is_set():
                            raise _Sospeso()
                        f.write(blocco)
                        digest.update(blocco)
                        gia_presenti += len(blocco)
                        if on_progress:
                            on_progress(Progresso(fase, gia_presenti, totale, destinazione.name))

        if on_progress and sha256:
            # Il confronto è istantaneo: il digest è già pronto. Si pubblica
            # comunque un evento "in verifica", altrimenti l'interfaccia
            # resterebbe ferma sull'ultimo "in download" fino al prossimo poll.
            on_progress(Progresso("verifica", gia_presenti, gia_presenti, destinazione.name))

        if sha256 and digest.hexdigest() != sha256:
            parziale.unlink(missing_ok=True)
            raise RuntimeError(
                f"{destinazione.name}: il file scaricato non corrisponde a quello atteso. "
                "Riprova il download."
            )

        parziale.replace(destinazione)
        return destinazione

    @staticmethod
    def _sha_atteso(repo: str, commit: str, file: str) -> str | None:
        """Chiede a Hugging Face l'hash del file, al commit pinnato.

        Per i file grandi l'API restituisce l'oid LFS, che è lo SHA-256 del
        contenuto.
        """
        try:
            r = httpx.get(f"{HF_API}/{repo}/tree/{commit}?expand=1", timeout=30.0)
            r.raise_for_status()
            for voce in r.json():
                if voce.get("path") == file:
                    return (voce.get("lfs") or {}).get("oid")
        except Exception:
            return None
        return None

    def installa_motore(self, on_progress: Callable[[Progresso], None] | None = None) -> Path:
        """Scarica ed estrae llama-server con il backend Vulkan."""
        if self.server_exe.exists():
            return self.server_exe

        nome = f"llama-{LLAMA_BUILD}-bin-win-vulkan-x64.zip"
        url = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/{nome}"
        zip_path = self.dir / nome
        self._scarica(url, zip_path, on_progress=on_progress, fase="motore")

        self.dir_bin.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(self.dir_bin)
        zip_path.unlink(missing_ok=True)

        # Alcune build annidano i binari in una sottocartella.
        if not self.server_exe.exists():
            for trovato in self.dir_bin.rglob("llama-server.exe"):
                for file in trovato.parent.iterdir():
                    shutil.move(str(file), self.dir_bin / file.name)
                break
        if not self.server_exe.exists():
            raise RuntimeError("llama-server.exe non trovato nell'archivio scaricato.")
        return self.server_exe

    def _installa_bloccante(
        self,
        modello: ModelloDisponibile,
        *,
        on_progress: Callable[[Progresso], None] | None = None,
        annulla: threading.Event | None = None,
    ) -> Path:
        percorso = self.percorso(modello)
        if percorso.exists():
            return percorso
        sha = modello.sha256 or self._sha_atteso(modello.repo, modello.commit, modello.file)
        return self._scarica(
            modello.url, percorso, sha256=sha, on_progress=on_progress, annulla=annulla
        )

    def installa_modello(
        self, model_id: str, on_progress: Callable[[Progresso], None] | None = None
    ) -> Path:
        """Scaricamento bloccante, per la riga di comando."""
        modello = self._trova(model_id)
        basta, mancano_gb, _ = self._controllo_spazio(modello)
        if not basta:
            raise RuntimeError(f"Spazio insufficiente: mancano circa {mancano_gb:.1f} GB.")
        return self._installa_bloccante(modello, on_progress=on_progress)

    def avvia_download(self, model_id: str) -> dict:
        """Avvia o riprende il download in un thread. Non blocca chi chiama.

        Il controllo dello spazio è sincrono e veloce apposta: deve poter
        dire "non c'è posto" prima di avviare qualunque thread, non a metà
        scaricamento con il disco già pieno per niente.
        """
        modello = self._trova(model_id)
        if self.percorso(modello).exists():
            return self.descrivi(modello)

        with self._lock:
            rt = self._runtime.setdefault(model_id, _StatoRuntime())
            if rt.thread is not None and rt.thread.is_alive():
                return self.descrivi(modello)  # già in corso, la richiesta è idempotente

            basta, mancano_gb, gia_presenti = self._controllo_spazio(modello)
            if not basta:
                rt.stato = "spazio_insufficiente"
                rt.errore = f"Mancano circa {mancano_gb:.1f} GB liberi."
                rt.scaricati_bytes = gia_presenti
                self._pubblica(modello)
                return self.descrivi(modello)

            rt.stato = "in_download"
            rt.errore = None
            rt.scaricati_bytes = gia_presenti
            rt.velocita_bps = None
            rt.secondi_rimanenti = None
            rt.annulla = threading.Event()
            thread = threading.Thread(
                target=self._esegui_download,
                args=(modello, rt),
                daemon=True,  # non deve tenere in vita il processo da solo
                name=f"scarica-{model_id}",
            )
            rt.thread = thread
            thread.start()
        return self.descrivi(modello)

    def _esegui_download(self, modello: ModelloDisponibile, rt: _StatoRuntime) -> None:
        ultimo_pubblicato = 0.0
        inizio = time.monotonic()
        bytes_a_inizio = rt.scaricati_bytes
        fase_precedente: str | None = None

        def progresso(p: Progresso) -> None:
            nonlocal ultimo_pubblicato, inizio, bytes_a_inizio, fase_precedente
            if p.fase != fase_precedente:
                # La velocità di lettura del parziale (fase "verifica") non è
                # quella di rete: si azzera la media a ogni cambio di fase,
                # altrimenti il primo blocco scaricato dopo una ripresa
                # mostra una velocità falsata dal tempo speso a rileggere.
                inizio = time.monotonic()
                bytes_a_inizio = p.scaricati
                fase_precedente = p.fase

            rt.scaricati_bytes = p.scaricati
            rt.stato = "in_verifica" if p.fase == "verifica" else "in_download"

            trascorso = time.monotonic() - inizio
            if p.fase == "download" and trascorso > 0.2:
                velocita = max(0.0, (p.scaricati - bytes_a_inizio) / trascorso)
                rt.velocita_bps = velocita
                rimanenti = max(0, p.totale - p.scaricati)
                rt.secondi_rimanenti = (rimanenti / velocita) if velocita > 1 else None
            else:
                rt.velocita_bps = None
                rt.secondi_rimanenti = None

            ora = time.monotonic()
            if ora - ultimo_pubblicato >= 1.0:
                # Non più di un evento al secondo: durante un download da 17 GB
                # a un chunk al millisecondo sarebbero decine di migliaia di
                # messaggi inutili sul websocket.
                ultimo_pubblicato = ora
                self._pubblica(modello)

        try:
            self._installa_bloccante(modello, on_progress=progresso, annulla=rt.annulla)
        except _Sospeso:
            rt.stato = None  # torna a essere derivato dal disco: "in_pausa"
        except Exception as exc:
            rt.stato = "errore"
            rt.errore = str(exc)
        else:
            rt.stato = None  # torna a essere derivato dal disco: "installato"
            rt.errore = None
        finally:
            rt.scaricati_bytes = 0
            rt.velocita_bps = None
            rt.secondi_rimanenti = None
            rt.thread = None
            self._pubblica(modello)

    def sospendi_download(self, model_id: str) -> dict:
        """Ferma il thread di download tenendo il parziale: si riprende dopo."""
        modello = self._trova(model_id)
        rt = self._runtime.get(model_id)
        if rt is not None and rt.thread is not None and rt.thread.is_alive():
            rt.annulla.set()
            rt.thread.join(timeout=15.0)
        return self.descrivi(modello)

    def elimina_modello(self, model_id: str) -> dict:
        modello = self._trova(model_id)
        if (
            self._server_model_id == model_id
            and self._server is not None
            and self._server.poll() is None
        ):
            raise RuntimeError(f"{modello.etichetta} è in uso: fermalo prima di eliminarlo.")

        rt = self._runtime.get(model_id)
        if rt is not None and rt.thread is not None and rt.thread.is_alive():
            rt.annulla.set()
            rt.thread.join(timeout=15.0)

        percorso = self.percorso(modello)
        percorso.unlink(missing_ok=True)
        self._parziale(percorso).unlink(missing_ok=True)

        if rt is not None:
            rt.stato = None
            rt.errore = None
            rt.scaricati_bytes = 0
            rt.velocita_bps = None
            rt.secondi_rimanenti = None

        self._pubblica(modello)
        return self.descrivi(modello)

    def attendi_download(self, model_id: str, timeout: float = 30.0) -> None:
        """Blocca finché il download in corso per questo modello non finisce.

        Serve ai test, che non hanno altro modo di sapere quando il thread ha
        finito senza affidarsi a un polling temporizzato.
        """
        rt = self._runtime.get(model_id)
        if rt is not None and rt.thread is not None:
            rt.thread.join(timeout=timeout)

    # ---------------------------------------------------------------- server

    def server_attivo(self, porta: int = 8080) -> bool:
        try:
            return httpx.get(f"http://127.0.0.1:{porta}/health", timeout=2.0).status_code == 200
        except Exception:
            return False

    def avvia_server(self, model_id: str, *, porta: int = 8080, gpu_layers: int = 0) -> dict:
        """Avvia il modello di analisi come sottoprocesso.

        `gpu_layers` è 0 di proposito. Su questa macchina il backend Vulkan
        produce output corrotto — una sequenza infinita di `<unused49>` — anche
        scaricando pochi layer, e il difetto si presenta identico con due
        conversioni GGUF diverse dello stesso modello, quindi non è il file. Il
        driver della scheda risale al 2022 e il supporto Vulkan compute di
        quell'epoca è incompleto per le operazioni che llama.cpp usa.

        Aggiornato il driver, alzare questo valore: fa la differenza fra ~4,5
        token/s su CPU e diverse decine su GPU.
        """
        modello = self._trova(model_id)
        if modello.uso != "analisi":
            raise RuntimeError(f"{modello.etichetta} non è un modello di analisi.")
        if not self.installato(modello):
            raise RuntimeError(f"{modello.etichetta} non è installato.")

        if (
            self._server_model_id == model_id
            and self._server is not None
            and self._server.poll() is None
        ):
            return self.descrivi(modello)  # già acceso, la richiesta è idempotente

        if self._server is not None:
            self.ferma_server()

        if not self.server_exe.exists():
            self.installa_motore()

        comando = [
            str(self.server_exe),
            "-m", str(self.percorso(modello)),
            "--port", str(porta),
            "--host", "127.0.0.1",
            "-c", "32768",          # una call di un'ora sta in ~25k token
            "-ngl", str(gpu_layers),
            # Gemma 4 ragiona prima di rispondere, e il ragionamento finisce in
            # un campo separato. Per riassumere ed estrarre JSON quei token sono
            # solo tempo speso: senza questo, con un tetto basso di max_tokens la
            # risposta torna vuota perché il modello ha pensato e basta.
            "--reasoning-budget", "0",
            "--no-webui",
        ]
        self._server = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(self.dir_bin),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._server_model_id = model_id
        self._porta = porta
        _lega_al_processo_padre(self._server)
        self._pubblica(modello)
        return self.descrivi(modello)

    def ferma_server(self) -> dict | None:
        modello = self._trova(self._server_model_id) if self._server_model_id else None
        if self._server is not None:
            self._server.terminate()
            try:
                self._server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._server.kill()
                with suppress(subprocess.TimeoutExpired):
                    self._server.wait(timeout=5)
            self._server = None
        self._server_model_id = None
        if modello is not None:
            self._pubblica(modello)
            return self.descrivi(modello)
        return None


def _cli() -> int:  # pragma: no cover - utilità da riga di comando
    import argparse

    parser = argparse.ArgumentParser(description="Gestione dei modelli di analisi")
    parser.add_argument("azione", choices=["stato", "installa", "avvia"])
    parser.add_argument("--model", default="gemma-4-12b")
    parser.add_argument("--dir", default=str(Path.home() / ".scriba" / "models"))
    args = parser.parse_args()

    mgr = ModelsManager(args.dir)

    if args.azione == "stato":
        print(json.dumps(mgr.elenco_modelli(), indent=2, ensure_ascii=False))
        return 0

    if args.azione == "installa":
        # Su un terminale la barra si riscrive sulla stessa riga. Quando l'output
        # e' ridiretto o passa da una pipe, il ritorno a capo carrello non serve
        # a nulla e il progresso resta invisibile: li' si stampa una riga ogni
        # tanto, cosi' si vede comunque che sta succedendo qualcosa.
        interattivo = sys.stdout.isatty()
        ultimo = [-1]
        passo = 1 if interattivo else 5

        def mostra(p: Progresso) -> None:
            pct = int(p.percentuale)
            if pct < ultimo[0] + passo and pct != 100:
                return
            ultimo[0] = pct
            gb, tot = p.scaricati / 1e9, p.totale / 1e9
            testo = f"  {p.fase}: {pct:3d}%  {gb:.2f}/{tot:.2f} GB"
            if interattivo:
                print(f"\r{testo}   ", end="", flush=True)
            else:
                print(testo, flush=True)

        def fine_fase() -> None:
            ultimo[0] = -1
            print("\n  installato." if interattivo else "  installato.", flush=True)

        print("Motore llama.cpp (Vulkan)...", flush=True)
        mgr.installa_motore(mostra)
        fine_fase()
        print(f"Modello {args.model}...", flush=True)
        mgr.installa_modello(args.model, mostra)
        fine_fase()
        return 0

    if args.azione == "avvia":
        mgr.avvia_server(args.model)
        print("llama-server avviato su http://127.0.0.1:8080")
        return 0

    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
