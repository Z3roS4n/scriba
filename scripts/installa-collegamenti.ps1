<#
    Crea i collegamenti per aprire Scriba come una normale applicazione.

    Non e' un installatore vero, ma toglie di mezzo il terminale, che e' quello
    che serve per usarla tutti i giorni.

    Il collegamento punta direttamente a electron.exe con la cartella dell'app
    come argomento: cosi' non compare nessuna finestra di console, cosa che
    invece succede passando da un file .cmd.

    Questo file resta volutamente in ASCII puro: PowerShell 5.1 legge gli script
    senza BOM come ANSI, e un accento o un trattino lungo bastano a rompere il
    parser con un errore che non c'entra niente con la riga segnalata.

    Uso:
        powershell -ExecutionPolicy Bypass -File scripts\installa-collegamenti.ps1
        powershell -ExecutionPolicy Bypass -File scripts\installa-collegamenti.ps1 --avvio-automatico
#>

$ErrorActionPreference = 'Stop'

$radice = Split-Path -Parent $PSScriptRoot
$ui = Join-Path $radice 'ui'
$electron = Join-Path $ui 'node_modules\electron\dist\electron.exe'
$icona = Join-Path $radice 'assets\scriba.ico'

Write-Host "Scriba - installazione dei collegamenti" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $electron)) {
    Write-Host "[X] Electron non trovato." -ForegroundColor Red
    Write-Host "    Mancano le dipendenze. Esegui:  cd `"$ui`"; npm install"
    exit 1
}

$bundle = Join-Path $ui 'dist\renderer\bundle.js'
if (-not (Test-Path $bundle)) {
    Write-Host "[!] Applicazione non ancora compilata. La compilo adesso..." -ForegroundColor Yellow
    Push-Location $ui
    try { npm run build | Out-Null } finally { Pop-Location }
    Write-Host "    fatto." -ForegroundColor Green
}

$venv = Join-Path $radice 'core\.venv\Scripts\python.exe'
if (-not (Test-Path $venv)) {
    Write-Host "[!] Ambiente Python assente: l'app si aprira' ma non registrera'." -ForegroundColor Yellow
    Write-Host "    Crealo con:  uv venv core\.venv --python 3.12"
    Write-Host ""
}

function New-Collegamento {
    param([string]$Percorso, [string]$Descrizione)

    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($Percorso)
    $lnk.TargetPath = $electron
    # Il punto e' la cartella dell'app: Electron la interpreta come progetto da
    # avviare, ed e' anche la directory di lavoro.
    $lnk.Arguments = '.'
    $lnk.WorkingDirectory = $ui
    $lnk.Description = $Descrizione
    if (Test-Path $icona) { $lnk.IconLocation = $icona }
    $lnk.Save()
}

$descrizione = 'Registra e trascrive le call'

$desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Scriba.lnk'
New-Collegamento -Percorso $desktop -Descrizione $descrizione
Write-Host "[OK] Desktop" -ForegroundColor Green

$menu = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs\Scriba.lnk'
New-Item -ItemType Directory -Force -Path (Split-Path $menu) | Out-Null
New-Collegamento -Percorso $menu -Descrizione $descrizione
Write-Host "[OK] Menu Start (cercala scrivendo 'Scriba')" -ForegroundColor Green

$avvio = Join-Path ([Environment]::GetFolderPath('Startup')) 'Scriba.lnk'
if ($args -contains '--avvio-automatico') {
    New-Collegamento -Percorso $avvio -Descrizione $descrizione
    Write-Host "[OK] Avvio automatico all'accesso" -ForegroundColor Green
} elseif (Test-Path $avvio) {
    Remove-Item $avvio -Force
    Write-Host "[--] Avvio automatico rimosso" -ForegroundColor DarkGray
} else {
    Write-Host "[--] Avvio automatico non attivo (--avvio-automatico per attivarlo)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Fatto. Apri Scriba dal desktop o dal menu Start." -ForegroundColor Cyan
Write-Host "Durante una call, Alt+R mostra e nasconde la trascrizione sovrapposta."
