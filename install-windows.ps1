#Requires -RunAsAdministrator
<#
Installs deepcool-lm on Windows: creates a virtual environment, installs
dependencies, and registers an elevated logon Scheduled Task that runs the
monitor headless (pythonw.exe, no console window).

One-time prerequisite (manual): bind the WinUSB driver to the LM360 using
Zadig (https://zadig.akeo.ie):
  Options > List All Devices, select the device with USB ID 3633 0026,
  choose WinUSB as the target driver, click "Replace Driver".
This replaces the stock DeepCool driver — the stock app can no longer drive
the display afterwards.

Elevation is required both for this script and for the monitor itself
(LibreHardwareMonitor loads the WinRing0 kernel driver to read CPU temps).
#>
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$taskName = 'deepcool-lm'

Write-Host 'Creating virtual environment...'
python -m venv "$root\.venv"
& "$root\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$root\.venv\Scripts\python.exe" -m pip install -r "$root\requirements.txt"
# NVML bindings: optional but recommended for NVIDIA GPU util/VRAM readings.
& "$root\.venv\Scripts\python.exe" -m pip install nvidia-ml-py

Write-Host "Registering scheduled task '$taskName'..."
$action    = New-ScheduledTaskAction -Execute "$root\.venv\Scripts\pythonw.exe" `
             -Argument "`"$root\deepcool-lm`" monitor" -WorkingDirectory $root
$trigger   = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
             -LogonType Interactive -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
             -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null

Write-Host 'Starting the monitor...'
Start-ScheduledTask -TaskName $taskName

Write-Host ''
Write-Host 'Done. The monitor starts automatically at logon.'
Write-Host 'If the display stays blank: bind WinUSB with Zadig (see the'
Write-Host 'comment at the top of this script), then run:'
Write-Host "  Start-ScheduledTask -TaskName $taskName"
