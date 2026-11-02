$ErrorActionPreference = 'Stop'

# Read only the dependency collector, without executing the publisher's stages.
$tokens = $null
$parseErrors = $null
$publisher = Join-Path $PSScriptRoot '../publish-notion.ps1'
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $publisher, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$collector = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Get-FrontendAssetPaths'
}, $true)
. ([scriptblock]::Create($collector.Extent.Text))

$fixture = Join-Path ([IO.Path]::GetTempPath()) ('frontend-assets-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
try {
    $variants = @(@{ component = 'en.php' }, @{ component = 'hi.php' })
    $widget = '<section data-component="example" data-source="/resource/data/example.json" data-component-script="/resource/components/example.js" data-component-style="/resource/components/example.css"></section>'
    foreach ($variant in $variants) {
        [IO.File]::WriteAllText((Join-Path $fixture $variant.component), $widget)
    }
    $assets = @(Get-FrontendAssetPaths -RenderRoot $fixture -Variants $variants)
    $expected = @('resource/components/example.css', 'resource/components/example.js', 'resource/data/example.json', 'script.js')
    if (Compare-Object $expected $assets) { throw 'Widget dependencies must include the shared loader exactly once across translations.' }

    # These are the same route keys used by the isolated URL-table filter.
    $routes = @("`tscript`tjs", "resource/components/`texample`tjs", "resource/components/`texample`tcss", "resource/data/`texample`tjson")
    foreach ($row in $routes) {
        $fields = $row.Split("`t")
        $key = "$($fields[0])$($fields[1]).$($fields[2])"
        if ($assets -notcontains $key) { throw "Required bake route was dropped: $key" }
    }

    [IO.File]::WriteAllText((Join-Path $fixture 'en.php'), '<p>Ordinary article</p>')
    if (@(Get-FrontendAssetPaths -RenderRoot $fixture -Variants @($variants[0])).Count) {
        throw 'Ordinary articles must not trigger shared script deployment.'
    }
    [IO.File]::WriteAllText((Join-Path $fixture 'en.php'), '<section data-component="example" data-source="/resource/data/../private.json"></section>')
    $rejected = $false
    try { Get-FrontendAssetPaths -RenderRoot $fixture -Variants @($variants[0]) | Out-Null }
    catch { $rejected = $_.Exception.Message -eq 'Unsafe frontend asset path' }
    if (-not $rejected) { throw 'Unsafe asset traversal was accepted.' }
    Write-Host 'Frontend asset dependency checks passed.'
}
finally {
    # Delete only this explicitly created, uniquely named fixture's files.
    Get-ChildItem -LiteralPath $fixture -File | Remove-Item
    Remove-Item -LiteralPath $fixture
}
