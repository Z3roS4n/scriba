# Pubblica una release su GitHub per la versione che sta in ui/package.json.
#
#   powershell -ExecutionPolicy Bypass -File scripts/rilascia.ps1 -Note note.md
#   powershell -ExecutionPolicy Bypass -File scripts/rilascia.ps1 -Note note.md -ConInstaller
#
# Il numero **non** lo alza questo script: lo alza la PR che contiene il fix
# (`scripts/versione.ps1`), perche' su `main` non si committa mai. Qui si
# controlla che sia stato alzato davvero, si mette il tag e si pubblica.
#
# Le note vanno divise in tre sezioni, ed e' la divisione a decidere lo scatto:
#
#   ## Cambiamenti che rompono   -> maggiore   cambia il modo di usarla, o i dati
#                                              vanno migrati
#   ## Funzioni nuove            -> minore     qualcosa che prima non si poteva fare,
#                                              o un comportamento visibilmente diverso
#   ## Correzioni                -> patch      un difetto in meno, niente di nuovo
#                                              da imparare
#
# Una sezione senza voci si lascia fuori. Lo scatto atteso e' quello della
# sezione piu' alta presente: se non corrisponde a quanto e' stato alzato in
# package.json lo script lo dice e si ferma, perche' un numero che non riflette
# cosa c'e' dentro e' peggio di nessun numero.

param(
    [Parameter(Mandatory = $true)]
    [string]$Note,
    # L'installer pesa ~170 MB e non e' firmato: allegarlo a una release
    # pubblica e' una decisione, non un dettaglio, e si chiede a parte.
    [switch]$ConInstaller,
    # Salta i controlli sullo stato del repository. Per riprovare una
    # pubblicazione fallita a meta', non per pubblicare da un albero sporco.
    [switch]$Forza
)

$ErrorActionPreference = 'Stop'
$radice = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $Note)) { throw "File delle note non trovato: $Note" }

# ------------------------------------------------------------- il repository

if (-not $Forza) {
    $ramo = (git -C $radice rev-parse --abbrev-ref HEAD).Trim()
    if ($ramo -ne 'main') { throw "Si pubblica da main, non da '$ramo'." }
    if (git -C $radice status --porcelain) {
        throw "L'albero ha modifiche non salvate: la release punterebbe a un commit che non le contiene."
    }
    git -C $radice fetch --quiet origin
    $avanti = (git -C $radice rev-list --count 'origin/main..HEAD').Trim()
    $indietro = (git -C $radice rev-list --count 'HEAD..origin/main').Trim()
    if ($avanti -ne '0' -or $indietro -ne '0') {
        throw "main locale e origin/main non coincidono ($avanti avanti, $indietro indietro)."
    }
}

# ------------------------------------------------------------- la versione

$pacchetto = Join-Path $radice 'ui\package.json'
$versione = (Get-Content $pacchetto -Raw -Encoding UTF8 | ConvertFrom-Json).version
$tag = "v$versione"

if ((git -C $radice tag --list $tag)) {
    throw "Il tag $tag esiste gia'. La versione va alzata nella PR del fix (scripts/versione.ps1)."
}

# ------------------------------------------------------- lo scatto dichiarato

$testo = Get-Content $Note -Raw -Encoding UTF8
function Ha-Sezione([string]$titolo) {
    # La sezione conta solo se ha delle voci sotto: un'intestazione vuota
    # dichiarerebbe uno scatto che nessuno ha fatto.
    #
    # Il pattern si compone da stringhe con apici singoli: fra doppi apici
    # PowerShell leggerebbe `$(` come l'inizio di una sottoespressione e
    # proverebbe a eseguire `.*?` come se fosse un comando.
    $pattern = '(?ms)^##\s+' + [regex]::Escape($titolo) + '\s*$(.*?)(?=^##\s|\z)'
    $m = [regex]::Match($testo, $pattern)
    return $m.Success -and ($m.Groups[1].Value.Trim().Length -gt 0)
}

$atteso = $null
if (Ha-Sezione 'Cambiamenti che rompono') { $atteso = 'maggiore' }
elseif (Ha-Sezione 'Funzioni nuove') { $atteso = 'minore' }
elseif (Ha-Sezione 'Correzioni') { $atteso = 'patch' }
if (-not $atteso) {
    throw "Le note non hanno nessuna sezione con voci. Attese: '## Cambiamenti che rompono', '## Funzioni nuove', '## Correzioni'."
}

$precedente = (git -C $radice tag --list 'v*' --sort=-v:refname | Select-Object -First 1)
if ($precedente) {
    $p = $precedente.TrimStart('v').Split('.')
    $n = $versione.Split('.')
    $fatto =
    if ([int]$n[0] -gt [int]$p[0]) { 'maggiore' }
    elseif ([int]$n[1] -gt [int]$p[1]) { 'minore' }
    elseif ([int]$n[2] -gt [int]$p[2]) { 'patch' }
    else { 'nessuno' }

    if ($fatto -ne $atteso) {
        throw "Le note dichiarano uno scatto '$atteso' ma da $precedente a $tag lo scatto e' '$fatto'. Correggi l'uno o le altre."
    }
}

# ----------------------------------------------------------------- pubblica

$commit = (git -C $radice rev-parse --short HEAD).Trim()
Write-Host "rilascio  $tag  ($atteso)  da $commit"

git -C $radice tag -a $tag -m "Scriba $versione"
git -C $radice push --quiet origin $tag

$argomenti = @('release', 'create', $tag, '--title', "Scriba $versione", '--notes-file', (Resolve-Path $Note).Path)
if ($ConInstaller) {
    $installer = Join-Path $radice "ui\release\Scriba Setup $versione.exe"
    if (-not (Test-Path $installer)) {
        throw "Installer non trovato: $installer. Costruiscilo con 'cd ui; npm run dist'."
    }
    $argomenti += $installer
}

& gh @argomenti
if ($LASTEXITCODE -ne 0) {
    # Il tag e' gia' su origin: si dice come riprendere invece di lasciare uno
    # stato a meta' senza spiegazione.
    throw "gh release create non e' riuscito. Il tag $tag e' gia' pubblicato: rilancia con -Forza dopo aver risolto."
}
Write-Host "pubblicata: https://github.com/Z3roS4n/scriba/releases/tag/$tag"
