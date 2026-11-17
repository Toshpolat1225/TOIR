# Registers the TOIR scales collector as a Windows scheduled task (run in PowerShell as the SAME Windows user that has the
# SMB credentials of the scale PCs in Windows Credential Manager: that is why it runs "as this user, only when logged on").
#
#   powershell -ExecutionPolicy Bypass -File scripts\scales_collector\install_task.ps1
#
# Creates two tasks:
#   TOIR-Scales-Collector   at logon, restarts if it stops, runs `collector.py --loop 60` (one pass per minute, never overlaps)
#   TOIR-Scales-Rescan      daily 03:30, `collector.py --rescan-days 3 --once` (picks up an operator's late edits)
# The ingest token is read from the user-level environment variable SCALES_INGEST_TOKEN (never stored in the task).
param(
    [string]$Python = "",
    [string]$ToirUrl = "https://192.168.28.104"
)
$ErrorActionPreference = "Stop"
if (-not $Python) {
    # the real interpreter of this user (not a project venv that may be first on PATH): the py launcher, else `python`
    # `python` of the CURRENT shell (an activated project .venv is fine: pyodbc is installed into whatever interpreter is chosen)
    $Python = (Get-Command python -ErrorAction Stop).Source
}
$ErrorActionPreference = "Continue"
& $Python -c "import pyodbc" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "pyodbc is missing for ${Python}: installing it..."
    & $Python -m pip install --quiet pyodbc
    & $Python -c "import pyodbc" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "pyodbc could not be installed for $Python" }
}
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "collector.py"
if (-not [Environment]::GetEnvironmentVariable("SCALES_INGEST_TOKEN", "User")) {
    throw "SCALES_INGEST_TOKEN is not set for this user. Set it first (see README.md), then run this script again."
}
[Environment]::SetEnvironmentVariable("TOIR_URL", $ToirUrl, "User")

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

$loop = New-ScheduledTaskAction -Execute $Python -Argument "`"$script`" --loop 60" -WorkingDirectory $PSScriptRoot
Register-ScheduledTask -TaskName "TOIR-Scales-Collector" -Action $loop -Trigger (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME") `
    -Settings $settings -Principal $principal -Force | Out-Null

$rescan = New-ScheduledTaskAction -Execute $Python -Argument "`"$script`" --rescan-days 3 --once" -WorkingDirectory $PSScriptRoot
Register-ScheduledTask -TaskName "TOIR-Scales-Rescan" -Action $rescan -Trigger (New-ScheduledTaskTrigger -Daily -At "03:30") `
    -Settings $settings -Principal $principal -Force | Out-Null

Start-ScheduledTask -TaskName "TOIR-Scales-Collector"
Write-Host "Done. Log: $env:LOCALAPPDATA\toir_scales\collector.log"
