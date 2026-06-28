param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $RemainingArgs
)

$ErrorActionPreference = "Stop"

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {
}

$env:PYTHONUTF8 = if ($env:PYTHONUTF8) { $env:PYTHONUTF8 } else { "1" }
$env:PYTHONIOENCODING = if ($env:PYTHONIOENCODING) { $env:PYTHONIOENCODING } else { "utf-8" }
$env:LANG = if ($env:LANG) { $env:LANG } else { "C.UTF-8" }
$env:LC_ALL = if ($env:LC_ALL) { $env:LC_ALL } else { "C.UTF-8" }

$rootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$extraPathEntries = @()
if ($env:LOCALAPPDATA) {
    $androidPlatformTools = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools"
    if (Test-Path $androidPlatformTools) {
        $extraPathEntries += $androidPlatformTools
        $adbExe = Join-Path $androidPlatformTools "adb.exe"
        if ((Test-Path $adbExe) -and -not $env:ADB_PATH) {
            $env:ADB_PATH = $adbExe
        }
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

& $bash -lc "cd '$bashRoot' && scripts/start_all.sh$argText"
