#Requires -RunAsAdministrator
<#
Removes the deepcool-lm scheduled task. The WinUSB driver binding is left in
place; to restore the stock driver, open Device Manager, find the LM device,
and choose "Update driver".
#>
$ErrorActionPreference = 'Stop'
$taskName = 'deepcool-lm'

Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host "Removed scheduled task '$taskName'."
Write-Host 'The .venv directory and the WinUSB binding were left in place.'
