Set-StrictMode -Version Latest

function Get-UjnotesPublishRunner {
    param([string]$ConfigPath = 'H:\Console\config.yaml')

    $runner = 'docker'
    if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
        foreach ($line in [System.IO.File]::ReadAllLines($ConfigPath)) {
            if ($line -match '^\s*runner:\s*(\S+)') {
                $runner = $Matches[1].Trim([char[]]@([char]39, [char]34)).ToLowerInvariant()
                break
            }
        }
    }
    if ($runner -notin @('docker', 'native')) {
        throw "Console runner must be docker or native, not '$runner'."
    }
    return $runner
}

function ConvertTo-UjnotesGitBashPath {
    param([Parameter(Mandatory)] [string]$Path)

    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full -match '^([A-Za-z]):\\(.*)$') {
        return '/' + $Matches[1].ToLowerInvariant() + '/' + ($Matches[2] -replace '\\', '/')
    }
    return ($full -replace '\\', '/')
}

function Get-UjnotesGitBash {
    $bash = 'C:\Program Files\Git\bin\bash.exe'
    if (-not (Test-Path -LiteralPath $bash -PathType Leaf)) {
        throw "Native runner needs Git bash at $bash."
    }
    return $bash
}

function Get-UjnotesNativeToolchain {
    param([Parameter(Mandatory)] [string]$WebsiteRoot)

    $toolsRoot = Join-Path $WebsiteRoot '.native-tools'
    $minify = Join-Path $toolsRoot 'minify\minify.exe'
    $closure = Join-Path $toolsRoot 'closure-compiler-v20250402.jar'
    $java = 'C:\Program Files\Android\Android Studio\jbr\bin\java.exe'
    foreach ($required in @($minify, $closure, $java)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Native publishing dependency is missing: $required. Run Install-NativePublishTools.ps1."
        }
    }
    return [pscustomobject]@{
        Minify = $minify
        Closure = $closure
        Java = $java
    }
}

function Invoke-UjnotesNativeTiggu {
    param(
        [Parameter(Mandatory)] [string]$ProjectPath,
        [Parameter(Mandatory)] [string]$WebsiteRoot,
        [switch]$SkipScriptVersioning
    )

    $bash = Get-UjnotesGitBash
    $tiggu = Join-Path $WebsiteRoot 'tiggu\build.sh'
    if (-not (Test-Path -LiteralPath $tiggu -PathType Leaf)) {
        throw "Native runner needs Tiggu at $tiggu."
    }
    if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
        throw "Native renderer project does not exist: $ProjectPath"
    }

    $tigguUnix = ConvertTo-UjnotesGitBashPath -Path $tiggu
    $projectUnix = ConvertTo-UjnotesGitBashPath -Path $ProjectPath
    $toolchain = Get-UjnotesNativeToolchain -WebsiteRoot $WebsiteRoot
    $minifyUnix = ConvertTo-UjnotesGitBashPath -Path $toolchain.Minify
    $closureUnix = ConvertTo-UjnotesGitBashPath -Path $toolchain.Closure
    $javaUnix = ConvertTo-UjnotesGitBashPath -Path $toolchain.Java
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    $pythonUnix = ConvertTo-UjnotesGitBashPath -Path $pythonPath
    $command = 'export PATH=/usr/bin:/bin:$PATH; ' +
        'export TIGGU_ORIGIN="http://127.0.0.1:8084"; ' +
        'export TIGGU_HOST_HEADER="ujnotes.local"; ' +
        $(if ($SkipScriptVersioning) { 'export TIGGU_SKIP_SCRIPT_VERSIONING=1; ' } else { '' }) +
        'export TIGGU_MINIFY="' + $minifyUnix + '"; ' +
        'export TIGGU_CLOSURE_JAR="' + $closureUnix + '"; ' +
        'export TIGGU_JAVA="' + $javaUnix + '"; ' +
        'export TIGGU_NATIVE_PYTHON="' + $pythonUnix + '"; ' +
        '"' + $tigguUnix + '" "' + $projectUnix + '"'
    Push-Location $WebsiteRoot
    try {
        & $bash --noprofile --norc -c $command
        if ($LASTEXITCODE -ne 0) {
            throw "Native Tiggu failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}
