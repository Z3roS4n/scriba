<#
    Costruisce l'eseguibile pacchettizzato del core (PyInstaller, onedir).

    Usa lo stesso ambiente virtuale dello sviluppo (core/.venv): PyInstaller
    deve importare per davvero scriba_core e le sue dipendenze per capire cosa
    impacchettare, quindi deve girare con lo stesso interprete che le ha gia'
    installate. Se PyInstaller manca in quell'ambiente lo si installa al volo
    con pip — l'ambiente e' creato con uv e nasce senza pip, va inizializzato
    con ensurepip la prima volta.

    Uso:
        powershell -ExecutionPolicy Bypass -File scripts\build-core.ps1

    Output: dist\core\scriba_core\scriba_core.exe (+ le sue DLL e dati, nella
    stessa cartella). E' quello che electron-builder.yml copia come
    extraResource dentro il pacchetto finale.
#>

$ErrorActionPreference = 'Stop'

$radice = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $radice 'core\.venv\Scripts\python.exe'
$spec = Join-Path $radice 'scripts\pyinstaller\scriba_core.spec'
$distPath = Join-Path $radice 'dist\core'
$workPath = Join-Path $radice 'build\core'

Write-Host "Scriba - build del core (PyInstaller)" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $venvPython)) {
    Write-Host "[X] Ambiente Python assente in core\.venv." -ForegroundColor Red
    Write-Host "    Crealo con:  uv venv core\.venv --python 3.12  seguito dalle dipendenze del core."
    exit 1
}

# Si chiede a Python di rispondere su stdout invece di lasciarlo fallire:
# redirigere lo stderr di un eseguibile nativo (`2>$null`) fa avvolgere ogni
# riga in un ErrorRecord, e con ErrorActionPreference a Stop quella diventa
# un'eccezione terminante. In locale non si vedeva perche' pip c'era gia';
# su un runner pulito la build moriva qui.
$haPip = (& $venvPython -c "import importlib.util as u, sys; sys.stdout.write('si' if u.find_spec('pip') else 'no')")
if ($haPip -ne 'si') {
    Write-Host "[!] pip assente nell'ambiente (normale per un venv creato con uv): lo installo." -ForegroundColor Yellow
    & $venvPython -m ensurepip --upgrade | Out-Null
}

$haPyInstaller = (& $venvPython -c "import importlib.util as u, sys; sys.stdout.write('si' if u.find_spec('PyInstaller') else 'no')")
if ($haPyInstaller -ne 'si') {
    Write-Host "[!] PyInstaller assente: lo installo nell'ambiente del core." -ForegroundColor Yellow
    & $venvPython -m pip install --upgrade pyinstaller
    if ($LASTEXITCODE -ne 0) { Write-Host "[X] Installazione di PyInstaller non riuscita." -ForegroundColor Red; exit 1 }
}

Write-Host "Costruzione in corso (qualche minuto, soprattutto la prima volta)..." -ForegroundColor Cyan
& $venvPython -m PyInstaller $spec --distpath $distPath --workpath $workPath --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] PyInstaller ha fallito. Vedi l'output sopra per l'errore vero." -ForegroundColor Red
    exit 1
}

$eseguibile = Join-Path $distPath 'scriba_core\scriba_core.exe'
if (-not (Test-Path $eseguibile)) {
    Write-Host "[X] Build terminata ma scriba_core.exe non c'e'. Qualcosa non torna nello spec." -ForegroundColor Red
    exit 1
}

$dimensione = (Get-ChildItem -Recurse (Join-Path $distPath 'scriba_core') | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ""
Write-Host ("[OK] Core costruito: {0} ({1:N0} MB)" -f $eseguibile, $dimensione) -ForegroundColor Green
