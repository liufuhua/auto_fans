# Windows Launcher

This folder contains the Windows launcher source for the project.

The launcher does not bundle Python, MySQL, Node.js, ADB, or Appium. Those
dependencies still need to be installed on the system first.

## Run without packaging

```powershell
python launcher\start_launcher.py
python launcher\finish_launcher.py
```

## Build exe

```powershell
.\launcher\build_exe.ps1 -CopyToRoot
```

If Python is not in `PATH`, specify the Python executable used for packaging:

```powershell
$env:LAUNCHER_PYTHON = "C:\Path\To\python.exe"
.\launcher\build_exe.ps1 -CopyToRoot
```

Generated files:

```text
AutoFans.exe
AutoFansStart.exe
AutoFansFinish.exe
```

`AutoFans.exe` is the normal desktop entry. It opens a WebView window,
starts all local services without command windows, and stops all services when
the client window closes.

## Runtime logs

Launcher logs are written to:

```text
logs\launcher\
```

The latest machine-readable status is written to:

```text
logs\launcher\service_status.json
```

## Check commands

These commands do not start or stop services:

```powershell
.\AutoFansStart.exe --check-only --no-popup
.\AutoFansStart.exe --status-only
.\AutoFansFinish.exe --status-only
```
