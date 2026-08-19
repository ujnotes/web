<#
.SYNOPSIS
Publishes an existing Notion article subtree through one guarded local workflow.

.DESCRIPTION
Discovers canonical Website database rows at RootSlug and below it, optionally
copies one JPEG cover to every row, queues only those canonical rows, invokes
publish-notion.ps1 for each row while reusing one renderer container, and
verifies every canonical production cover by SHA-256.

Notion body edits (including translated disclaimer text) must be completed
before this script is run. Nested translations are rendered and verified
atomically by publish-notion.ps1; they are never queued separately.

.EXAMPLE
.\publish-notion-subtree.ps1 `
    -RootSlug computer/game/doom `
    -CoverSource H:\Resource\doom.jpg

.EXAMPLE
.\publish-notion-subtree.ps1 -RootSlug computer/game/doom -DryRun
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_./-]*$')]
    [string]$RootSlug,

    [string]$CoverSource,

    [string]$NcmsProject = 'D:\Projects\Cutie\Sample\ncms\project',

    [string]$SiteProject = 'H:\Website\site\project',

    [string]$BaseUrl = 'https://ujnotes.com',

    [int]$DeployTimeoutSeconds = 600,

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Python -X utf8 writes UTF-8; Windows console capture defaults to OEM (CP437)
# and will mojibake Hindi titles/descriptions before ConvertFrom-Json.
$script:Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $script:Utf8NoBom
[Console]::OutputEncoding = $script:Utf8NoBom
$OutputEncoding = $script:Utf8NoBom
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$PSNativeCommandUseErrorActionPreference = $false

function Write-Step {
    param([Parameter(Mandatory)] [string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-Native {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string[]]$ArgumentList,
        [Parameter(Mandatory)] [string]$WorkingDirectory,
        [switch]$Capture
    )

    Push-Location $WorkingDirectory
    try {
        $output = & $FilePath @ArgumentList 2>&1
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw "$FilePath failed with exit code $exitCode.`n$(($output | ForEach-Object { "$_" }) -join "`n")"
        }
        if ($Capture) {
            return @($output)
        }
        $output | ForEach-Object { Write-Host "$_" }
    }
    finally {
        Pop-Location
    }
}

function Assert-CleanRepository {
    param([Parameter(Mandatory)] [string]$Path)
    $status = @(Invoke-Native -FilePath 'git' -ArgumentList @('status', '--porcelain') -WorkingDirectory $Path -Capture)
    if ($status.Count -gt 0 -and ($status -join '').Trim()) {
        throw "Repository must be clean before a subtree publish: $Path`n$($status -join "`n")"
    }
}

function Resolve-ArticleComponentDirectory {
    param(
        [Parameter(Mandatory)] [string]$ComponentRoot,
        [Parameter(Mandatory)] [string]$Slug
    )

    $current = Get-Item -LiteralPath $ComponentRoot
    foreach ($segment in $Slug.Split('/')) {
        $matches = @(
            Get-ChildItem -LiteralPath $current.FullName -Directory |
                Where-Object { $_.Name -ieq $segment }
        )
        if ($matches.Count -ne 1) {
            throw "Expected one case-preserving component directory for '$Slug' below '$($current.FullName)'; found $($matches.Count)."
        }
        $current = $matches[0]
    }
    if (-not (Test-Path -LiteralPath (Join-Path $current.FullName 'index.php'))) {
        throw "Canonical component is missing index.php: $($current.FullName)"
    }
    return $current
}

if ($RootSlug.StartsWith('/') -or $RootSlug.EndsWith('/') -or $RootSlug.Contains('\') -or
    @($RootSlug.Split('/') | Where-Object { $_ -in @('.', '..') }).Count -gt 0) {
    throw "Unsafe root slug: '$RootSlug'"
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$publisher = Join-Path $scriptRoot 'publish-notion.ps1'
$python = Join-Path $NcmsProject '.venv\Scripts\python.exe'
$componentRoot = Join-Path $SiteProject 'root\HTML\Component'
$resourceRoot = Join-Path $SiteProject 'root\Resource'
$publicRepo = Join-Path $scriptRoot 'build'
$composeFile = Join-Path $scriptRoot 'compose-dev.yaml'

foreach ($required in @($publisher, $python, $componentRoot, $resourceRoot, $publicRepo, $composeFile)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path not found: $required"
    }
}

Write-Step 'Preflighting repositories and source image'
Assert-CleanRepository -Path $SiteProject
Assert-CleanRepository -Path $publicRepo

$resolvedCover = $null
$coverHash = $null
if ($CoverSource) {
    if (-not (Test-Path -LiteralPath $CoverSource -PathType Leaf)) {
        throw "Cover source does not exist exactly as supplied: $CoverSource"
    }
    $resolvedCover = (Resolve-Path -LiteralPath $CoverSource).Path
    if ([System.IO.Path]::GetExtension($resolvedCover) -notin @('.jpg', '.jpeg', '.JPG', '.JPEG')) {
        throw "Cover source must already be a JPEG; convert it before publishing: $resolvedCover"
    }
    Add-Type -AssemblyName System.Drawing
    $image = [System.Drawing.Image]::FromFile($resolvedCover)
    try {
        if ($image.RawFormat.Guid -ne [System.Drawing.Imaging.ImageFormat]::Jpeg.Guid) {
            throw "Cover source has a .jpg/.jpeg name but is not JPEG data: $resolvedCover"
        }
    }
    finally {
        $image.Dispose()
    }
    $coverHash = (Get-FileHash -LiteralPath $resolvedCover -Algorithm SHA256).Hash
}

Write-Step 'Discovering canonical Notion rows in the subtree'
$discoverCode = @'
import json
import sys
import ncms_fetch as ncms

root = sys.argv[1]
allowed = {"publish", "published"}
pages = []
cursor = None
while True:
    response = ncms.notion.databases.query(
        database_id=ncms.database_id,
        start_cursor=cursor,
    )
    pages.extend(response.get("results", []))
    if not response.get("has_more"):
        break
    cursor = response.get("next_cursor")

matches = []
for page in pages:
    slug = ncms.page_slug(page)
    status_value = page.get("properties", {}).get("Status", {}).get("select") or {}
    status = status_value.get("name", "")
    if slug == root or slug.startswith(root + "/"):
        if status not in allowed:
            continue
        ncms.validate_slug(slug)
        matches.append({"page_id": page["id"], "slug": slug, "status": status})

matches.sort(key=lambda item: (item["slug"].count("/"), item["slug"]))
if not matches or matches[0]["slug"] != root:
    raise RuntimeError(f"No publishable canonical root row found for {root!r}")
print("SUBTREE_RESULT=" + json.dumps(matches, ensure_ascii=True))
'@

$discoverOutput = @(
    Invoke-Native -FilePath $python `
        -ArgumentList @('-X', 'utf8', '-c', $discoverCode, $RootSlug) `
        -WorkingDirectory $NcmsProject `
        -Capture
)
$marker = $discoverOutput | Where-Object { "$_".StartsWith('SUBTREE_RESULT=') } | Select-Object -Last 1
if (-not $marker) {
    throw 'Notion subtree discovery did not return metadata.'
}
$articles = @($marker.Substring('SUBTREE_RESULT='.Length) | ConvertFrom-Json)
$articles | ForEach-Object { Write-Host "  $($_.status)`t$($_.slug)" }

$coverDestinations = @()
if ($resolvedCover) {
    foreach ($article in $articles) {
        $componentDirectory = Resolve-ArticleComponentDirectory -ComponentRoot $componentRoot -Slug ([string]$article.slug)
        $relative = [System.IO.Path]::GetRelativePath((Resolve-Path -LiteralPath $componentRoot).Path, $componentDirectory.FullName)
        $coverDestinations += Join-Path (Join-Path $resourceRoot $relative) 'index.jpg'
    }
}

if ($DryRun) {
    if ($resolvedCover) {
        Write-Host "Would copy $resolvedCover to $($coverDestinations.Count) article cover paths."
    }
    Write-Host "Would queue and publish $($articles.Count) canonical rows with nested translations handled atomically."
    Write-Host 'Dry run complete; no files, Notion rows, containers, repositories, or deployments were changed.' -ForegroundColor Green
    return
}

if ($resolvedCover) {
    Write-Step 'Copying the cover to every canonical article path'
    foreach ($destination in $coverDestinations) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $resolvedCover -Destination $destination -Force
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $coverHash) {
            throw "Copied cover hash mismatch: $destination"
        }
        Write-Host "  $destination"
    }
}

Write-Step 'Queueing canonical Notion rows once'
$queueCode = @'
import json
import sys
import ncms_fetch as ncms

with open(sys.argv[1], encoding='utf-8') as handle:
    items = json.load(handle)
for item in items:
    page = ncms.notion.pages.retrieve(page_id=item["page_id"])
    actual = ncms.page_slug(page)
    if actual != item["slug"]:
        raise RuntimeError(f"Notion slug changed: expected {item['slug']!r}, got {actual!r}")
    status_value = page.get("properties", {}).get("Status", {}).get("select") or {}
    status = status_value.get("name", "")
    if status not in {"publish", "published"}:
        raise RuntimeError(f"Refusing to queue {actual!r} from status {status!r}")
    if status != "publish":
        ncms.notion.pages.update(
            page_id=item["page_id"],
            properties={"Status": {"select": {"name": "publish"}}},
        )
print(f"Queued {len(items)} canonical rows")
'@
$queueFile = Join-Path $env:TEMP ('ujnotes-subtree-queue-{0}.json' -f [guid]::NewGuid().ToString('n'))
try {
    $articleJson = ConvertTo-Json -InputObject $articles -Compress -Depth 6
    [System.IO.File]::WriteAllText($queueFile, $articleJson, [System.Text.UTF8Encoding]::new($false))
    Invoke-Native -FilePath $python `
        -ArgumentList @('-X', 'utf8', '-c', $queueCode, $queueFile) `
        -WorkingDirectory $NcmsProject
}
finally {
    if (Test-Path -LiteralPath $queueFile) {
        Remove-Item -LiteralPath $queueFile -Force
    }
}

$webSiteWasRunning = $false
& docker info --format '{{.ServerVersion}}' *> $null
if ($LASTEXITCODE -eq 0) {
    $runningServices = @(& docker compose -f $composeFile -p ujnotes ps --status running --services 2>$null)
    $webSiteWasRunning = $runningServices -contains 'web-site'
}

try {
    Write-Step 'Publishing the subtree with one warm renderer container'
    foreach ($article in $articles) {
        Write-Host "`nPublishing $($article.slug)" -ForegroundColor Yellow
        & $publisher `
            -Slug ([string]$article.slug) `
            -NcmsProject $NcmsProject `
            -BaseUrl $BaseUrl `
            -DeployTimeoutSeconds $DeployTimeoutSeconds `
            -KeepBuildContainer
        if ($LASTEXITCODE -ne 0) {
            throw "Publisher failed for '$($article.slug)'. Remaining canonical rows stay queued."
        }
    }

    if ($resolvedCover) {
        Write-Step 'Verifying canonical production cover hashes'
        $verifyRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('ujnotes-cover-verify-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $verifyRoot | Out-Null
        try {
            foreach ($article in $articles) {
                $download = Join-Path $verifyRoot (([string]$article.slug).Replace('/', '-') + '.jpg')
                & curl.exe -4 -sS -L --retry 2 --retry-all-errors --connect-timeout 10 --max-time 30 `
                    -o $download "$BaseUrl/$($article.slug).jpg"
                if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $download)) {
                    throw "Could not download canonical cover: $BaseUrl/$($article.slug).jpg"
                }
                $liveHash = (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash
                if ($liveHash -ne $coverHash) {
                    throw "Live cover hash mismatch: $BaseUrl/$($article.slug).jpg"
                }
                Write-Host "  verified $BaseUrl/$($article.slug).jpg"
            }
        }
        finally {
            if (Test-Path -LiteralPath $verifyRoot) {
                Remove-Item -LiteralPath $verifyRoot -Recurse -Force
            }
        }
    }
}
finally {
    if (-not $webSiteWasRunning) {
        & docker compose -f $composeFile -p ujnotes stop web-site
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'Could not stop the temporary web-site renderer container.'
        }
    }
}

Write-Host "`nPublished $($articles.Count) canonical rows under $RootSlug." -ForegroundColor Green
Write-Host 'Review and commit the generated web-site source changes according to AGENTS.md.'
