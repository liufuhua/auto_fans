param(
    [switch] $CopyToRoot
)

$ErrorActionPreference = "Stop"

$rootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$autoFansIcon = Join-Path $rootDir "launcher\assets\autofans.ico"
$pythonPath = $null
$pythonCandidates = @()
if ($env:LAUNCHER_PYTHON) {
    $pythonCandidates += $env:LAUNCHER_PYTHON
}

$pythonCandidates += @(
    (Join-Path $rootDir "automation_client\.venv\Scripts\python.exe"),
    (Join-Path $rootDir "api\.venv\Scripts\python.exe")
)

$systemPython = Get-Command python -ErrorAction SilentlyContinue
if ($systemPython) {
    $pythonCandidates += $systemPython.Source
}

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    $pythonCandidates += $pyLauncher.Source
}

foreach ($candidate in $pythonCandidates) {
    if (-not (Test-Path $candidate)) {
        continue
    }
    try {
        & $candidate -c "import sys; print(sys.version)" *> $null
        if ($LASTEXITCODE -eq 0) {
            $pythonPath = $candidate
            break
        }
    } catch {
        continue
    }
}

if (-not $pythonPath) {
    throw "No usable Python found. Install Python or create project virtualenvs first."
}

Push-Location $rootDir
try {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pythonPath -m pip show pyinstaller *> $null
    $pyinstallerMissing = $LASTEXITCODE -ne 0
    $ErrorActionPreference = $previousErrorActionPreference
    if ($pyinstallerMissing) {
        & $pythonPath -m pip install pyinstaller
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pythonPath -m pip show pywebview *> $null
    $pywebviewMissing = $LASTEXITCODE -ne 0
    $ErrorActionPreference = $previousErrorActionPreference
    if ($pywebviewMissing) {
        & $pythonPath -m pip install pywebview
    }

    & $pythonPath -m PyInstaller `
        --onefile `
        --console `
        --name AutoFansStart `
        launcher\start_launcher.py

    & $pythonPath -m PyInstaller `
        --onefile `
        --console `
        --name AutoFansFinish `
        launcher\finish_launcher.py

    & $pythonPath -m PyInstaller `
        --onefile `
        --windowed `
        --name AutoFans `
        --icon "$autoFansIcon" `
        launcher\desktop_client.py

    if ($CopyToRoot) {
        Copy-Item -LiteralPath "dist\AutoFansStart.exe" -Destination "AutoFansStart.exe" -Force
        Copy-Item -LiteralPath "dist\AutoFansFinish.exe" -Destination "AutoFansFinish.exe" -Force
        Copy-Item -LiteralPath "dist\AutoFans.exe" -Destination "AutoFans.exe" -Force
    }
}
finally {
    Pop-Location
}
