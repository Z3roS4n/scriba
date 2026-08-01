# Costruisce la grafica dell'installer NSIS in ui/build-resources.
#
# electron-builder prende questi file per convenzione da
# `directories.buildResources` (vedi ui/electron-builder.yml) e non serve
# nominarli nella configurazione: bastano il nome e la misura giusti.
#
#   installerHeader.bmp     150x57    barra in alto di ogni pagina
#   installerSidebar.bmp    164x314   pagine di benvenuto e di fine
#   uninstallerSidebar.bmp  164x314   le stesse, disinstallando
#   installerIcon.ico                 icona del Setup.exe
#   uninstallerIcon.ico               icona del disinstallatore
#
# Due vincoli che non sono opzionali, e che spiegano perche' i tre BMP non si
# somigliano:
#
# 1. I BMP devono essere a 24 bit. NSIS non legge il canale alfa: un BMP a 32
#    bit si vede con lo sfondo sporco o nero. Per questo si disegna su una tela
#    Format24bppRgb, e la trasparenza del logo si appiattisce sul fondo che gli
#    sta sotto invece di restare tale.
# 2. L'intestazione MUI2 vive su una barra BIANCA di sistema, e quel colore non
#    si cambia. Una grafica scura li' dentro diventa un rettangolo nero
#    incollato sul bianco: l'header si disegna chiaro, per fondersi. Il pannello
#    laterale invece occupa tutto il riquadro, e li' il tema scuro del prodotto
#    ci sta bene.
#
# Si esegue a mano quando il logo cambia, non a ogni build: i file prodotti
# stanno nel repository.
#
#   powershell -ExecutionPolicy Bypass -File scripts/genera-grafica-installer.ps1

param(
    [string]$Logo = "$PSScriptRoot\..\assets\scriba.png",
    [string]$Icona = "$PSScriptRoot\..\assets\scriba.ico",
    [string]$Destinazione = "$PSScriptRoot\..\ui\build-resources"
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

# Campionati dal logo stesso, non scelti a occhio: il punto della registrazione
# e il disco che gli sta intorno.
$Corallo = [System.Drawing.Color]::FromArgb(0xF0, 0x60, 0x5F)
$Scuro   = [System.Drawing.Color]::FromArgb(0x0E, 0x10, 0x14)
$Scuro2  = [System.Drawing.Color]::FromArgb(0x1B, 0x1F, 0x27)
$Inchio  = [System.Drawing.Color]::FromArgb(0x17, 0x1A, 0x21)
$Chiaro  = [System.Drawing.Color]::FromArgb(0xF5, 0xF5, 0xF7)
$Tenue   = [System.Drawing.Color]::FromArgb(0x8E, 0x90, 0x99)

if (-not (Test-Path $Logo)) { throw "Logo non trovato: $Logo" }
New-Item -ItemType Directory -Force -Path $Destinazione | Out-Null
$sorgente = [System.Drawing.Image]::FromFile((Resolve-Path $Logo))

function New-Tela([int]$w, [int]$h) {
    # 24 bit: vedi il vincolo 1 in cima al file.
    $t = New-Object System.Drawing.Bitmap($w, $h, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
    $g = [System.Drawing.Graphics]::FromImage($t)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode   = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.SmoothingMode     = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    # Antialiasing in scala di grigi, non ClearType. ClearType usa i sottopixel
    # dello schermo e lascia frange colorate dentro il bitmap: invisibili a
    # dimensione naturale, ben visibili appena NSIS scala l'immagine su uno
    # schermo ad alta densita', dove diventano bordi rosa e verdi attorno alle
    # lettere. Qui si sta scrivendo su un file, non su un monitor.
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    return @{ Tela = $t; G = $g }
}

function Scrivi($g, [string]$testo, $font, $colore, [single]$x, [single]$y, [string]$allineamento = 'left') {
    $pennello = New-Object System.Drawing.SolidBrush($colore)
    $formato = New-Object System.Drawing.StringFormat
    if ($allineamento -eq 'center') { $formato.Alignment = [System.Drawing.StringAlignment]::Center }
    $g.DrawString($testo, $font, $pennello, $x, $y, $formato)
    $formato.Dispose(); $pennello.Dispose()
}

# Segoe UI c'e' su ogni Windows 10/11, che e' l'unico sistema su cui Scriba
# gira: non serve un ripiego, e sceglierne uno diverso qui renderebbe
# l'installer diverso dal resto del sistema senza motivo.
$FontTitolo   = New-Object System.Drawing.Font("Segoe UI Semibold", 19, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$FontHeader   = New-Object System.Drawing.Font("Segoe UI Semibold", 15, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$FontDidasc   = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$FontPiccolo  = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)

# ------------------------------------------------------- pannello laterale

function New-Pannello([string]$file, [string]$riga1, [string]$riga2, [bool]$spento) {
    $c = New-Tela 164 314
    $g = $c.G

    $rett = New-Object System.Drawing.Rectangle(0, 0, 164, 314)
    $sfumatura = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
        $rett, $Scuro2, $Scuro, [System.Drawing.Drawing2D.LinearGradientMode]::Vertical)
    $g.FillRectangle($sfumatura, $rett)
    $sfumatura.Dispose()

    # Un alone dietro il marchio. Non e' decorazione: il disco del logo e' quasi
    # dello stesso colore del fondo, e senza qualcosa che lo stacchi resterebbe
    # visibile solo il punto rosso, sospeso nel vuoto. Corallo installando,
    # neutro disinstallando — il rosso li' dentro suonerebbe come un allarme.
    $tinta = & { if ($spento) { [System.Drawing.Color]::FromArgb(0xFF, 0xFF, 0xFF) } else { $Corallo } }
    $opacita = & { if ($spento) { 26 } else { 46 } }
    $percorso = New-Object System.Drawing.Drawing2D.GraphicsPath
    $percorso.AddEllipse(14, 40, 136, 136)
    $alone = New-Object System.Drawing.Drawing2D.PathGradientBrush($percorso)
    $alone.CenterColor = [System.Drawing.Color]::FromArgb($opacita, $tinta)
    $alone.SurroundColors = @([System.Drawing.Color]::FromArgb(0, $tinta))
    $g.FillPath($alone, $percorso)
    $alone.Dispose(); $percorso.Dispose()

    $g.DrawImage($sorgente, (New-Object System.Drawing.Rectangle(46, 68, 72, 72)))

    Scrivi $g "Scriba" $FontTitolo $Chiaro 82 156 'center'

    $penna = New-Object System.Drawing.Pen((& { if ($spento) { $Tenue } else { $Corallo } }), 2)
    $g.DrawLine($penna, 68, 186, 96, 186)
    $penna.Dispose()

    Scrivi $g $riga1 $FontDidasc $Tenue 82 202 'center'
    Scrivi $g $riga2 $FontPiccolo $Tenue 82 218 'center'

    $c.Tela.Save((Join-Path $Destinazione $file), [System.Drawing.Imaging.ImageFormat]::Bmp)
    $g.Dispose(); $c.Tela.Dispose()
    Write-Host "  $file  164x314"
}

New-Pannello "installerSidebar.bmp" "Registra le tue call." "Trascrive su questo computer." $false
# Il disinstallatore dice l'unica cosa che serve sapere in quel momento, e che
# nessuno si aspetta: le registrazioni non se ne vanno con il programma.
New-Pannello "uninstallerSidebar.bmp" "Le registrazioni restano." "Non le porta via nessuno." $true

# ------------------------------------------------------------ intestazione

$c = New-Tela 150 57
$g = $c.G
$g.Clear([System.Drawing.Color]::White)   # vedi il vincolo 2 in cima al file
$g.DrawImage($sorgente, (New-Object System.Drawing.Rectangle(14, 13, 31, 31)))
Scrivi $g "Scriba" $FontHeader $Inchio 53 19
$c.Tela.Save((Join-Path $Destinazione "installerHeader.bmp"), [System.Drawing.Imaging.ImageFormat]::Bmp)
$g.Dispose(); $c.Tela.Dispose()
Write-Host "  installerHeader.bmp  150x57"

# ------------------------------------------------------------------ icone

foreach ($nome in "installerIcon.ico", "uninstallerIcon.ico") {
    Copy-Item $Icona (Join-Path $Destinazione $nome) -Force
    Write-Host "  $nome"
}

# ---------------------------------------------------------------- licenza
#
# Copiata da LICENSE invece di essere scritta a mano qui: due copie dello
# stesso testo divergono, e la prima a diventare falsa e' sempre quella che
# nessuno rilegge. NSIS vuole un .txt con le terminazioni di riga di Windows.
$licenza = Join-Path $Destinazione "license.txt"
$testo = (Get-Content "$PSScriptRoot\..\LICENSE" -Raw) -replace "`r`n", "`n" -replace "`n", "`r`n"
[System.IO.File]::WriteAllText($licenza, $testo, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "  license.txt  (copia di LICENSE)"

$sorgente.Dispose()
foreach ($f in $FontTitolo, $FontHeader, $FontDidasc, $FontPiccolo) { $f.Dispose() }
Write-Host "Grafica dell'installer scritta in $Destinazione"
