param(
    [string]$Branch = "main",
    [string]$Remote = "origin",
    [switch]$SkipGit
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Join-Path $root "app"
$public = Join-Path $root "public"

function Write-PublishLog {
    param([string]$Message)
    $logPath = Join-Path $app "github_pages_publish.log"
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

function Copy-RequiredFile {
    param(
        [string]$Source,
        [string]$Destination
    )
    if (-not (Test-Path -LiteralPath $Source)) {
        throw "Missing required publish source: $Source"
    }
    Copy-Item -Force -LiteralPath $Source -Destination $Destination
}

try {
    Write-PublishLog "start github pages publish"

    if (-not (Test-Path -LiteralPath $public)) {
        New-Item -ItemType Directory -Path $public | Out-Null
    }

    Copy-RequiredFile -Source (Join-Path $app "collection_data_dashboard.html") -Destination (Join-Path $public "index.html")
    Copy-RequiredFile -Source (Join-Path $app "collection_dashboard.json") -Destination (Join-Path $public "collection_dashboard.json")
    Copy-RequiredFile -Source (Join-Path $app "dashboard_overview.json") -Destination (Join-Path $public "dashboard_overview.json")
    Copy-RequiredFile -Source (Join-Path $app "sources_manifest.json") -Destination (Join-Path $public "sources_manifest.json")
    Copy-RequiredFile -Source (Join-Path $app "run.log") -Destination (Join-Path $public "run.log")

    $metadata = [pscustomobject]@{
        status = "ok"
        generated_at = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        source = "local_scheduled_task"
        files = @(
            "index.html",
            "collection_dashboard.json",
            "dashboard_overview.json",
            "sources_manifest.json",
            "run.log"
        )
    }
    $metadata | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $public "publish_metadata.json") -Encoding UTF8

    if ($SkipGit) {
        Write-PublishLog "success prepared public directory with git skipped"
        return
    }

    Push-Location $root
    try {
        git rev-parse --is-inside-work-tree *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Current directory is not a Git repository. Run git init and configure a GitHub remote before publishing."
        }

        git add public/
        if ($LASTEXITCODE -ne 0) {
            throw "git add public/ failed"
        }

        $changes = git status --porcelain -- public/
        if ([string]::IsNullOrWhiteSpace($changes)) {
            Write-PublishLog "no public changes to publish"
            return
        }

        git commit -m "Update dashboard publish artifacts"
        if ($LASTEXITCODE -ne 0) {
            throw "git commit failed"
        }

        git push $Remote $Branch
        if ($LASTEXITCODE -ne 0) {
            throw "git push $Remote $Branch failed"
        }

        Write-PublishLog "success pushed public directory to $Remote/$Branch"
    }
    finally {
        Pop-Location
    }
}
catch {
    Write-PublishLog "failed $($_.Exception.Message)"
    throw
}
