param(
    [string]$SiteProject = 'D:\Ujnotes\Website\site\project',
    [string]$NcmsProject = 'D:\Ujnotes\Website\ncms'
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$python = Join-Path $NcmsProject '.venv\Scripts\python.exe'
$fetch = Join-Path $NcmsProject 'ncms_fetch.py'
& $python $fetch sync-home --site-project $SiteProject
if ($LASTEXITCODE -ne 0) {
    throw "NCMS sync-home failed with exit code $LASTEXITCODE"
}

$components = @(
    @{ Path = 'Root\HTML\Component\Root.php'; Include = "<?php require(__DIR__.'/../Fragment/Home_ajax_styles.php'); ?>" },
    @{ Path = 'Root\HTML\Component\hi\Root\index.php'; Include = "<?php require(__DIR__.'/../../../Fragment/Home_ajax_styles.php'); ?>" }
)
foreach ($component in $components) {
    $path = Join-Path $SiteProject $component.Path
    $body = [System.IO.File]::ReadAllText($path)
    if ($body.Contains('Home_ajax_styles.php')) { continue }
    [System.IO.File]::WriteAllText(
        $path,
        $component.Include + "`n" + $body,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Added Home AJAX styles to $path"
}
