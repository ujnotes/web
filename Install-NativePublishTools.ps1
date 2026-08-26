[CmdletBinding()]
param(
    [string]$WebsiteRoot = 'H:\Website'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$minifyVersion = '2.24.17'
$minifyHash = 'A854E283026752C34CF0C69FE574854526ADDA50721244285C53CF0C195F23B0'
$closureVersion = 'v20250402'
$closureHash = '6FCBD20F75994EDC6856E336BC0147CE3DD7110C6B3A132E93EDF580673C72BB'
$toolsRoot = Join-Path ([System.IO.Path]::GetFullPath($WebsiteRoot)) '.native-tools'
$minifyZip = Join-Path $toolsRoot 'minify_windows_amd64.zip'
$minifyDirectory = Join-Path $toolsRoot 'minify'
$minifyExe = Join-Path $minifyDirectory 'minify.exe'
$closureJar = Join-Path $toolsRoot "closure-compiler-$closureVersion.jar"

New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null

function Get-PinnedDownload {
    param(
        [Parameter(Mandatory)] [string]$Url,
        [Parameter(Mandatory)] [string]$Destination,
        [Parameter(Mandatory)] [string]$Sha256
    )

    if (
        (Test-Path -LiteralPath $Destination -PathType Leaf) -and
        (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -eq $Sha256
    ) {
        return
    }
    & curl.exe -fL --retry 3 -o $Destination $Url
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed: $Url"
    }
    $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash
    if ($actual -ne $Sha256) {
        throw "SHA-256 mismatch for '$Destination': expected $Sha256, got $actual"
    }
}

Get-PinnedDownload `
    -Url "https://github.com/tdewolff/minify/releases/download/v$minifyVersion/minify_windows_amd64.zip" `
    -Destination $minifyZip `
    -Sha256 $minifyHash
if (-not (Test-Path -LiteralPath $minifyExe -PathType Leaf)) {
    New-Item -ItemType Directory -Path $minifyDirectory -Force | Out-Null
    Expand-Archive -LiteralPath $minifyZip -DestinationPath $minifyDirectory -Force
}

Get-PinnedDownload `
    -Url "https://repo1.maven.org/maven2/com/google/javascript/closure-compiler/$closureVersion/closure-compiler-$closureVersion.jar" `
    -Destination $closureJar `
    -Sha256 $closureHash

Write-Host "Native publishing tools are ready in $toolsRoot" -ForegroundColor Green
