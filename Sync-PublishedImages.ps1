[CmdletBinding()]
param(
    [string]$SiteProject = 'D:\Ujnotes\Website\site\project',
    [string]$PublicProject = 'D:\Ujnotes\Website\project\build',
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$urlPath = Join-Path $SiteProject 'Config\Url.tsv'
$resourceRoot = Join-Path $SiteProject 'root\Resource'
$publicRoot = Join-Path $PublicProject 'public'
$changed = [System.Collections.Generic.List[string]]::new()

foreach ($line in [System.IO.File]::ReadAllLines($urlPath) | Select-Object -Skip 1) {
    $fields = @($line -split "`t")
    if ($fields.Count -lt 3 -or $fields[2].Trim().ToLowerInvariant() -ne 'jpg') { continue }
    $path = $fields[0].Replace('\', '/').Trim('/')
    $name = $fields[1].Trim('/')
    if (-not $name -or $path -eq '404') { continue }
    $slug = if ($name -eq 'index') { $path } elseif ($path) { "$path/$name" } else { $name }
    if (-not $slug -or $slug -match '(^|/)\.\.?(/|$)') { continue }
    $relative = $slug.Replace('/', '\')
    $page = Join-Path $publicRoot "$relative\index.html"
    if (-not (Test-Path -LiteralPath $page)) { continue }

    # Match the live component lookup: a flat Resource image wins over index.jpg.
    $flatSource = Join-Path $resourceRoot "$relative.jpg"
    $indexSource = Join-Path $resourceRoot "$relative\index.jpg"
    $source = if (Test-Path -LiteralPath $flatSource) { $flatSource } elseif (Test-Path -LiteralPath $indexSource) { $indexSource } else { $null }
    if (-not $source) { throw "Url.tsv has no source image for published page: $slug" }
    $target = Join-Path $publicRoot "$relative\index.jpg"
    $flatPublic = Join-Path $publicRoot "$relative.jpg"
    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $destinations = @(@($target, $flatPublic) | Where-Object { Test-Path -LiteralPath $_ })
    if ($destinations.Count -eq 0) { $destinations = @($target) }
    $stale = @($destinations | Where-Object { -not (Test-Path -LiteralPath $_) -or (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash -ne $sourceHash })
    if ($stale.Count -gt 0) {
        $changed.Add($slug)
        if ($Apply) {
            foreach ($destination in $stale) {
                New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
                Copy-Item -LiteralPath $source -Destination $destination -Force
            }
        }
    }
}

$changed | Sort-Object -Unique
if (-not $Apply) { Write-Host "Dry run: $($changed.Count) published image routes need sync. Use -Apply to update the local web-public checkout." }
