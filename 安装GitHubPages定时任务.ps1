param(
    [string]$TaskName = "",
    [int]$EveryHours = 2
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function ConvertFrom-CodePoint {
    param([int[]]$CodePoints)
    return (-join ($CodePoints | ForEach-Object { [char]$_ }))
}

if ([string]::IsNullOrWhiteSpace($TaskName)) {
    $TaskName = (ConvertFrom-CodePoint @(37319, 38598, 25968, 25454, 30475, 26495)) + "-" + (ConvertFrom-CodePoint @(21457, 24067)) + "GitHubPages"
}

$scriptName = (ConvertFrom-CodePoint @(23450, 26102, 26356, 26032, 24182, 21457, 24067)) + "GitHubPages.ps1"
$scriptPath = Join-Path $root $scriptName

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Missing scheduled publish script: $scriptPath"
}

$escapedScriptPath = $scriptPath.Replace('"', '\"')
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$escapedScriptPath`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours $EveryHours)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Generate the collection dashboard locally and publish the static output to GitHub Pages." `
    -Force | Out-Null

Write-Host "Scheduled task installed: $TaskName"
