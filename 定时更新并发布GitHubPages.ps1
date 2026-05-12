param(
    [switch]$SkipGit
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Join-Path $root "app"
$logPath = Join-Path $app "github_pages_publish.log"

function ConvertFrom-CodePoint {
    param([int[]]$CodePoints)
    return (-join ($CodePoints | ForEach-Object { [char]$_ }))
}

function Write-GitHubPagesRefreshLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

try {
    Write-GitHubPagesRefreshLog "start scheduled github pages refresh"

    $generateScript = (ConvertFrom-CodePoint @(29983, 25104, 30475, 26495)) + ".ps1"
    $publishScript = (ConvertFrom-CodePoint @(21457, 24067, 21040)) + "GitHubPages.ps1"

    & (Join-Path $root $generateScript)
    if ($LASTEXITCODE -ne 0) {
        throw "$generateScript failed with exit code $LASTEXITCODE"
    }

    if ($SkipGit) {
        & (Join-Path $root $publishScript) -SkipGit
    }
    else {
        & (Join-Path $root $publishScript)
    }
    if ($LASTEXITCODE -ne 0) {
        throw "$publishScript failed with exit code $LASTEXITCODE"
    }

    Write-GitHubPagesRefreshLog "success scheduled github pages refresh"
}
catch {
    Write-GitHubPagesRefreshLog "failed scheduled github pages refresh $($_.Exception.Message)"
    throw
}
