# -*- mode: python ; coding: utf-8 -*-
"""Spec di PyInstaller per il core di Scriba, in modalita' onedir.

Perche' onedir e non onefile: onefile si autoestrae in una cartella temporanea
a ogni avvio, quindi ricopierebbe ogni volta onnxruntime, scipy, i binari
audio — centinaia di MB — pochi secondi persi ogni volta che si apre l'app,
e con l'antivirus di turno che riscansiona tutto. Onedir li mette a posto una
sola volta, all'installazione, ed e' anche il formato che l'installer NSIS
copia piu' facilmente dentro `resources/`.

Uso:
    core/.venv/Scripts/python.exe -m PyInstaller scripts/pyinstaller/scriba_core.spec ^
        --distpath dist/core --workpath build/core --noconfirm

L'output finisce in `dist/core/scriba_core/` (eseguibile + DLL + dati):
quella cartella e' quello che `electron-builder` copia come extraResource.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# SPECPATH e' iniettata da PyInstaller: e' la cartella di questo file.
ROOT = Path(SPECPATH).resolve().parents[1]  # .../scriba
CORE_DIR = ROOT / "core"
ENTRY = Path(SPECPATH) / "entry_point.py"

# Import che l'analisi statica di PyInstaller non troverebbe da sola:
# `_portaudiowpatch` e' il modulo binario che pyaudiowpatch importa senza
# prefisso di pacchetto, e i moduli `uvicorn.*.auto` si risolvono a runtime in
# base al sistema operativo, non con un import diretto nel codice sorgente.
hidden_imports = [
    "_portaudiowpatch",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    # detect/call.py avvia questo modulo con `[sys.executable, "-m",
    # "scriba_core.detect.probe", ...]`: e' un nome di modulo passato come
    # stringa a subprocess.Popen, non un `import` che l'analisi statica di
    # PyInstaller possa trovare da sola. Senza questa riga la sonda di
    # rilevamento chiamate manca dall'eseguibile pacchettizzato.
    "scriba_core.detect.probe",
]

datas = [
    # schema.sql viene letto dal filesystem accanto al modulo (non importato):
    # senza questa riga il primo avvio fallisce creando il database.
    (str(CORE_DIR / "scriba_core" / "db" / "schema.sql"), "scriba_core/db"),
]

binaries = []

# Pacchetti con estensioni native (.pyd/.dll), dati binari propri o import
# dinamici, che vanno raccolti per intero invece di lasciare all'analisi
# statica il compito di scoprirli un file alla volta:
# - onnxruntime: le DLL del motore d'inferenza (onnxruntime.dll e affini);
# - onnx_asr: i modelli ONNX di preelaborazione (fbank, resample) spediti
#   dentro il pacchetto stesso, distinti dai modelli grandi scaricati a runtime;
# - pyaudiowpatch / sounddevice / _sounddevice_data: le DLL di PortAudio, in
#   due copie diverse perche' le due librerie non condividono binario;
# - winsdk: le proiezioni WinRT usate per l'OCR degli screenshot;
# - pycaw / comtypes: enumerazione delle sessioni audio per il rilevamento
#   automatico delle call.
collect_all_packages = [
    "onnxruntime",
    "onnx_asr",
    "pyaudiowpatch",
    "sounddevice",
    "_sounddevice_data",
    "winsdk",
    "pycaw",
    "comtypes",
    "psutil",
    "huggingface_hub",
    "numpy",
    "scipy",
]

def _e_test(percorso_sorgente: str) -> bool:
    """Vero se il file appartiene a una suite di test di scipy/numpy."""
    componenti = Path(percorso_sorgente).parts
    return "tests" in componenti or Path(percorso_sorgente).stem == "conftest"


# Sottopacchetti di onnxruntime che sono strumenti di conversione/benchmark
# per chi addestra modelli (transformers/, quantization/, tools/, training/),
# mai importati da scriba_core: usiamo solo l'inferenza (`onnxruntime.capi`).
# Vanno esclusi perche' `collect_submodules` li importa per scoprirli, e se
# nell'ambiente virtuale e' installato anche PyTorch — capita, e' un venv
# condiviso con altri task che possono aggiungere dipendenze pesanti — quei
# moduli lo trascinano dentro per intero: 300+ MB per codice che non gira mai.
ONNXRUNTIME_SOLO_INFERENZA = ("onnxruntime.transformers", "onnxruntime.quantization",
                               "onnxruntime.tools", "onnxruntime.training")


def _fuori_da_onnxruntime_inferenza(percorso_sorgente: str) -> bool:
    normalizzato = percorso_sorgente.replace("\\", "/")
    return any(f"/{p.split('.', 1)[1].replace('.', '/')}/" in normalizzato for p in ONNXRUNTIME_SOLO_INFERENZA)


for pkg in collect_all_packages:
    d, b, h = collect_all(pkg)
    if pkg in ("scipy", "numpy"):
        # `collect_all` prende il pacchetto per intero, suite di test comprese:
        # su scipy e numpy sono centinaia di file e megabyte che non girano mai
        # in produzione. Un `exclude` su Analysis non basterebbe da solo,
        # perche' agisce sui moduli importati, non su questi dati gia' raccolti
        # come file — si filtra qui, prima di aggiungerli.
        d = [(src, dest) for src, dest in d if not _e_test(src)]
        h = [m for m in h if ".tests." not in m and not m.endswith(".tests") and "conftest" not in m]
    if pkg == "onnxruntime":
        d = [(src, dest) for src, dest in d if not _fuori_da_onnxruntime_inferenza(src)]
        h = [m for m in h if not m.startswith(ONNXRUNTIME_SOLO_INFERENZA)]
    datas += d
    binaries += b
    hidden_imports += h

a = Analysis(
    [str(ENTRY)],
    pathex=[str(CORE_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # I test non servono nel pacchetto: sono l'unica cosa che si tira dietro
    # se non la si esclude esplicitamente, perche' pytest e' installato nello
    # stesso ambiente virtuale usato per costruire l'eseguibile. `collect_all`
    # su scipy/numpy include anche i LORO test interni (centinaia di file):
    # senza escluderli il pacchetto passa da ~90 MB a oltre 300 MB per
    # roba che non gira mai in produzione.
    excludes=[
        "pytest", "pytest_asyncio", "_pytest", "iniconfig", "pluggy",
        "scipy.conftest",
        "numpy.conftest", "numpy.testing",
        # `core/.venv` e' condiviso con altri task che ci installano
        # dipendenze pesanti non legate all'uso normale di scriba_core: la
        # diarizzazione dei partecipanti (`stt/diarizzazione.py`) usa
        # `pyannote.audio`, che si porta dietro l'intero stack PyTorch. E'
        # una funzione facoltativa, esplicitamente progettata per restare
        # assente con grazia: gli import di torch/pyannote in
        # diarizzazione.py sono dentro i metodi (non in cima al file) apposta
        # perche' `Diarizzatore.disponibile()` possa rispondere falso quando
        # mancano, senza rompere il resto dell'applicazione. Un installer da
        # oltre un giga per una funzione che gira a call finita non e' un
        # installer — la stessa ragione per cui i modelli AI stanno fuori.
        # Se in futuro la diarizzazione dovesse entrare per davvero nel
        # pacchetto, questa lista va tolta di proposito, non scoperta perche'
        # il pacchetto e' cresciuto di un giga da un giorno all'altro.
        "torch", "torchaudio", "torchvision", "torchgen", "torchmetrics",
        "torchcodec", "torch_audiomentations", "torch_pitch_shift",
        "pandas", "matplotlib", "pyannote",
        "lightning", "pytorch_lightning", "sklearn", "scikit-learn",
        "sympy", "optuna", "sqlalchemy", "alembic", "opentelemetry",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scriba_core",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Sottosistema console, non "windowed": sidecar.ts legge la prima riga di
    # stdout (porta e token) e inoltra stderr ai log. Il popup del terminale
    # non si vede comunque, perche' sidecar.ts avvia il processo con
    # `windowsHide: true` — la stessa soluzione gia' in uso per llama-server.exe.
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="scriba_core",
)
