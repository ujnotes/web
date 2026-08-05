<#
.SYNOPSIS
Publishes one Status=publish Notion article to ujnotes in a guarded end-to-end run.

.EXAMPLE
.\publish-notion.ps1

Publishes automatically when exactly one Notion page is queued.

.EXAMPLE
.\publish-notion.ps1 -Slug world/philosophy/cognition

Selects one page explicitly when multiple pages are queued.

.EXAMPLE
.\publish-notion.ps1 -Slug world/philosophy/cognition -DryRun

Fetches, renders, and PHP-lints the article without changing source, git, the live site, or Notion.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Slug,

    [string]$NcmsProject = 'D:\Projects\Cutie\Sample\ncms\project',

    [string]$BaseUrl = 'https://ujnotes.com',

    [int]$DeployTimeoutSeconds = 300,

    [switch]$DryRun,

    [switch]$KeepBuildContainer
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

function Write-Step {
    param([string]$Message)
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
        if ($Capture) {
            $output = & $FilePath @ArgumentList 2>&1
            $exitCode = $LASTEXITCODE
            if ($exitCode -ne 0) {
                $details = ($output | ForEach-Object { "$_" }) -join "`n"
                throw "$FilePath failed with exit code $exitCode.`n$details"
            }
            return @($output)
        }

        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "$FilePath failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

function Write-Utf8Text {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Text
    )

    [System.IO.File]::WriteAllText(
        $Path,
        $Text,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Write-LinesPreservingNewline {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string[]]$Lines
    )

    $raw = if (Test-Path -LiteralPath $Path) {
        [System.IO.File]::ReadAllText($Path)
    }
    else {
        ''
    }
    $newline = if ($raw.Contains("`r`n")) { "`r`n" } else { "`n" }
    Write-Utf8Text -Path $Path -Text (($Lines -join $newline) + $newline)
}

function Assert-SafeSlug {
    param([Parameter(Mandatory)] [string]$Value)

    if (
        [string]::IsNullOrWhiteSpace($Value) -or
        $Value.StartsWith('/') -or
        $Value.EndsWith('/') -or
        $Value.Contains('\') -or
        $Value -match '(^|/)\.\.?($|/)' -or
        $Value -notmatch '^[A-Za-z0-9][A-Za-z0-9_./-]*$'
    ) {
        throw "Unsafe article slug: '$Value'."
    }
}


function Merge-IdRow {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$ArticleSlug,
        [Parameter(Mandatory)] [string]$ArticleRow
    )

    $lines = @([System.IO.File]::ReadAllLines($Path))
    if ($lines.Count -eq 0) {
        throw "ID file is empty: $Path"
    }

    $headerFields = @($lines[0] -split "`t")
    $typeIndex = [Array]::IndexOf($headerFields, 'Type')
    if ($typeIndex -ge 0) {
        $articleFields = @($ArticleRow -split "`t")
        while ($articleFields.Count -lt $headerFields.Count) {
            $articleFields += ''
        }
        $articleFields[$typeIndex] = 'article'
        $ArticleRow = $articleFields -join "`t"
    }

    $found = $false
    $updated = foreach ($line in $lines) {
        $fields = @($line -split "`t")
        if ($fields.Count -ge 2 -and $fields[1] -eq $ArticleSlug) {
            $found = $true
            $ArticleRow
        }
        else {
            $line
        }
    }
    if (-not $found) {
        $updated = @($updated) + $ArticleRow
    }

    Write-LinesPreservingNewline -Path $Path -Lines @($updated)
}

function Set-IdStatus {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$ArticleSlug,
        [Parameter(Mandatory)] [string]$Status
    )

    $changed = $false
    $lines = foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $fields = @($line -split "`t")
        if ($fields.Count -ge 2 -and $fields[1] -eq $ArticleSlug) {
            $fields[0] = $Status
            $changed = $true
            $fields -join "`t"
        }
        else {
            $line
        }
    }
    if (-not $changed) {
        throw "Could not update status for '$ArticleSlug' in $Path."
    }
    Write-LinesPreservingNewline -Path $Path -Lines @($lines)
}

function Merge-UrlRow {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$ArticleSlug,
        [Parameter(Mandatory)] [bool]$HasCover
    )

    $lines = @([System.IO.File]::ReadAllLines($Path))
    if ($lines.Count -eq 0) {
        throw "URL file is empty: $Path"
    }

    $kept = @($lines[0])
    foreach ($line in $lines | Select-Object -Skip 1) {
        $fields = @($line -split "`t")
        if ($fields.Count -gt 0) {
            $normalized = $fields[0].Replace('\', '/').TrimEnd('/')
            if ($normalized -eq $ArticleSlug) {
                continue
            }
        }
        $kept += $line
    }

    if ($HasCover) {
        $kept += "$ArticleSlug/`tindex`tjpg"
    }
    Write-LinesPreservingNewline -Path $Path -Lines $kept
}

function Add-SitemapUrl {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Url
    )

    $uri = [Uri]$Url
    $canonicalUrl = $uri.GetLeftPart([System.UriPartial]::Path).TrimEnd('/')
    $raw = [System.IO.File]::ReadAllText($Path)
    $newline = if ($raw.Contains("`r`n")) { "`r`n" } else { "`n" }
    $slugPattern = '<loc>https?://' +
        [regex]::Escape($uri.Authority) +
        [regex]::Escape($uri.AbsolutePath.TrimEnd('/')) +
        '/?</loc>'
    if ($raw -match $slugPattern) {
        $updated = [regex]::Replace(
            $raw,
            $slugPattern,
            "<loc>$canonicalUrl</loc>",
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
        $updated = [regex]::Replace(
            $updated,
            '\s*</urlset>',
            "${newline}${newline}</urlset>"
        )
        if ($updated -cne $raw) {
            Write-Utf8Text -Path $Path -Text $updated
        }
        return
    }

    $entry = "<url>${newline}`t<loc>$canonicalUrl</loc>${newline}</url>${newline}${newline}"
    if (-not $raw.Contains('</urlset>')) {
        throw "Invalid sitemap; missing </urlset>: $Path"
    }
    $raw = $raw.Replace('</urlset>', $entry + '</urlset>')
    Write-Utf8Text -Path $Path -Text $raw
}

function Update-FirebaseConfig {
    param(
        [Parameter(Mandatory)] [string]$Python,
        [Parameter(Mandatory)] [string]$PythonWorkingDirectory,
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$ArticleSlug,
        [Parameter(Mandatory)] [bool]$HasCover
    )

    $code = @'
import json
import sys

path, slug, has_cover_text = sys.argv[1:4]
has_cover = has_cover_text == "1"

with open(path, encoding="utf-8") as source:
    data = json.load(source)

hosting = data.setdefault("hosting", {})
redirects = hosting.setdefault("redirects", [])
rewrites = hosting.setdefault("rewrites", [])

short_source = "/" + slug.rsplit("/", 1)[-1]
destination = "/" + slug
existing_short = next((item for item in redirects if item.get("source") == short_source), None)
if existing_short and existing_short.get("destination") != destination:
    raise RuntimeError(
        f"Shortcut {short_source!r} already points to {existing_short.get('destination')!r}"
    )
if not existing_short:
    redirects.append({"source": short_source, "destination": destination, "type": 301})

required = [
    {"source": f"/{slug}.json", "destination": f"/{slug}/index.json"},
]
if has_cover:
    required.append({"source": f"/{slug}.jpg", "destination": f"/{slug}/index.jpg"})

for wanted in required:
    existing = next((item for item in rewrites if item.get("source") == wanted["source"]), None)
    if existing and existing.get("destination") != wanted["destination"]:
        raise RuntimeError(
            f"Rewrite {wanted['source']!r} already points to {existing.get('destination')!r}"
        )
    if not existing:
        rewrites.append(wanted)

with open(path, "w", encoding="utf-8", newline="\n") as target:
    json.dump(data, target, ensure_ascii=False, indent=2)
    target.write("\n")
'@

    Invoke-Native -FilePath $Python `
        -ArgumentList @('-c', $code, $Path, $ArticleSlug, $(if ($HasCover) { '1' } else { '0' })) `
        -WorkingDirectory $PythonWorkingDirectory
}

function Wait-Docker {
    param([int]$TimeoutSeconds = 120)

    & docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -eq 0) {
        return
    }

    $dockerDesktop = 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $dockerDesktop)) {
        throw 'Docker is not running and Docker Desktop was not found.'
    }

    Write-Step 'Starting Docker Desktop'
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        & docker info --format '{{.ServerVersion}}' *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "Docker did not become ready within $TimeoutSeconds seconds."
}

function Remove-WorkDirectory {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$AllowedParent
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $parent = (Resolve-Path -LiteralPath $AllowedParent).Path
    if (-not $resolved.StartsWith($parent + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove work directory outside '$parent': $resolved"
    }
    if ((Split-Path -Leaf $resolved) -notlike '.ncms-publish-*') {
        throw "Refusing unexpected work directory: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$websiteRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $projectRoot)).Path
$siteProject = Join-Path $websiteRoot 'site\project'
$publicRepo = Join-Path $projectRoot 'build'
$composeFile = Join-Path $projectRoot 'compose-dev.yaml'
$python = Join-Path $NcmsProject '.venv\Scripts\python.exe'
$php = 'C:\programs\php\bin\php.exe'

foreach ($required in @(
    $siteProject,
    $publicRepo,
    $composeFile,
    $NcmsProject,
    $python,
    (Join-Path $NcmsProject 'ncms_fetch.py')
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path not found: $required"
    }
}

if ($Slug) {
    Assert-SafeSlug $Slug
}
$BaseUrl = $BaseUrl.TrimEnd('/')

$workName = '.ncms-publish-' + [Guid]::NewGuid().ToString('N')
$workRoot = Join-Path $websiteRoot $workName
$renderRoot = Join-Path $workRoot 'render'
$stageProject = Join-Path $workRoot 'site'
$realIdPath = Join-Path $siteProject 'Config\ID.tsv'
$realUrlPath = Join-Path $siteProject 'Config\Url.tsv'
$realSitemapPath = Join-Path $siteProject 'root\Site\sitemap.xml'
$realIdBackup = Join-Path $workRoot 'real-ID.tsv.backup'
$realIdTemporarilyFiltered = $false
$containerStarted = $false
$webSiteWasRunning = $false
$completed = $false

New-Item -ItemType Directory -Path $renderRoot -Force | Out-Null

try {
    Write-Step 'Fetching and rendering one Notion article'
    $renderCode = @'
import json
import os
import sys

import ncms_fetch as ncms

output_dir = os.path.abspath(sys.argv[1])
requested = sys.argv[2].strip() if len(sys.argv) > 2 else ""

def page_slug(page):
    title = page.get("properties", {}).get("Id", {}).get("title", [])
    return title[0].get("plain_text", "") if title else ""

pages = ncms.fetch_database_content(ncms.database_id, status="publish")
candidates = [{"slug": page_slug(page), "page_id": page["id"]} for page in pages]

if requested:
    selected = [page for page in pages if page_slug(page) == requested]
    if len(selected) != 1:
        raise RuntimeError(
            f"Expected one publish page for {requested!r}; found {len(selected)}. "
            f"Queued: {[item['slug'] for item in candidates]}"
        )
else:
    if len(pages) != 1:
        raise RuntimeError(
            "Expected exactly one page with Status=publish. "
            f"Found {len(pages)}: {[item['slug'] for item in candidates]}. "
            "Pass -Slug to select one explicitly."
        )
    selected = pages

ncms.output_dir = output_dir
ncms.project_dir = output_dir
ncms.git_push_enabled = False
ncms.notion_update_enabled = False

articles = ncms.extract_fields(selected, included_statuses=("publish",))
if len(articles) != 1:
    raise RuntimeError(f"Expected one extracted article; got {len(articles)}")
ncms.transform_to_php(articles)

article = articles[0]
print("NCMS_RESULT=" + json.dumps({
    "slug": article["slug"],
    "title": article["title"],
    "description": article["description"],
    "page_id": article["id"],
    "queued_slugs": [item["slug"] for item in candidates],
}, ensure_ascii=False))
'@

    Push-Location $NcmsProject
    try {
        $renderOutput = @(& $python -c $renderCode $renderRoot $(if ($Slug) { $Slug } else { '' }) 2>&1)
        $renderExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    $renderOutput | ForEach-Object { Write-Host "$_" }
    if ($renderExitCode -ne 0) {
        throw "Notion render failed with exit code $renderExitCode."
    }

    $marker = $renderOutput |
        ForEach-Object { "$_" } |
        Where-Object { $_.StartsWith('NCMS_RESULT=') } |
        Select-Object -Last 1
    if (-not $marker) {
        throw 'The NCMS renderer did not return article metadata.'
    }
    $article = $marker.Substring('NCMS_RESULT='.Length) | ConvertFrom-Json
    $targetSlug = [string]$article.slug
    Assert-SafeSlug $targetSlug
    $slugPath = $targetSlug.Replace('/', '\')
    $componentRelative = "HTML\Component\$slugPath\index.php"
    $renderComponent = Join-Path $renderRoot $componentRelative
    if (-not (Test-Path -LiteralPath $renderComponent)) {
        throw "Rendered PHP component not found: $renderComponent"
    }

    if (Test-Path -LiteralPath $php) {
        Invoke-Native -FilePath $php -ArgumentList @('-l', $renderComponent) -WorkingDirectory $projectRoot
    }

    Write-Host "Selected: $targetSlug ($($article.title))" -ForegroundColor Green
    if ($DryRun) {
        Write-Host 'Dry run passed. No source, git, deployment, or Notion status changes were made.' -ForegroundColor Green
        $completed = $true
        return
    }

    $publicStatus = @(Invoke-Native -FilePath 'git' -ArgumentList @('-C', $publicRepo, 'status', '--porcelain') -WorkingDirectory $projectRoot -Capture)
    if ($publicStatus.Count -gt 0 -and ($publicStatus -join '').Trim()) {
        throw "Public repository is not clean:`n$($publicStatus -join "`n")"
    }

    Write-Step 'Updating the local generated source'
    $realComponent = Join-Path $siteProject ("root\" + $componentRelative)
    New-Item -ItemType Directory -Path (Split-Path -Parent $realComponent) -Force | Out-Null
    Copy-Item -LiteralPath $renderComponent -Destination $realComponent -Force

    $coverSource = Join-Path $siteProject ("root\Resource\" + $slugPath + "\index.jpg")
    $componentText = [System.IO.File]::ReadAllText($realComponent)
    if ((Test-Path -LiteralPath $coverSource) -and -not $componentText.Contains('Component_cover.php')) {
        $coverAlt = ([string]$article.title).Replace('\', '\\').Replace("'", "\'")
        $coverMarkup = "<?php `$alt='$coverAlt'; require('../HTML/Fragment/Component_cover.php') ?>"
        Write-Utf8Text -Path $realComponent -Text ($coverMarkup + "`n`n" + $componentText)
    }

    $renderIdPath = Join-Path $renderRoot 'Config\ID.tsv'
    $articleRow = [System.IO.File]::ReadAllLines($renderIdPath) |
        Where-Object {
            $fields = @($_ -split "`t")
            $fields.Count -ge 2 -and $fields[1] -eq $targetSlug
        } |
        Select-Object -First 1
    if (-not $articleRow) {
        throw "No ID row was generated for '$targetSlug'."
    }
    Merge-IdRow -Path $realIdPath -ArticleSlug $targetSlug -ArticleRow $articleRow

    $hasCover = [System.IO.File]::ReadAllText($realComponent).Contains('Component_cover.php')
    Merge-UrlRow -Path $realUrlPath -ArticleSlug $targetSlug -HasCover $hasCover
    Add-SitemapUrl -Path $realSitemapPath -Url "$BaseUrl/$targetSlug"

    Write-Step 'Creating the isolated Cutie build'
    $exclude = @(
        (Join-Path $siteProject '.git'),
        (Join-Path $siteProject 'public'),
        (Join-Path $siteProject 'interim'),
        (Join-Path $siteProject 'HTML'),
        (Join-Path $siteProject 'Site')
    )
    $roboArgs = @($siteProject, $stageProject, '/E', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/XD') + $exclude
    & robocopy @roboArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE."
    }

    $stageIdPath = Join-Path $stageProject 'Config\ID.tsv'
    $stageIdLines = @([System.IO.File]::ReadAllLines($stageIdPath))
    $stageArticleRow = $stageIdLines |
        Where-Object {
            $fields = @($_ -split "`t")
            $fields.Count -ge 2 -and $fields[1] -eq $targetSlug
        } |
        Select-Object -First 1
    Write-Utf8Text -Path $stageIdPath -Text ($stageIdLines[0] + "`n" + $stageArticleRow + "`n")

    $stageUrlPath = Join-Path $stageProject 'Config\Url.tsv'
    $stageUrlLines = @([System.IO.File]::ReadAllLines($stageUrlPath))
    $stageUrlText = $stageUrlLines[0] + "`n"
    if ($hasCover) {
        $stageUrlText += "$targetSlug/`tindex`tjpg`n"
    }
    Write-Utf8Text -Path $stageUrlPath -Text $stageUrlText

    Wait-Docker
    $runningServices = @(
        & docker compose -f $composeFile -p ujnotes ps --status running --services 2>$null
    )
    $webSiteWasRunning = $runningServices -contains 'web-site'
    Write-Step 'Starting the local Cutie renderer'
    Invoke-Native -FilePath 'docker' `
        -ArgumentList @('compose', '-f', $composeFile, '-p', 'ujnotes', 'up', '-d', 'web-site') `
        -WorkingDirectory $projectRoot
    $containerStarted = $true

    Invoke-Native -FilePath 'docker' `
        -ArgumentList @(
            'compose', '-f', $composeFile, '-p', 'ujnotes', 'exec', '-T', 'web-site',
            'sh', '-lc',
            'command -v wget >/dev/null 2>&1 && command -v minify >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends wget minify)'
        ) `
        -WorkingDirectory $projectRoot

    Copy-Item -LiteralPath $realIdPath -Destination $realIdBackup
    $realLines = @([System.IO.File]::ReadAllLines($realIdPath))
    $filteredRealLines = foreach ($line in $realLines) {
        $fields = @($line -split "`t")
        if (
            $fields.Count -ge 2 -and
            $fields[0] -eq 'publish' -and
            $fields[1] -ne $targetSlug
        ) {
            continue
        }
        $line
    }
    Write-Utf8Text -Path $realIdPath -Text (($filteredRealLines -join "`n") + "`n")
    $realIdTemporarilyFiltered = $true

    $containerStage = "/app/$workName/site"
    try {
        Write-Step 'Rendering the requested route only'
        Invoke-Native -FilePath 'docker' `
            -ArgumentList @(
                'compose', '-f', $composeFile, '-p', 'ujnotes', 'exec', '-T', 'web-site',
                '/app/tiggu/build.sh', $containerStage
            ) `
            -WorkingDirectory $projectRoot
    }
    finally {
        Copy-Item -LiteralPath $realIdBackup -Destination $realIdPath -Force
        $realIdTemporarilyFiltered = $false
    }

    $stagePublicTarget = Join-Path $stageProject "public\$slugPath"
    $stageHtml = Join-Path $stagePublicTarget 'index.html'
    $stageJson = Join-Path $stagePublicTarget 'index.json'
    foreach ($artifact in @($stageHtml, $stageJson)) {
        if (-not (Test-Path -LiteralPath $artifact) -or (Get-Item -LiteralPath $artifact).Length -eq 0) {
            throw "Required build artifact is missing or empty: $artifact"
        }
    }
    $builtJson = [System.IO.File]::ReadAllText($stageJson) | ConvertFrom-Json
    if ([string]$builtJson.desc -ne [string]$article.description) {
        throw 'Built JSON description does not match Notion.'
    }
    foreach ($queuedSlug in @($article.queued_slugs)) {
        if ($queuedSlug -and $queuedSlug -ne $targetSlug -and [string]$builtJson.content -like "*$queuedSlug*") {
            throw "Built article links to queued unpublished page '$queuedSlug'."
        }
    }

    Write-Step 'Updating the public repository'
    $publicTarget = Join-Path $publicRepo "public\$slugPath"
    New-Item -ItemType Directory -Path $publicTarget -Force | Out-Null
    Copy-Item -LiteralPath $stageHtml, $stageJson -Destination $publicTarget -Force

    $stageJpg = Join-Path $stagePublicTarget 'index.jpg'
    if ($hasCover -and (Test-Path -LiteralPath $stageJpg) -and (Get-Item -LiteralPath $stageJpg).Length -gt 0) {
        Copy-Item -LiteralPath $stageJpg -Destination $publicTarget -Force
    }

    $firebasePath = Join-Path $publicRepo 'firebase.json'
    Update-FirebaseConfig `
        -Python $python `
        -PythonWorkingDirectory $NcmsProject `
        -Path $firebasePath `
        -ArticleSlug $targetSlug `
        -HasCover $hasCover

    $sitemapPath = Join-Path $publicRepo 'public\sitemap.xml'
    Add-SitemapUrl -Path $sitemapPath -Url "$BaseUrl/$targetSlug"

    [void]([System.IO.File]::ReadAllText($firebasePath) | ConvertFrom-Json)
    [xml]([System.IO.File]::ReadAllText($sitemapPath)) | Out-Null

    $gitPaths = @(
        'firebase.json',
        'public/sitemap.xml',
        "public/$targetSlug/index.html",
        "public/$targetSlug/index.json"
    )
    if ($hasCover -and (Test-Path -LiteralPath (Join-Path $publicTarget 'index.jpg'))) {
        $gitPaths += "public/$targetSlug/index.jpg"
    }
    Invoke-Native -FilePath 'git' -ArgumentList (@('add', '--') + $gitPaths) -WorkingDirectory $publicRepo
    Invoke-Native -FilePath 'git' -ArgumentList @('diff', '--cached', '--check') -WorkingDirectory $publicRepo

    & git -C $publicRepo diff --cached --quiet
    $hasCommitChanges = $LASTEXITCODE -ne 0
    if ($hasCommitChanges) {
        $commitTitle = if ($article.title) { [string]$article.title } else { $targetSlug }
        Invoke-Native -FilePath 'git' `
            -ArgumentList @('commit', '-m', "Publish $commitTitle from Notion") `
            -WorkingDirectory $publicRepo
    }
    else {
        Write-Host 'No new public commit was needed; verifying the existing deployment.' -ForegroundColor Yellow
    }

    Write-Step 'Pushing the public site'
    Invoke-Native -FilePath 'git' -ArgumentList @('push', 'origin', 'main') -WorkingDirectory $publicRepo

    Write-Step 'Waiting for the deployed JSON to match'
    $localHash = (Get-FileHash -LiteralPath $stageJson -Algorithm SHA256).Hash
    $liveJsonPath = Join-Path $workRoot 'live.json'
    $liveUrl = "$BaseUrl/$targetSlug.json"
    $deadline = [DateTime]::UtcNow.AddSeconds($DeployTimeoutSeconds)
    $deployed = $false
    do {
        & curl.exe -4 -sS -L `
            --retry 2 --retry-all-errors --connect-timeout 10 --max-time 30 `
            -o $liveJsonPath $liveUrl
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $liveJsonPath)) {
            $liveHash = (Get-FileHash -LiteralPath $liveJsonPath -Algorithm SHA256).Hash
            if ($liveHash -eq $localHash) {
                $deployed = $true
                break
            }
        }
        Start-Sleep -Seconds 5
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $deployed) {
        throw "Deployment did not match $liveUrl within $DeployTimeoutSeconds seconds. Notion was left as publish."
    }

    Write-Step 'Marking the Notion page as published'
    $statusCode = @'
import sys
import ncms_fetch as ncms

page_id, expected_slug = sys.argv[1:3]
page = ncms.notion.pages.retrieve(page_id=page_id)
title = page.get("properties", {}).get("Id", {}).get("title", [])
actual_slug = title[0].get("plain_text", "") if title else ""
if actual_slug != expected_slug:
    raise RuntimeError(f"Notion page slug changed: {actual_slug!r}")

status = page["properties"]["Status"].get("select")
status_name = status.get("name") if status else ""
if status_name not in {"publish", "published"}:
    raise RuntimeError(f"Refusing to update unexpected status {status_name!r}")
if status_name != "published":
    ncms.notion.pages.update(
        page_id=page_id,
        properties={"Status": {"select": {"name": "published"}}},
    )

check = ncms.notion.pages.retrieve(page_id=page_id)
final_status = check["properties"]["Status"]["select"]["name"]
if final_status != "published":
    raise RuntimeError(f"Unexpected final status: {final_status!r}")
print(f"{expected_slug} status={final_status}")
'@
    Invoke-Native -FilePath $python `
        -ArgumentList @('-c', $statusCode, [string]$article.page_id, $targetSlug) `
        -WorkingDirectory $NcmsProject
    Set-IdStatus -Path $realIdPath -ArticleSlug $targetSlug -Status 'published'

    $finalStatus = @(Invoke-Native -FilePath 'git' -ArgumentList @('status', '--porcelain') -WorkingDirectory $publicRepo -Capture)
    if ($finalStatus.Count -gt 0 -and ($finalStatus -join '').Trim()) {
        throw "Public repository is unexpectedly dirty after push:`n$($finalStatus -join "`n")"
    }

    $completed = $true
    Write-Host "`nPublished: $BaseUrl/$targetSlug" -ForegroundColor Green
}
finally {
    if ($realIdTemporarilyFiltered -and (Test-Path -LiteralPath $realIdBackup)) {
        Copy-Item -LiteralPath $realIdBackup -Destination $realIdPath -Force
    }

    if ($containerStarted -and -not $webSiteWasRunning -and -not $KeepBuildContainer) {
        try {
            Invoke-Native -FilePath 'docker' `
                -ArgumentList @('compose', '-f', $composeFile, '-p', 'ujnotes', 'stop', 'web-site') `
                -WorkingDirectory $projectRoot
        }
        catch {
            Write-Warning "Could not stop the local build container: $($_.Exception.Message)"
        }
    }

    try {
        Remove-WorkDirectory -Path $workRoot -AllowedParent $websiteRoot
    }
    catch {
        Write-Warning "Could not remove temporary work directory '$workRoot': $($_.Exception.Message)"
    }

    if (-not $completed) {
        Write-Warning 'Publishing did not complete. Notion is only marked published after a matching live deployment.'
    }
}

