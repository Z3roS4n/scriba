# Costruisce assets/scriba.ico dalle dimensioni che Windows usa davvero.
#
# Perche' non basta un'immagine sola: un .ico puo' contenerne piu' d'una, e
# Windows sceglie quella della misura giusta invece di rimpicciolire la piu'
# grande. La differenza si vede nell'area di notifica e nella barra delle
# applicazioni, dove l'icona vive a 16 e 32 pixel: rimpicciolita al volo esce
# molle, disegnata a quella misura no.
#
# Sorgente di verita' e' assets/scriba.png (256x256). Questo script si esegue a
# mano quando il logo cambia, non a ogni build: il .ico prodotto sta nel
# repository, cosi' chi costruisce l'installer non ha bisogno di rigenerarlo.
#
#   powershell -ExecutionPolicy Bypass -File scripts/genera-icona.ps1
#
# Il formato scritto e' quello con i PNG dentro (Vista in avanti). Scriba gira
# solo su Windows 10/11, che lo leggono senza problemi.

param(
    [string]$Sorgente = "$PSScriptRoot\..\assets\scriba.png",
    [string]$Destinazione = "$PSScriptRoot\..\assets\scriba.ico"
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

# 16 e 32: area di notifica e barra delle applicazioni. 24 e 48: schermi con
# scalatura diversa dal 100%. 64/128/256: finestra delle proprieta', anteprime
# grandi in Esplora risorse e la voce del menu Start.
$Misure = @(16, 24, 32, 48, 64, 128, 256)

if (-not (Test-Path $Sorgente)) { throw "Sorgente non trovata: $Sorgente" }
$originale = [System.Drawing.Image]::FromFile((Resolve-Path $Sorgente))

try {
    $immagini = @()
    foreach ($m in $Misure) {
        $tela = New-Object System.Drawing.Bitmap($m, $m, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
        $g = [System.Drawing.Graphics]::FromImage($tela)
        try {
            # Bicubica di qualita' alta: sotto i 32 pixel la differenza fra
            # questa e la riduzione predefinita e' la differenza fra un bordo
            # pulito e uno seghettato.
            $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
            $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
            $g.Clear([System.Drawing.Color]::Transparent)
            $g.DrawImage($originale, (New-Object System.Drawing.Rectangle(0, 0, $m, $m)))
        } finally {
            $g.Dispose()
        }

        $buffer = New-Object System.IO.MemoryStream
        $tela.Save($buffer, [System.Drawing.Imaging.ImageFormat]::Png)
        $tela.Dispose()
        $immagini += , @{ Misura = $m; Byte = $buffer.ToArray() }
        $buffer.Dispose()
    }
} finally {
    $originale.Dispose()
}

# ICONDIR (6 byte) + un ICONDIRENTRY da 16 byte per immagine, poi i PNG in coda.
$uscita = New-Object System.IO.MemoryStream
$w = New-Object System.IO.BinaryWriter($uscita)
$w.Write([UInt16]0)                  # riservato
$w.Write([UInt16]1)                  # tipo: 1 = icona
$w.Write([UInt16]$immagini.Count)

$scorrimento = 6 + (16 * $immagini.Count)
foreach ($img in $immagini) {
    # 256 si scrive come 0: il campo e' di un byte solo e 256 non ci sta.
    $lato = if ($img.Misura -ge 256) { 0 } else { $img.Misura }
    $w.Write([Byte]$lato)            # larghezza
    $w.Write([Byte]$lato)            # altezza
    $w.Write([Byte]0)                # colori della tavolozza: 0 = colore pieno
    $w.Write([Byte]0)                # riservato
    $w.Write([UInt16]1)              # piani
    $w.Write([UInt16]32)             # bit per pixel
    $w.Write([UInt32]$img.Byte.Length)
    $w.Write([UInt32]$scorrimento)
    $scorrimento += $img.Byte.Length
}
foreach ($img in $immagini) { $w.Write($img.Byte) }

$w.Flush()
[System.IO.File]::WriteAllBytes((New-Item -ItemType File -Path $Destinazione -Force).FullName, $uscita.ToArray())
$w.Dispose()

$peso = [math]::Round((Get-Item $Destinazione).Length / 1KB, 1)
Write-Host "Scritto $Destinazione : $($immagini.Count) misure ($($Misure -join ', ')), $peso KB"
