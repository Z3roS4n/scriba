# Alza la versione di Scriba, in un posto solo.
#
#   powershell -ExecutionPolicy Bypass -File scripts/versione.ps1 minore
#   powershell -ExecutionPolicy Bypass -File scripts/versione.ps1 0.7.2
#
# La verita' sta in `ui/package.json`, e da li' la leggono electron-builder (nome
# dell'installer, proprieta' del file su Windows, chiave di disinstallazione),
# il processo principale (`app.getVersion()`) e, di rimbalzo, il core.
#
# Non si alza a ogni build. Una build senza modifiche di rilievo condivide il
# numero con la precedente, e a distinguerle ci pensa il commit che
# `npm run build` scrive in `dist/versione.json`. Quando si alza:
#
#   patch    correzioni, niente di nuovo da imparare per chi usa l'app
#   minore   funzioni nuove, o un cambiamento visibile nel comportamento
#   maggiore quando il modo di usarla cambia davvero, o i dati vanno migrati
#
# Il tag serve a poter dire "la versione X" a mesi di distanza: senza, l'unico
# modo di ritrovare quel codice e' la data.

param(
    [Parameter(Mandatory = $true)]
    [string]$Scatto,
    # Il tag si crea solo quando lo si chiede: alzare il numero e rilasciare
    # sono due gesti diversi, e capita di fare il primo senza il secondo.
    [switch]$ConTag
)

$ErrorActionPreference = 'Stop'
$radice = Split-Path -Parent $PSScriptRoot
$pacchetto = Join-Path $radice 'ui\package.json'

$json = Get-Content $pacchetto -Raw -Encoding UTF8 | ConvertFrom-Json
$attuale = $json.version
if ($attuale -notmatch '^(\d+)\.(\d+)\.(\d+)$') {
    throw "Versione attuale non riconosciuta in ui/package.json: '$attuale'"
}
$ma, $mi, $pa = [int]$Matches[1], [int]$Matches[2], [int]$Matches[3]

switch ($Scatto.ToLower()) {
    'maggiore' { $nuova = "$($ma + 1).0.0" }
    'minore' { $nuova = "$ma.$($mi + 1).0" }
    'patch' { $nuova = "$ma.$mi.$($pa + 1)" }
    default {
        if ($Scatto -notmatch '^\d+\.\d+\.\d+$') {
            throw "Scatto sconosciuto: '$Scatto'. Attesi 'maggiore', 'minore', 'patch' o un numero tipo 0.7.2."
        }
        $nuova = $Scatto
    }
}

# Si riscrive il campo dentro il testo invece di riserializzare il JSON:
# ConvertTo-Json riordina le chiavi, cambia il rientro e riscrive gli
# apostrofi delle descrizioni. Il diff deve contenere una riga, non il file.
$testo = Get-Content $pacchetto -Raw -Encoding UTF8
$testo = [regex]::Replace($testo, '("version"\s*:\s*")[^"]+(")', "`${1}$nuova`${2}", 1)
[System.IO.File]::WriteAllText($pacchetto, $testo, (New-Object System.Text.UTF8Encoding($false)))

Write-Host "versione  $attuale -> $nuova"

if ($ConTag) {
    $sporco = git -C $radice status --porcelain
    if ($sporco) {
        Write-Host "  (albero con modifiche non salvate: il tag si crea dopo il commit)"
    }
    git -C $radice tag -a "v$nuova" -m "Scriba $nuova"
    Write-Host "  tag v$nuova creato. Per pubblicarlo: git push origin v$nuova"
}

Write-Host "Ora: cd ui; npm run dist"
