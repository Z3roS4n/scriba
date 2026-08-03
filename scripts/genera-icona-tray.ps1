# Costruisce le icone dell'area di notifica in assets/tray/.
#
# Sono un'altra cosa dal logo, e vanno disegnate da capo invece che
# rimpicciolite. Il logo e' un disco scuro con un punto rosso: a 16 pixel su
# una barra scura il disco sparisce nel fondo e resta solo il punto: non si
# riconosce come Scriba, e un punto rosso nell'area di notifica per convenzione
# vuol dire "sto registrando". Mostrarlo sempre insegna a ignorarlo proprio
# quando conta.
#
# Qui si producono quattro icone, due assi per due:
#
#                 barra chiara            barra scura
#   a riposo      anello scuro            anello chiaro
#   registrando   anello + punto rosso    anello + punto rosso
#
# L'anello vuoto e' un pulsante di registrazione non premuto; con il punto
# dentro diventa premuto. Cosi' il rosso torna a voler dire qualcosa, e chi
# guarda la barra sa in che stato e' senza aprire niente.
#
# Il colore dell'inchiostro dipende dalla barra, non dal tema di Scriba:
# `main/index.ts` sceglie il file guardando `nativeTheme.shouldUseDarkColors` e
# lo ricambia quando Windows cambia.
#
#   powershell -ExecutionPolicy Bypass -File scripts/genera-icona-tray.ps1
#
# I .ico sono scritti con immagini BMP, non PNG: sotto i 48 pixel e' la forma
# che tutto sa leggere — `System.Drawing.Icon`, per dirne una, i PNG dentro un
# .ico non li decodifica, ed e' anche cio' che rende queste icone verificabili
# da uno script invece che solo a occhio.

param(
    [string]$Destinazione = "$PSScriptRoot\..\assets\tray"
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

# Le misure che Windows chiede all'area di notifica: 100%, 125%, 150%, 200%.
$Misure = @(16, 20, 24, 32)

$Corallo = [System.Drawing.Color]::FromArgb(0xF0, 0x60, 0x5F)   # campionato dal logo
$Inchiostro = @{
    chiara = [System.Drawing.Color]::FromArgb(0x1B, 0x1F, 0x27)  # su barra chiara
    scura  = [System.Drawing.Color]::FromArgb(0xEC, 0xEC, 0xEF)  # su barra scura
}

New-Item -ItemType Directory -Force -Path $Destinazione | Out-Null

function New-Disegno([int]$m, $inchiostro, [bool]$registrando) {
    $b = New-Object System.Drawing.Bitmap($m, $m, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($b)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    # Spessore proporzionale: a 16 pixel sono 2, a 32 sono 4. Sotto i 2 l'anello
    # sparisce nell'antialiasing, sopra i 4 si chiude e sembra un disco pieno.
    $spessore = [math]::Max(2.0, [math]::Round($m / 8.0))
    $margine = $spessore / 2.0 + ($m / 16.0)
    $lato = $m - 2 * $margine

    $penna = New-Object System.Drawing.Pen($inchiostro, $spessore)
    $g.DrawEllipse($penna, $margine, $margine, $lato, $lato)
    $penna.Dispose()

    if ($registrando) {
        # Il punto occupa poco piu' di un terzo: piu' grande tocca l'anello e i
        # due si fondono in una macchia, piu' piccolo a 16 pixel non si vede.
        $d = [math]::Max(4.0, $m * 0.36)
        $o = ($m - $d) / 2.0
        $pennello = New-Object System.Drawing.SolidBrush($Corallo)
        $g.FillEllipse($pennello, $o, $o, $d, $d)
        $pennello.Dispose()
    }

    $g.Dispose()
    return $b
}

function ConvertTo-Dib($bitmap) {
    <#
        Un'immagine dentro un .ico in forma BMP: intestazione, pixel BGRA dal
        basso verso l'alto, e la maschera AND. La maschera resta tutta a zero —
        la trasparenza la porta il canale alfa — ma il campo deve esserci
        comunque, e un .ico senza si legge storto.
    #>
    $w = $bitmap.Width; $h = $bitmap.Height
    $ms = New-Object System.IO.MemoryStream
    $bw = New-Object System.IO.BinaryWriter($ms)

    $bw.Write([UInt32]40)          # biSize
    $bw.Write([Int32]$w)
    $bw.Write([Int32]($h * 2))     # doppia: XOR + AND, come vuole il formato
    $bw.Write([UInt16]1)           # biPlanes
    $bw.Write([UInt16]32)          # biBitCount
    $bw.Write([UInt32]0)           # BI_RGB
    $bw.Write([UInt32]0)           # biSizeImage: 0 e' ammesso senza compressione
    $bw.Write([Int32]0); $bw.Write([Int32]0)
    $bw.Write([UInt32]0); $bw.Write([UInt32]0)

    for ($y = $h - 1; $y -ge 0; $y--) {
        for ($x = 0; $x -lt $w; $x++) {
            $c = $bitmap.GetPixel($x, $y)
            $bw.Write([Byte]$c.B); $bw.Write([Byte]$c.G)
            $bw.Write([Byte]$c.R); $bw.Write([Byte]$c.A)
        }
    }

    $bytePerRiga = [math]::Ceiling($w / 8.0)
    $riempimento = (4 - ($bytePerRiga % 4)) % 4
    for ($y = 0; $y -lt $h; $y++) {
        for ($i = 0; $i -lt $bytePerRiga + $riempimento; $i++) { $bw.Write([Byte]0) }
    }

    $bw.Flush()
    $fuori = $ms.ToArray()
    $bw.Dispose()
    # `return $fuori` srotolerebbe l'array nella pipeline e chi lo riceve si
    # ritroverebbe un Object[] invece di un byte[]: `BinaryWriter.Write` a quel
    # punto aggancia l'overload sbagliato e scrive un byte solo. La virgola lo
    # impedisce. Il sintomo era un .ico di 74 byte con l'indice giusto e nessuna
    # immagine dentro.
    return , $fuori
}

function Write-Ico([string]$file, $immagini) {
    $ms = New-Object System.IO.MemoryStream
    $w = New-Object System.IO.BinaryWriter($ms)
    $w.Write([UInt16]0); $w.Write([UInt16]1); $w.Write([UInt16]$immagini.Count)

    $scorrimento = 6 + 16 * $immagini.Count
    foreach ($i in $immagini) {
        $w.Write([Byte]$i.Misura); $w.Write([Byte]$i.Misura)
        $w.Write([Byte]0); $w.Write([Byte]0)
        $w.Write([UInt16]1); $w.Write([UInt16]32)
        $w.Write([UInt32]$i.Byte.Length); $w.Write([UInt32]$scorrimento)
        $scorrimento += $i.Byte.Length
    }
    # Cast esplicito: se per qualunque motivo arrivasse un Object[], scrivere
    # senza accorgersene produrrebbe un file che sembra a posto nell'indice e
    # non contiene nessuna immagine.
    foreach ($i in $immagini) { $w.Write([byte[]]$i.Byte) }
    $w.Flush()
    [System.IO.File]::WriteAllBytes($file, $ms.ToArray())
    $w.Dispose()

    # Si rilegge quello che si e' appena scritto: un .ico che Windows rifiuta e'
    # un'icona che manca, e la si scoprirebbe guardando la barra invece che qui.
    $prova = New-Object System.Drawing.Icon($file, 16, 16)
    if ($prova.Width -ne 16) { throw "$file : Windows non lo legge a 16 pixel" }
    $prova.Dispose()
}

foreach ($barra in 'chiara', 'scura') {
    foreach ($stato in @{n = 'riposo'; r = $false }, @{n = 'registra'; r = $true }) {
        $immagini = @()
        foreach ($m in $Misure) {
            $b = New-Disegno $m $Inchiostro[$barra] $stato.r
            $immagini += , @{ Misura = $m; Byte = (ConvertTo-Dib $b) }
            $b.Dispose()
        }
        $nome = "tray-$($stato.n)-$barra.ico"
        # Percorso assoluto: System.Drawing non usa la cartella corrente di
        # PowerShell, e con un percorso relativo l'errore che esce parla d'altro.
        $file = [System.IO.Path]::GetFullPath((Join-Path $Destinazione $nome))
        Write-Ico $file $immagini
        Write-Host "  $nome  ($($Misure -join ', ')) - $((Get-Item $file).Length) byte, riletto ok"
    }
}

Write-Host "Icone dell'area di notifica scritte in $Destinazione"
