# Pubblica una release su GitHub per la versione che sta in ui/package.json.
#
# ATTENZIONE: questo file e' salvato in UTF-8 **con BOM**, e deve restarci.
# PowerShell 5.1 legge un .ps1 senza firma come ANSI: le lettere accentate nelle
# stringhe qui dentro diventerebbero "Ã¨" e finirebbero cosi' nella descrizione
# della release, pubblicate. E' gia' successo una volta.
#
#   powershell -ExecutionPolicy Bypass -File scripts/rilascia.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/rilascia.ps1 -SenzaInstaller
#
# **Il changelog non sta nella descrizione della release**, sta in `CHANGELOG.md`
# e `CHANGELOG.it.md`. Una descrizione e' un pezzo di testo dentro GitHub: non si
# cerca, non si legge in blocco, non entra in un diff, e chi guarda il repository
# non la trova. Il file si', e le due lingue restano una accanto all'altra.
# La descrizione della release si limita a due righe e ai collegamenti.
#
# Il numero **non** lo alza questo script: lo alza la PR che contiene il fix
# (`scripts/versione.ps1`), perche' su `main` non si committa mai. Qui si
# controlla che sia stato alzato davvero, si mette il tag e si pubblica.
#
# La voce del changelog va divisa in tre sezioni, ed e' la divisione a decidere
# lo scatto:
#
#   ### Breaking changes  -> maggiore  cambia il modo di usarla, o i dati vanno
#                                      migrati
#   ### New features      -> minore    qualcosa che prima non si poteva fare, o
#                                      un comportamento visibilmente diverso
#   ### Fixes             -> patch     un difetto in meno, niente di nuovo da
#                                      imparare
#
# Una sezione senza voci si lascia fuori. Lo scatto atteso e' quello della
# sezione piu' alta presente: se non corrisponde a quanto e' stato alzato in
# package.json lo script si ferma, perche' un numero che non riflette cosa c'e'
# dentro e' peggio di nessun numero.

param(
    # L'installer e' allegato di default: una release di un'applicazione senza
    # l'applicazione costringe chi arriva a compilarsela. Resta **non firmato**,
    # e questo va detto nel changelog, non nascosto.
    [switch]$SenzaInstaller,
    # Salta i controlli sullo stato del repository (ramo, albero pulito,
    # allineamento con origin). **Non serve** per riprendere una pubblicazione
    # caduta a meta': quella si riprende rilanciando il comando cosi' com'e', e
    # lo script riusa il tag invece di riposarlo. Serve per i casi in cui si sa
    # cosa si sta facendo e il repository non e' nello stato canonico.
    [switch]$Forza
)

$ErrorActionPreference = 'Stop'
$radice = Split-Path -Parent $PSScriptRoot
$changelog = Join-Path $radice 'CHANGELOG.md'
$changelogIt = Join-Path $radice 'CHANGELOG.it.md'

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

# Il tag si decide **qui e una volta sola**, presto: chi ha sbagliato versione
# lo scopre prima di aspettare changelog, controlli e installer.
#
# Prima c'erano due controlli sulla stessa domanda, questo e uno novanta righe
# piu' sotto, e il primo non faceva passare il secondo: la ripresa aggiunta con
# #68 non era raggiungibile, perche' nel caso che doveva risolvere il tag c'e'
# sempre — la pubblicazione era caduta **dopo** averlo spinto (#76). Due
# controlli che possono rispondere in modo diverso sono il difetto: se serve
# cambiare questa regola, si cambia qui e basta.
#
# Tre esiti, tutti espliciti:
$suDiEsso = (git -C $radice rev-list -n 1 $tag 2>$null)
$riusoIlTag = $false
if ($LASTEXITCODE -eq 0 -and $suDiEsso) {
    $qui = (git -C $radice rev-parse HEAD).Trim()
    if ($suDiEsso.Trim() -ne $qui) {
        # C'e', ma su un altro commit: pubblicare adesso spedirebbe codice
        # diverso da quello che si ha davanti.
        throw @"
Il tag $tag esiste gia' e punta a $($suDiEsso.Substring(0,7)), non a $($qui.Substring(0,7)).
Se la versione non e' stata alzata, alzala nella PR del fix (scripts/versione.ps1).
Se invece il tag e' rimasto indietro: git tag -d $tag; git push origin :refs/tags/$tag
"@
    }
    # C'e' ed e' questo commit: e' una pubblicazione da riprendere, non un
    # errore. Il messaggio si stampa piu' sotto, quando si posa il tag.
    $riusoIlTag = $true
}

# --------------------------------------------------------------- il changelog

function Voce-Changelog([string]$file, [string]$v) {
    <#
        Il testo della voce di questa versione, senza la sua intestazione.
        Il pattern si compone da stringhe con apici singoli: fra doppi apici
        PowerShell leggerebbe `$(` come l'inizio di una sottoespressione e
        proverebbe a eseguire il resto come se fosse un comando.
    #>
    if (-not (Test-Path $file)) { throw "Changelog non trovato: $file" }
    $testo = Get-Content $file -Raw -Encoding UTF8
    $pattern = '(?ms)^##\s+' + [regex]::Escape($v) + '\b.*?$(.*?)(?=^##\s|\z)'
    $m = [regex]::Match($testo, $pattern)
    if (-not $m.Success -or $m.Groups[1].Value.Trim().Length -eq 0) {
        throw "$([System.IO.Path]::GetFileName($file)) non ha una voce per $v. Va scritta nella PR del fix."
    }
    return $m.Groups[1].Value
}

$voce = Voce-Changelog $changelog $versione
# L'italiano non decide niente, ma deve esserci: una release documentata in una
# lingua sola e' una release documentata a meta'.
[void](Voce-Changelog $changelogIt $versione)

function Ha-Sezione([string]$titolo) {
    $pattern = '(?ms)^###\s+' + [regex]::Escape($titolo) + '\s*$(.*?)(?=^###\s|\z)'
    $m = [regex]::Match($voce, $pattern)
    return $m.Success -and ($m.Groups[1].Value.Trim().Length -gt 0)
}

$atteso = $null
if (Ha-Sezione 'Breaking changes') { $atteso = 'maggiore' }
elseif (Ha-Sezione 'New features') { $atteso = 'minore' }
elseif (Ha-Sezione 'Fixes') { $atteso = 'patch' }
if (-not $atteso) {
    throw "La voce $versione non ha nessuna sezione con voci. Attese: '### Breaking changes', '### New features', '### Fixes'."
}

# L'ultima versione **rilasciata**, non l'ultimo tag posato. Non sono la stessa
# cosa: se una pubblicazione cade dopo il tag e prima della release — e' successo,
# la chiamata a GitHub non e' arrivata — resta in giro un tag che non corrisponde
# a niente. Contandolo, al secondo tentativo lo scatto risulterebbe 'nessuno' e
# lo script si fermerebbe proprio quando gli si sta chiedendo di riprendere (#67).
$precedente = (& gh release list --limit 1 --json tagName --jq '.[0].tagName' 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $precedente) {
    # Senza rete o senza release precedenti si ripiega sui tag: meglio un
    # controllo su una base imperfetta che nessun controllo.
    $precedente = (git -C $radice tag --list 'v*' --sort=-v:refname |
        Where-Object { $_ -ne $tag } | Select-Object -First 1)
}
if ($precedente) {
    $p = $precedente.TrimStart('v').Split('.')
    $n = $versione.Split('.')
    $fatto =
    if ([int]$n[0] -gt [int]$p[0]) { 'maggiore' }
    elseif ([int]$n[1] -gt [int]$p[1]) { 'minore' }
    elseif ([int]$n[2] -gt [int]$p[2]) { 'patch' }
    else { 'nessuno' }

    if ($fatto -ne $atteso) {
        throw "Il changelog dichiara uno scatto '$atteso' ma da $precedente a $tag lo scatto e' '$fatto'. Correggi l'uno o l'altro."
    }
}

# ----------------------------------------------------------------- pubblica

$installer = Join-Path $radice "ui\release\Scriba Setup $versione.exe"
if (-not $SenzaInstaller -and -not (Test-Path $installer)) {
    throw "Installer non trovato: $installer. Costruiscilo con 'cd ui; npm run dist', oppure passa -SenzaInstaller."
}

$commit = (git -C $radice rev-parse --short HEAD).Trim()
Write-Host "rilascio  $tag  ($atteso)  da $commit"

$base = "https://github.com/Z3roS4n/scriba/blob/$tag"
$descrizione = @"
Cosa è cambiato: **[CHANGELOG.it.md]($base/CHANGELOG.it.md)** · **[CHANGELOG.md]($base/CHANGELOG.md)** (English).

$(if ($SenzaInstaller) { "L'installer non è allegato: si costruisce dai sorgenti con ``cd ui && npm run dist``." } else { "L'installer allegato **non è firmato**: Windows mostrerà l'avviso di SmartScreen alla prima apertura. I limiti noti stanno nel changelog." })
"@
$fileDescrizione = Join-Path ([System.IO.Path]::GetTempPath()) "scriba-release-$versione.md"
[System.IO.File]::WriteAllText($fileDescrizione, $descrizione, (New-Object System.Text.UTF8Encoding($false)))

# Se ci fosse un secondo controllo sul tag qui, tornerebbe il difetto di #76:
# due regole sulla stessa domanda, e quella a monte che decide da sola. La
# risposta e' gia' stata data, in cima, e qui si usa e basta.
if ($riusoIlTag) {
    Write-Host "  il tag $tag c'era gia' su questo commit: riprendo"
} else {
    git -C $radice tag -a $tag -m "Scriba $versione"
    if ($LASTEXITCODE -ne 0) { throw "Non sono riuscito a posare il tag $tag." }
}
git -C $radice push --quiet origin $tag
if ($LASTEXITCODE -ne 0) { throw "Non sono riuscito a spingere il tag $tag su origin." }

$argomenti = @('release', 'create', $tag, '--title', "Scriba $versione", '--notes-file', $fileDescrizione)
if (-not $SenzaInstaller) { $argomenti += $installer }

& gh @argomenti
if ($LASTEXITCODE -ne 0) {
    # Si dice **in che stato e' rimasta**, non si indovina la causa. La prima
    # volta questo messaggio dava la colpa al tag mentre era caduta la rete, e
    # mandava a cercare nel posto sbagliato (#67).
    throw @"
gh release create non e' riuscito (uscita $LASTEXITCODE). L'errore vero e' quello stampato qui sopra.
Stato: il tag $tag e' su origin, la release NO. L'installer e' pronto in $installer.
Risolto il guasto, rilancia lo stesso comando: il tag viene riusato, non riposato.
"@
}
Remove-Item $fileDescrizione -ErrorAction SilentlyContinue
Write-Host "pubblicata: https://github.com/Z3roS4n/scriba/releases/tag/$tag"
