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
.\publish-notion.ps1 -Slug hi/world/philosophy/hindu

Selects the canonical Notion page for a language-prefixed public slug and
publishes that translation.

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

    [switch]$KeepBuildContainer,

    [switch]$AllowQueuedLinks,

    [switch]$Resume
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


function Read-Utf8Text {
    param(
        [Parameter(Mandatory)] [string]$Path
    )

    [System.IO.File]::ReadAllText(
        $Path,
        [System.Text.UTF8Encoding]::new($false)
    )
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

. (Join-Path $PSScriptRoot 'Repair-GitTextFiles.ps1')
. (Join-Path $PSScriptRoot 'PublishRunner.ps1')

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
        if ($fields.Count -ge 3) {
            $normalizedPath = $fields[0].Replace('\', '/').Trim('/')
            $name = $fields[1].Trim('/')
            $extension = $fields[2].Trim().ToLowerInvariant()
            $rowSlug = if ($name -eq 'index') {
                $normalizedPath
            }
            elseif ($normalizedPath) {
                "$normalizedPath/$name"
            }
            else {
                $name
            }
            if ($extension -eq 'jpg' -and $rowSlug -eq $ArticleSlug) {
                continue
            }
        }
        $kept += $line
    }

    if ($HasCover) {
        $slash = $ArticleSlug.LastIndexOf('/')
        if ($slash -ge 0) {
            $parentPath = $ArticleSlug.Substring(0, $slash + 1)
            $coverName = $ArticleSlug.Substring($slash + 1)
        }
        else {
            $parentPath = ''
            $coverName = $ArticleSlug
        }
        $kept += "$parentPath`t$coverName`tjpg"
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
        [Parameter(Mandatory)] [bool]$HasCover,
        [bool]$HasSvg = $false
    )

    $code = @'
import json
import sys

path, slug, has_cover_text, has_svg_text = sys.argv[1:5]
has_cover = has_cover_text == "1"
has_svg = has_svg_text == "1"

with open(path, encoding="utf-8") as source:
    data = json.load(source)

hosting = data.setdefault("hosting", {})
redirects = hosting.setdefault("redirects", [])
rewrites = hosting.setdefault("rewrites", [])

short_source = "/" + slug.rsplit("/", 1)[-1]
destination = "/" + slug
existing_short = next((item for item in redirects if item.get("source") == short_source), None)
if existing_short and existing_short.get("destination") != destination:
    print(
        f"WARNING: Skipping shortcut {short_source!r}; already points to {existing_short.get('destination')!r}",
        file=sys.stderr,
    )
elif not existing_short:
    redirects.append({"source": short_source, "destination": destination, "type": 301})

required = [
    {"source": f"/{slug}.json", "destination": f"/{slug}/index.json"},
]
if has_cover:
    required.append({"source": f"/{slug}.jpg", "destination": f"/{slug}/index.jpg"})
if has_svg:
    required.append({"source": f"/{slug}.svg", "destination": f"/{slug}/index.svg"})

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
        -ArgumentList @('-X', 'utf8', '-c', $code, $Path, $ArticleSlug, $(if ($HasCover) { '1' } else { '0' }), $(if ($HasSvg) { '1' } else { '0' })) `
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

function Import-PipelineStateModule {
    $path = 'H:\Website\console\PipelineState.ps1'
    if (Test-Path -LiteralPath $path) {
        return $path
    }
    return $null
}

function New-PublishResumeSnapshot {
    [ordered]@{
        workName               = $workName
        workRoot               = $workRoot
        renderRoot             = $renderRoot
        stageProject           = $stageProject
        targetSlug             = $targetSlug
        slugPath               = $slugPath
        hasCover               = [bool]$hasCover
        alreadyPublishedSlugs  = @($alreadyPublishedSlugs)
        article                = $article
        variants               = @($variants)
        builtVariants          = @($builtVariants)
        ncmsProject            = $NcmsProject
        baseUrl                = $BaseUrl
        deployTimeoutSeconds   = $DeployTimeoutSeconds
        keepBuildContainer     = [bool]$KeepBuildContainer
        allowQueuedLinks       = [bool]$AllowQueuedLinks
        slugArgument           = [string]$Slug
        dryRun                 = [bool]$DryRun
    }
}

function Enter-Stage {
    param([Parameter(Mandatory)] [string]$Id)
    if (Get-Command -Name Enter-PublishStage -ErrorAction SilentlyContinue) {
        return [bool](Enter-PublishStage -Id $Id)
    }
    Write-Step $Id
    return $true
}

function Complete-Stage {
    param([Parameter(Mandatory)] [string]$Id)
    if (Get-Command -Name Complete-PublishStage -ErrorAction SilentlyContinue) {
        Complete-PublishStage -Id $Id -Snapshot (New-PublishResumeSnapshot)
    }
}

$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$websiteRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $projectRoot)).Path
$siteProject = Join-Path $websiteRoot 'site\project'
$publicRepo = Join-Path $projectRoot 'build'
$composeFile = Join-Path $projectRoot 'compose-dev.yaml'
$python = Join-Path $NcmsProject '.venv\Scripts\python.exe'
$php = 'C:\programs\php\bin\php.exe'
$publishRunner = Get-UjnotesPublishRunner

foreach ($required in @(
    $siteProject,
    $publicRepo,
    $NcmsProject,
    $python,
    (Join-Path $NcmsProject 'ncms_fetch.py')
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required path not found: $required"
    }
}
if ($publishRunner -eq 'docker' -and -not (Test-Path -LiteralPath $composeFile)) {
    throw "Required path not found: $composeFile"
}

if ($Slug) {
    Assert-SafeSlug $Slug
}
$BaseUrl = $BaseUrl.TrimEnd('/')

# Dot-source at script scope. Sourcing inside a function would define
# Get-PublishCheckpoint (and the rest) only for that function call.
$pipelineStatePath = Import-PipelineStateModule
$pipelineLoaded = $false
if ($pipelineStatePath) {
    . $pipelineStatePath
    $pipelineLoaded = $true
}
$article = $null
$variants = @()
$builtVariants = @()
$targetSlug = ''
$slugPath = ''
$hasCover = $false
$alreadyPublishedSlugs = @()
$keepWorkRoot = $false
$realIdPath = Join-Path $siteProject 'Config\ID.tsv'
$realUrlPath = Join-Path $siteProject 'Config\Url.tsv'
$realSitemapPath = Join-Path $siteProject 'root\Site\sitemap.xml'
$containerStarted = $false
$webSiteWasRunning = $false
$completed = $false
$realIdTemporarilyFiltered = $false
$realIdBackup = $null

if ($Resume) {
    if (-not $pipelineLoaded) {
        throw 'Resume requires H:\Website\console\PipelineState.ps1.'
    }
    $checkpoint = Get-PublishCheckpoint
    if ($Slug -and $checkpoint.slug -and $Slug -ne [string]$checkpoint.slug) {
        throw "Resume checkpoint is for '$($checkpoint.slug)', not '$Slug'."
    }
    $workName = [string]$checkpoint.workName
    $workRoot = [string]$checkpoint.workRoot
    $renderRoot = [string]$checkpoint.renderRoot
    $stageProject = [string]$checkpoint.stageProject
    $targetSlug = [string]$checkpoint.targetSlug
    $slugPath = [string]$checkpoint.slugPath
    $hasCover = [bool]$checkpoint.hasCover
    $alreadyPublishedSlugs = @($checkpoint.alreadyPublishedSlugs)
    $article = $checkpoint.article
    $variants = @($checkpoint.variants)
    $builtVariants = @($checkpoint.builtVariants)
    if ($checkpoint.dryRun) {
        $DryRun = $true
    }
    if (
        $checkpoint.PSObject.Properties.Name -contains 'allowQueuedLinks' -and
        $checkpoint.allowQueuedLinks
    ) {
        $AllowQueuedLinks = $true
    }
    if ($checkpoint.slugArgument -and -not $Slug) {
        $Slug = [string]$checkpoint.slugArgument
    }
    $realIdBackup = Join-Path $workRoot 'real-ID.tsv.backup'
    if (-not (Test-Path -LiteralPath $workRoot)) {
        throw "Resume work directory is missing: $workRoot"
    }
    Resume-PublishPipeline -Checkpoint $checkpoint
    $failedId = [string]$checkpoint.failedStage
    $stageIds = @((Get-PublishStageCatalog).Id)
    if (
        $publishRunner -eq 'docker' -and
        $stageIds.IndexOf($failedId) -ge $stageIds.IndexOf('start-renderer')
    ) {
        Wait-Docker
        $runningServices = @(
            & docker compose -f $composeFile -p ujnotes ps --status running --services 2>$null
        )
        $webSiteWasRunning = $runningServices -contains 'web-site'
        Invoke-Native -FilePath 'docker' `
            -ArgumentList @('compose', '-f', $composeFile, '-p', 'ujnotes', 'up', '-d', 'web-site') `
            -WorkingDirectory $projectRoot
        $containerStarted = $true
    }
}
else {
    if ($pipelineLoaded -and (Test-PublishCheckpoint)) {
        $previous = Get-PublishCheckpoint
        if ($previous.workRoot) {
            try {
                Remove-WorkDirectory -Path ([string]$previous.workRoot) -AllowedParent $websiteRoot
            }
            catch {
                Write-Warning $_.Exception.Message
            }
        }
    }
    $workName = '.ncms-publish-' + [Guid]::NewGuid().ToString('N')
    $workRoot = Join-Path $websiteRoot $workName
    $renderRoot = Join-Path $workRoot 'render'
    $stageProject = Join-Path $workRoot 'site'
    $realIdBackup = Join-Path $workRoot 'real-ID.tsv.backup'
    New-Item -ItemType Directory -Path $renderRoot -Force | Out-Null
    $taskName = if ($Slug) { 'PublishArticle' } else { 'PublishQueued' }
    if ($pipelineLoaded) {
        Initialize-PublishPipeline -Task $taskName -Slug $Slug -DryRun:$DryRun
    }
}

try {
    if (Enter-Stage 'fetch') {
    Write-Step 'Fetching and rendering one Notion article'
    $renderCode = @'
import json
import os
import sys

import ncms_fetch as ncms

output_dir = os.path.abspath(sys.argv[1])
requested = sys.argv[2].strip() if len(sys.argv) > 2 else ""

pages = ncms.fetch_database_content(ncms.database_id, status="publish")
selected, candidates, requested_language = ncms.select_publish_page(
    pages, requested or None
)

ncms.output_dir = output_dir
ncms.project_dir = output_dir
ncms.git_push_enabled = False
ncms.notion_update_enabled = False

articles = ncms.extract_fields([selected], included_statuses=("publish",))
if not articles:
    raise RuntimeError("Expected at least one extracted article")
base_articles = [
    article for article in articles if article.get("language", "en") == "en"
]
if len(base_articles) != 1:
    raise RuntimeError(f"Expected one English base article; got {len(base_articles)}")
if requested_language:
    requested_articles = [
        item
        for item in articles
        if item.get("language", "en") == requested_language
    ]
    if not requested_articles:
        raise RuntimeError(
            f"No {requested_language!r} translation for {base_articles[0]['slug']!r}"
        )
ncms.transform_to_php(articles)

article = requested_articles[0] if requested_language else base_articles[0]
variants = []
for item in articles:
    language = item.get("language", "en")
    component_parts = ["HTML", "Component"]
    if language != "en":
        component_parts.append(language)
    component_parts.extend(item["slug"].split("/"))
    component_parts.append("index.php")
    variants.append({
        "slug": item["slug"],
        "title": item["title"],
        "description": item["description"],
        "language": language,
        "component": "/".join(component_parts),
    })
result = {
    "slug": base_articles[0]["slug"],
    "title": article["title"],
    "description": article["description"],
    "page_id": base_articles[0]["id"],
    "language": article.get("language", "en"),
    "variants": variants,
    "queued_slugs": [item["slug"] for item in candidates],
}
if requested_language:
    result["requested_language"] = requested_language
print("NCMS_RESULT=" + json.dumps(result, ensure_ascii=True))
'@

    Push-Location $NcmsProject
    try {
        $renderOutput = @(& $python -X utf8 -c $renderCode $renderRoot $(if ($Slug) { $Slug } else { '' }) 2>&1)
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
    $variants = @($article.variants)
    foreach ($variant in $variants) {
        $variantComponentRelative = ([string]$variant.component).Replace('/', '\')
        $renderVariantComponent = Join-Path $renderRoot $variantComponentRelative
        if (-not (Test-Path -LiteralPath $renderVariantComponent)) {
            throw "Rendered PHP component not found: $renderVariantComponent"
        }
        if (Test-Path -LiteralPath $php) {
            Invoke-Native -FilePath $php -ArgumentList @('-l', $renderVariantComponent) -WorkingDirectory $projectRoot
        }
    }

    Write-Host "Selected: $targetSlug ($($article.title))" -ForegroundColor Green
    if (Get-Command -Name Set-PublishPipelineSlug -ErrorAction SilentlyContinue) {
        Set-PublishPipelineSlug -Slug $targetSlug
    }
    Complete-Stage 'fetch'
    if ($DryRun) {
        Write-Host 'Dry run passed. No source, git, deployment, or Notion status changes were made.' -ForegroundColor Green
        if (Get-Command -Name Skip-RemainingPublishStages -ErrorAction SilentlyContinue) {
            Skip-RemainingPublishStages
        }
        $completed = $true
        return
    }
    }

    if (Enter-Stage 'update-source') {
    $publicStatus = @(Invoke-Native -FilePath 'git' -ArgumentList @('-C', $publicRepo, 'status', '--porcelain') -WorkingDirectory $projectRoot -Capture)
    if ($publicStatus.Count -gt 0 -and ($publicStatus -join '').Trim()) {
        throw "Public repository is not clean:`n$($publicStatus -join "`n")"
    }

    $coverSource = Join-Path $siteProject ("root\Resource\" + $slugPath + "\index.jpg")
    $realComponent = $null
    foreach ($variant in $variants) {
        $variantComponentRelative = ([string]$variant.component).Replace('/', '\')
        $renderVariantComponent = Join-Path $renderRoot $variantComponentRelative
        $realVariantComponent = Join-Path $siteProject ("root\" + $variantComponentRelative)
        New-Item -ItemType Directory -Path (Split-Path -Parent $realVariantComponent) -Force | Out-Null
        Copy-Item -LiteralPath $renderVariantComponent -Destination $realVariantComponent -Force

        $componentText = Read-Utf8Text -Path $realVariantComponent
        if ((Test-Path -LiteralPath $coverSource) -and -not $componentText.Contains('Component_cover.php')) {
            $coverAlt = ([string]$variant.title).Replace('\', '\\').Replace("'", "\'")
            $coverMarkup = "<?php `$alt='$coverAlt'; require('../HTML/Fragment/Component_cover.php') ?>"
            Write-Utf8Text -Path $realVariantComponent -Text ($coverMarkup + "`n`n" + $componentText)
        }
        if ([string]$variant.language -eq 'en') {
            $realComponent = $realVariantComponent
        }
    }
    if (-not $realComponent) {
        throw "The render did not include the canonical English component for '$targetSlug'."
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
    $alreadyPublishedSlugs = @(
        [System.IO.File]::ReadAllLines($realIdPath) |
            ForEach-Object {
                $fields = @($_ -split "`t")
                if ($fields.Count -ge 2 -and $fields[0] -eq 'published') {
                    $fields[1]
                }
            }
    )
    Merge-IdRow -Path $realIdPath -ArticleSlug $targetSlug -ArticleRow $articleRow

    $hasCover = [System.IO.File]::ReadAllText($realComponent).Contains('Component_cover.php')
    Merge-UrlRow -Path $realUrlPath -ArticleSlug $targetSlug -HasCover $hasCover
    Add-SitemapUrl -Path $realSitemapPath -Url "$BaseUrl/$targetSlug"
    Complete-Stage 'update-source'
    }

    if (Enter-Stage 'create-stage') {
    $exclude = @(
        (Join-Path $siteProject '.git'),
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

    # A single-route build must also constrain every localized ID table. Leaving
    # ID_hi.tsv (or another ID_<lang>.tsv) unfiltered makes Tiggu rebuild the
    # entire translated site for every canonical article in a batch.
    Get-ChildItem -LiteralPath (Split-Path -Parent $stageIdPath) -File -Filter 'ID_*.tsv' |
        ForEach-Object {
            $localizedLines = @([System.IO.File]::ReadAllLines($_.FullName))
            if ($localizedLines.Count -eq 0) {
                return
            }
            $localizedArticleRows = @(
                $localizedLines |
                    Select-Object -Skip 1 |
                    Where-Object {
                        $fields = @($_ -split "`t")
                        $fields.Count -ge 2 -and $fields[1] -eq $targetSlug
                    }
            )
            $localizedText = $localizedLines[0] + "`n"
            if ($localizedArticleRows.Count -gt 0) {
                $localizedText += ($localizedArticleRows -join "`n") + "`n"
            }
            Write-Utf8Text -Path $_.FullName -Text $localizedText
        }

    $stageUrlPath = Join-Path $stageProject 'Config\Url.tsv'
    $stageUrlLines = @([System.IO.File]::ReadAllLines($stageUrlPath))
    $stageUrlText = $stageUrlLines[0] + "`n"
    if ($hasCover) {
        $coverSlash = $targetSlug.LastIndexOf('/')
        if ($coverSlash -ge 0) {
            $stageCoverPath = $targetSlug.Substring(0, $coverSlash + 1)
            $stageCoverName = $targetSlug.Substring($coverSlash + 1)
        }
        else {
            $stageCoverPath = ''
            $stageCoverName = $targetSlug
        }
        $stageUrlText += "$stageCoverPath`t$stageCoverName`tjpg`n"
    }
    Write-Utf8Text -Path $stageUrlPath -Text $stageUrlText
    Complete-Stage 'create-stage'
    }

    if (Enter-Stage 'start-renderer') {
    if ($publishRunner -eq 'docker') {
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
    }
    else {
        Write-Step 'Using the native Tiggu renderer'
        [void](Get-UjnotesGitBash)
        $nativeTiggu = Join-Path $websiteRoot 'tiggu\build.sh'
        if (-not (Test-Path -LiteralPath $nativeTiggu -PathType Leaf)) {
            throw "Native runner needs Tiggu at $nativeTiggu."
        }
    }
    Complete-Stage 'start-renderer'
    }

    if (Enter-Stage 'render-route') {
    if ($publishRunner -eq 'docker') {
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
    }

    $containerStage = "/app/$workName/site"
    try {
        Write-Step 'Rendering the requested route only'
        if ($publishRunner -eq 'docker') {
            Invoke-Native -FilePath 'docker' `
                -ArgumentList @(
                    'compose', '-f', $composeFile, '-p', 'ujnotes', 'exec', '-T', 'web-site',
                    '/app/tiggu/build.sh', $containerStage
                ) `
                -WorkingDirectory $projectRoot
        }
        else {
            Invoke-UjnotesNativeTiggu `
                -ProjectPath $stageProject `
                -WebsiteRoot $websiteRoot `
                -SkipScriptVersioning
        }
    }
    finally {
        if ($realIdTemporarilyFiltered) {
            Copy-Item -LiteralPath $realIdBackup -Destination $realIdPath -Force
            $realIdTemporarilyFiltered = $false
        }
    }

    $builtVariants = @()
    foreach ($variant in $variants) {
        $variantPublicSlug = if ([string]$variant.language -eq 'en') {
            $targetSlug
        }
        else {
            "$([string]$variant.language)/$targetSlug"
        }
        $variantPublicPath = $variantPublicSlug.Replace('/', '\')
        $stageVariantTarget = Join-Path $stageProject "public\$variantPublicPath"
        $stageVariantHtml = Join-Path $stageVariantTarget 'index.html'
        $stageVariantJson = Join-Path $stageVariantTarget 'index.json'
        foreach ($artifact in @($stageVariantHtml, $stageVariantJson)) {
            if (-not (Test-Path -LiteralPath $artifact) -or (Get-Item -LiteralPath $artifact).Length -eq 0) {
                throw "Required build artifact is missing or empty: $artifact"
            }
        }
        $builtJson = (Read-Utf8Text -Path $stageVariantJson) | ConvertFrom-Json
        if ([string]$builtJson.desc -ne [string]$variant.description) {
            throw "Built JSON description does not match Notion for '$variantPublicSlug'."
        }
        foreach ($queuedSlug in $(if ($AllowQueuedLinks) { @() } else { @($article.queued_slugs) })) {
            if (
                $queuedSlug -and
                $queuedSlug -ne $targetSlug -and
                $alreadyPublishedSlugs -notcontains $queuedSlug -and
                [string]$builtJson.content -like "*$queuedSlug*"
            ) {
                throw "Built article links to queued unpublished page '$queuedSlug'."
            }
        }
        $builtVariants += [pscustomobject]@{
            PublicSlug = $variantPublicSlug
            Html = $stageVariantHtml
            Json = $stageVariantJson
            Language = [string]$variant.language
        }
    }
    Complete-Stage 'render-route'
    }

    if (Enter-Stage 'update-public') {
    foreach ($builtVariant in $builtVariants) {
        $publicTarget = Join-Path $publicRepo ("public\" + $builtVariant.PublicSlug.Replace('/', '\'))
        New-Item -ItemType Directory -Path $publicTarget -Force | Out-Null
        Copy-Item -LiteralPath $builtVariant.Html, $builtVariant.Json -Destination $publicTarget -Force
    }

    $publicTarget = Join-Path $publicRepo "public\$slugPath"
    $stagePublicTarget = Join-Path $stageProject "public\$slugPath"
    $resourceRoot = Join-Path $siteProject ("root\Resource\" + $slugPath)
    $publishedAssets = @{}
    foreach ($extension in @('jpg', 'svg')) {
        $candidates = @(
            "$stagePublicTarget.$extension"
            (Join-Path $stagePublicTarget "index.$extension")
            "$resourceRoot.$extension"
            (Join-Path $resourceRoot "index.$extension")
        )
        $sourceAsset = @($candidates) |
            Where-Object { (Test-Path -LiteralPath $_) -and (Get-Item -LiteralPath $_).Length -gt 0 } |
            Select-Object -First 1
        if (-not [string]::IsNullOrWhiteSpace($sourceAsset)) {
            Copy-Item -LiteralPath $sourceAsset -Destination (Join-Path $publicTarget "index.$extension") -Force
            $publishedAssets[$extension] = $true
        }
    }
    $hasPublishedCover = $publishedAssets.ContainsKey('jpg')
    $hasPublishedSvg = $publishedAssets.ContainsKey('svg')

    $legacyParent = Split-Path -Parent $publicTarget
    $legacyStem = Split-Path -Leaf $publicTarget
    $legacyGitPaths = @()
    foreach ($extension in @('html', 'json', 'jpg', 'svg')) {
        $legacyPath = Join-Path $legacyParent "$legacyStem.$extension"
        if (Test-Path -LiteralPath $legacyPath) {
            Remove-Item -LiteralPath $legacyPath -Force
            $lastSlash = $targetSlug.LastIndexOf('/')
            $legacyPrefix = if ($lastSlash -ge 0) {
                $targetSlug.Substring(0, $lastSlash) + '/'
            }
            else {
                ''
            }
            $legacyGitPaths += "public/$legacyPrefix$legacyStem.$extension"
        }
    }

    $firebasePath = Join-Path $publicRepo 'firebase.json'
    Update-FirebaseConfig `
        -Python $python `
        -PythonWorkingDirectory $NcmsProject `
        -Path $firebasePath `
        -ArticleSlug $targetSlug `
        -HasCover $hasPublishedCover `
        -HasSvg $hasPublishedSvg

    $sitemapPath = Join-Path $publicRepo 'public\sitemap.xml'
    Add-SitemapUrl -Path $sitemapPath -Url "$BaseUrl/$targetSlug"

    [void]([System.IO.File]::ReadAllText($firebasePath) | ConvertFrom-Json)
    [xml]([System.IO.File]::ReadAllText($sitemapPath)) | Out-Null

    $gitPaths = @(
        'firebase.json',
        'public/sitemap.xml'
    )
    foreach ($builtVariant in $builtVariants) {
        $gitPaths += "public/$($builtVariant.PublicSlug)/index.html"
        $gitPaths += "public/$($builtVariant.PublicSlug)/index.json"
    }
    if ($hasPublishedCover -and (Test-Path -LiteralPath (Join-Path $publicTarget 'index.jpg'))) {
        $gitPaths += "public/$targetSlug/index.jpg"
    }
    if ($hasPublishedSvg -and (Test-Path -LiteralPath (Join-Path $publicTarget 'index.svg'))) {
        $gitPaths += "public/$targetSlug/index.svg"
    }
    $gitPaths += $legacyGitPaths
    foreach ($gitPath in $gitPaths) {
        Repair-GitTextPath -Path (Join-Path $publicRepo ($gitPath.Replace('/', '\')))
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
    Complete-Stage 'update-public'
    }

    if (Enter-Stage 'push-public') {
    Invoke-Native -FilePath 'git' -ArgumentList @('push', 'origin', 'main') -WorkingDirectory $publicRepo
    Complete-Stage 'push-public'
    }

    if (Enter-Stage 'verify-live') {
    foreach ($builtVariant in $builtVariants) {
        $deployedJsonPath = Join-Path $publicRepo ("public\" + $builtVariant.PublicSlug.Replace('/', '\') + "\index.json")
        $localHash = (Get-FileHash -LiteralPath $deployedJsonPath -Algorithm SHA256).Hash
        $liveJsonPath = Join-Path $workRoot ("live-" + $builtVariant.PublicSlug.Replace('/', '-') + '.json')
        $liveUrl = "$BaseUrl/$($builtVariant.PublicSlug).json"
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
    }
    Complete-Stage 'verify-live'
    }

    if (Enter-Stage 'mark-published') {
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
        -ArgumentList @('-X', 'utf8', '-c', $statusCode, [string]$article.page_id, $targetSlug) `
        -WorkingDirectory $NcmsProject
    Set-IdStatus -Path $realIdPath -ArticleSlug $targetSlug -Status 'published'

    $finalStatus = @(Invoke-Native -FilePath 'git' -ArgumentList @('status', '--porcelain') -WorkingDirectory $publicRepo -Capture)
    if ($finalStatus.Count -gt 0 -and ($finalStatus -join '').Trim()) {
        throw "Public repository is unexpectedly dirty after push:`n$($finalStatus -join "`n")"
    }

    $completed = $true
    Write-Host "`nPublished: $BaseUrl/$targetSlug" -ForegroundColor Green
    Complete-Stage 'mark-published'
    if (Get-Command -Name Complete-PublishPipeline -ErrorAction SilentlyContinue) {
        Complete-PublishPipeline -Summary "Published $BaseUrl/$targetSlug"
    }
    }
}
catch {
    $keepWorkRoot = $true
    if (Get-Command -Name Fail-PublishPipeline -ErrorAction SilentlyContinue) {
        Fail-PublishPipeline -ErrorRecord $_ -Snapshot (New-PublishResumeSnapshot)
    }
    throw
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

    if ($completed) {
        try {
            Remove-WorkDirectory -Path $workRoot -AllowedParent $websiteRoot
        }
        catch {
            Write-Warning "Could not remove temporary work directory '$workRoot': $($_.Exception.Message)"
        }
    }
    else {
        Write-Warning "Publishing did not complete. Work directory kept at '$workRoot' so Console can continue from the failed stage. Notion is only marked published after a matching live deployment."
    }
}
