"""Scarica e avvia il modello di analisi locale.

Si spedisce `llama-server` come binario invece di dipendere da Ollama o LM
Studio installati dall'utente: la versione del motore la controlliamo noi, e si
ha accesso diretto alla generazione vincolata da schema, che è ciò che rende
affidabile l'estrazione delle task.

Su questa classe di hardware (Radeon, niente CUDA) il backend è Vulkan, che su
RDNA2 va anche meglio di ROCm — e ROCm su Windows non supporta ufficialmente
queste schede.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx

HF_API = "https://huggingface.co/api/models"
GH_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases"

# Build fissata invece di "l'ultima": llama.cpp pubblica piu' release al giorno e
# un aggiornamento silenzioso puo' cambiare il comportamento del modello fra due
# analisi della stessa call.
LLAMA_BUILD = "b10151"


@dataclass(frozen=True)
class ModelloDisponibile:
    id: str
    repo: str
    file: str
    etichetta: str
    descrizione: str
    gb: float


CATALOGO = [
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
        repo="google/gemma-4-12b-it-qat-q4_0-gguf",
        file="gemma-4-12b-it-qat-q4_0.gguf",
        etichetta="Gemma 4 12B",
        descrizione="Predefinito. Conversione ufficiale Google, quantizzazione QAT.",
        gb=6.5,
    ),
    ModelloDisponibile(
        id="qwen3.5-9b",
        repo="unsloth/Qwen3.5-9B-MTP-GGUF",
        file="Qwen3.5-9B-Q4_0.gguf",
        etichetta="Qwen 3.5 9B",
        descrizione="Più veloce e più leggero. Segue meglio le istruzioni, ma "
        "l'architettura è recente: va verificato che la build lo supporti.",
        gb=5.2,
    ),
    ModelloDisponibile(
        id="gemma-4-26b-a4b",
        repo="unsloth/gemma-4-26B-A4B-it-GGUF",
        file="gemma-4-26B-A4B-it-Q4_K_M.gguf",
        etichetta="Gemma 4 26B (MoE)",
        descrizione="Qualità migliore, molto più lento. Solo 3,8 miliardi di parametri "
        "attivi per token: sta in 10 GB di VRAM tenendo gli esperti in RAM.",
        gb=16.9,
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


class ModelsManager:
    def __init__(self, dir_modelli: Path | str) -> None:
        self.dir = Path(dir_modelli)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dir_bin = self.dir / "llama.cpp"
        self._server: subprocess.Popen | None = None

    # ------------------------------------------------------------------ stato

    @property
    def server_exe(self) -> Path:
        return self.dir_bin / "llama-server.exe"

    def percorso(self, modello: ModelloDisponibile) -> Path:
        return self.dir / modello.file

    def installato(self, modello: ModelloDisponibile) -> bool:
        return self.percorso(modello).exists()

    def stato(self) -> dict:
        return {
            "motore_installato": self.server_exe.exists(),
            "server_attivo": self.server_attivo(),
            "modelli": [
                {
                    "id": m.id,
                    "etichetta": m.etichetta,
                    "descrizione": m.descrizione,
                    "gb": m.gb,
                    "installato": self.installato(m),
                }
                for m in CATALOGO
            ],
        }

    # -------------------------------------------------------------- download

    def _scarica(
        self,
        url: str,
        destinazione: Path,
        *,
        sha256: str | None = None,
        on_progress: Callable[[Progresso], None] | None = None,
        fase: str = "download",
    ) -> Path:
        """Scarica riprendendo da dove si era interrotto e verificando l'integrità.

        Sette gigabyte di download si interrompono: senza ripresa, chi ha una
        connessione instabile non arriva mai in fondo. E un file troncato che
        sembra completo produce errori incomprensibili al primo avvio, quindi si
        controlla l'hash prima di considerarlo buono.
        """
        parziale = destinazione.with_suffix(destinazione.suffix + ".parziale")
        gia_presenti = parziale.stat().st_size if parziale.exists() else 0
        headers = {"Range": f"bytes={gia_presenti}-"} if gia_presenti else {}

        digest = hashlib.sha256()
        if gia_presenti:
            with parziale.open("rb") as f:
                for blocco in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(blocco)

        with httpx.stream(
            "GET", url, headers=headers, follow_redirects=True, timeout=httpx.Timeout(60.0)
        ) as r:
            if r.status_code == 416:  # già completo
                gia_presenti = parziale.stat().st_size
            else:
                r.raise_for_status()
                if r.status_code == 200 and gia_presenti:
                    # Il server ha ignorato la richiesta di ripresa: si ricomincia.
                    gia_presenti, digest = 0, hashlib.sha256()

                totale = int(r.headers.get("content-length", 0)) + gia_presenti
                with parziale.open("ab" if gia_presenti else "wb") as f:
                    for blocco in r.iter_bytes(1024 * 1024):
                        f.write(blocco)
                        digest.update(blocco)
                        gia_presenti += len(blocco)
                        if on_progress:
                            on_progress(Progresso(fase, gia_presenti, totale, destinazione.name))

        if sha256 and digest.hexdigest() != sha256:
            parziale.unlink(missing_ok=True)
            raise RuntimeError(
                f"{destinazione.name}: il file scaricato non corrisponde a quello atteso. "
                "Riprova il download."
            )

        parziale.replace(destinazione)
        return destinazione

    @staticmethod
    def _sha_atteso(repo: str, file: str) -> str | None:
        """Chiede a Hugging Face l'hash del file.

        Per i file grandi l'API restituisce l'oid LFS, che è lo SHA-256 del
        contenuto.
        """
        try:
            r = httpx.get(f"{HF_API}/{repo}/tree/main?expand=1", timeout=30.0)
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

    def installa_modello(
        self, model_id: str, on_progress: Callable[[Progresso], None] | None = None
    ) -> Path:
        modello = next((m for m in CATALOGO if m.id == model_id), None)
        if modello is None:
            raise ValueError(f"Modello sconosciuto: {model_id}")
        if self.installato(modello):
            return self.percorso(modello)

        libero = shutil.disk_usage(self.dir).free / 1e9
        if libero < modello.gb * 1.15:
            raise RuntimeError(
                f"Spazio insufficiente: servono circa {modello.gb:.1f} GB, "
                f"liberi {libero:.1f} GB."
            )

        url = f"https://huggingface.co/{modello.repo}/resolve/main/{modello.file}?download=true"
        return self._scarica(
            url,
            self.percorso(modello),
            sha256=self._sha_atteso(modello.repo, modello.file),
            on_progress=on_progress,
            fase="modello",
        )

    # ---------------------------------------------------------------- server

    def server_attivo(self, porta: int = 8080) -> bool:
        try:
            return httpx.get(f"http://127.0.0.1:{porta}/health", timeout=2.0).status_code == 200
        except Exception:
            return False

    def avvia_server(
        self, model_id: str, porta: int = 8080, *, gpu_layers: int = 0
    ) -> subprocess.Popen:
        """Avvia il modello di analisi.

        `gpu_layers` è 0 di proposito. Su questa macchina il backend Vulkan
        produce output corrotto — una sequenza infinita di `<unused49>` — anche
        scaricando pochi layer, e il difetto si presenta identico con due
        conversioni GGUF diverse dello stesso modello, quindi non è il file. Il
        driver della scheda risale al 2022 e il supporto Vulkan compute di
        quell'epoca è incompleto per le operazioni che llama.cpp usa.

        Aggiornato il driver, alzare questo valore: fa la differenza fra ~4,5
        token/s su CPU e diverse decine su GPU.
        """
        modello = next((m for m in CATALOGO if m.id == model_id), None)
        if modello is None or not self.installato(modello):
            raise RuntimeError(f"Modello {model_id} non installato.")
        if not self.server_exe.exists():
            raise RuntimeError("Motore non installato.")

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
        return self._server

    def ferma_server(self) -> None:
        if self._server is not None:
            self._server.terminate()
            try:
                self._server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._server.kill()
            self._server = None


def _cli() -> int:  # pragma: no cover - utilità da riga di comando
    import argparse

    parser = argparse.ArgumentParser(description="Gestione dei modelli di analisi")
    parser.add_argument("azione", choices=["stato", "installa", "avvia"])
    parser.add_argument("--model", default="gemma-4-12b")
    parser.add_argument("--dir", default=str(Path.home() / ".scriba" / "models"))
    args = parser.parse_args()

    mgr = ModelsManager(args.dir)

    if args.azione == "stato":
        print(json.dumps(mgr.stato(), indent=2, ensure_ascii=False))
        return 0

    if args.azione == "installa":
        import sys

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
