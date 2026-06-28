$ErrorActionPreference = "Continue"

$root = "D:\android_auto_test"
$portPattern = ":8000|:5173|:4723|:4724|:4725|:4732|:4733"
$ports = @(8000, 5173, 4723, 4724, 4725, 4732, 4733)

$targets = Get-CimInstance Win32_Process | Where-Object {
    $cmd = $_.CommandLine
    $name = $_.Name
    if (-not $cmd) {
        return $false
    }
    if ($_.ProcessId -eq $PID) {
        return $false
    }

    $isProjectRuntime =
        ($name -in @(
            "python.exe",
            "node.exe",
            "AndroidAutoClient.exe",
            "AutoFans.exe",
            "AutoFansStart.exe",
            "AutoFansFinish.exe"
        )) -and (
            $cmd -like "*$root*" -or
            $cmd -like "*uvicorn*app.main*" -or
            $cmd -like "*automation_client*" -or
            $cmd -like "*appium*" -or
            $cmd -like "*vite*"
        )

    $isProjectShell =
        ($name -in @("powershell.exe", "bash.exe", "sh.exe")) -and (
            $cmd -like "*$root*scripts*start_all*" -or
            $cmd -like "*$root*scripts*finish_all*" -or
            $cmd -like "*/d/android_auto_test*scripts/start_all*"
        )

    return $isProjectRuntime -or $isProjectShell
}

Write-Host "--- targets ---"
$targets | Select-Object ProcessId, Name, CommandLine | Format-List

foreach ($process in $targets) {
    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        Write-Host "stopped $($process.ProcessId) $($process.Name)"
    } catch {
        Write-Host "failed $($process.ProcessId) $($process.Name): $($_.Exception.Message)"
    }
}

Start-Sleep -Seconds 2
Write-Host "--- stop port owners ---"
foreach ($port in $ports) {
    $lines = netstat -ano | Select-String ":$port"
    foreach ($line in $lines) {
        $parts = ($line.Line.Trim() -split "\s+")
        if ($parts.Length -lt 5 -or $parts[3] -ne "LISTENING") {
            continue
        }
        $ownerPid = [int] $parts[4]
        if ($ownerPid -eq $PID) {
            continue
        }
        try {
            Stop-Process -Id $ownerPid -Force -ErrorAction Stop
            Write-Host "stopped port=$port pid=$ownerPid"
        } catch {
            Write-Host "failed port=$port pid=$ownerPid`: $($_.Exception.Message)"
        }
    }
}

Start-Sleep -Seconds 2
Write-Host "--- remaining ports ---"
netstat -ano | Select-String $portPattern
