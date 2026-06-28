param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $RemainingArgs
)

$ErrorActionPreference = "Stop"

$rootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$extraPathEntries = @()
if ($env:LOCALAPPDATA) {
    $androidPlatformTools = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools"
    if (Test-Path $androidPlatformTools) {
        $extraPathEntries += $androidPlatformTools
    }
}
if ($env:APPDATA) {
    $npmGlobalBin = Join-Path $env:APPDATA "npm"
    if (Test-Path $npmGlobalBin) {
        $extraPathEntries += $npmGlobalBin
    }
}
if ($extraPathEntries.Count -gt 0) {
    $env:Path = (($extraPathEntries + @($env:Path)) -join ";")
    $env:PATH = $env:Path
}

$bashCandidates = @(
    "C:\Program Files\Git\usr\bin\bash.exe",
    "C:\Program Files\Git\bin\bash.exe"
)

$bash = $bashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $bash) {
    $bashCommand = Get-Command bash.exe -ErrorAction SilentlyContinue
    if ($bashCommand) {
        $bash = $bashCommand.Source
    }
}

if (-not $bash) {
    throw "Git Bash not found. Please install Git for Windows first."
}

function Convert-ToBashPath([string] $Path) {
    $resolved = Resolve-Path $Path
    $raw = $resolved.Path
    if ($raw -match "^([A-Za-z]):\\(.*)$") {
        $drive = $Matches[1].ToLowerInvariant()
        $rest = $Matches[2] -replace "\\", "/"
        return "/$drive/$rest"
    }
    return $raw -replace "\\", "/"
}

$bashRoot = Convert-ToBashPath $rootDir
$argText = ""
if ($RemainingArgs.Count -gt 0) {
    $argText = " " + (($RemainingArgs | ForEach-Object { "'" + ($_ -replace "'", "'\''") + "'" }) -join " ")
}

& $bash -lc "cd '$bashRoot' && scripts/finish_all.sh$argText"
