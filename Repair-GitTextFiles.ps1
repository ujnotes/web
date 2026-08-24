# Normalizes text that Git will store: LF only, no trailing whitespace, no blank EOF.
# git diff --check treats both spaces-at-EOL and CR-at-EOL as trailing whitespace.

function Test-GitTextPath {
    param([Parameter(Mandatory)] [string]$Path)

    $name = [System.IO.Path]::GetFileName($Path)
    if ($name -eq '.htaccess' -or $name -eq '.gitattributes') {
        return $true
    }

    $extension = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    return @(
        '.css',
        '.html',
        '.js',
        '.json',
        '.map',
        '.md',
        '.svg',
        '.txt',
        '.webmanifest',
        '.xml'
    ) -contains $extension
}

function ConvertTo-GitLfText {
    param([Parameter(Mandatory)] [string]$Text)

    $value = $Text
    if ($value.Length -gt 0 -and $value[0] -eq [char]0xFEFF) {
        $value = $value.Substring(1)
    }

    $normalized = $value.Replace("`r`n", "`n").Replace("`r", "`n")
    $lines = $normalized.Split("`n")
    for ($index = 0; $index -lt $lines.Length; $index++) {
        $lines[$index] = $lines[$index].TrimEnd()
    }

    $end = $lines.Length - 1
    while ($end -ge 0 -and $lines[$end] -eq '') {
        $end--
    }
    if ($end -lt 0) {
        return "`n"
    }

    return (($lines[0..$end] -join "`n") + "`n")
}

function Repair-GitTextPath {
    param([Parameter(Mandatory)] [string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    if (-not (Test-GitTextPath -Path $Path)) {
        return
    }

    $utf8 = [System.Text.UTF8Encoding]::new($false)
    $original = [System.IO.File]::ReadAllText($Path, $utf8)
    $fixed = ConvertTo-GitLfText -Text $original
    if ($fixed -cne $original) {
        [System.IO.File]::WriteAllText($Path, $fixed, $utf8)
    }
}

function Repair-GitTextTree {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [string[]]$Also = @()
    )

    if (Test-Path -LiteralPath $Path -PathType Container) {
        Get-ChildItem -LiteralPath $Path -Recurse -File -Force | ForEach-Object {
            Repair-GitTextPath -Path $_.FullName
        }
    }
    elseif (Test-Path -LiteralPath $Path -PathType Leaf) {
        Repair-GitTextPath -Path $Path
    }

    foreach ($extra in $Also) {
        Repair-GitTextPath -Path $extra
    }
}
