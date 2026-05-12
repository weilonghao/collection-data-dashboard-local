$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "source"
$app = Join-Path $root "app"

Push-Location $source
try {
    $anchorDate = Get-Date -Format "yyyy-MM-dd"
    python backend\jobs\generate_collection_dashboard.py `
        --config config\collection_dashboard.yaml `
        --anchor-date $anchorDate
}
finally {
    Pop-Location
}

$latest = Join-Path $source "data\collection-dashboard\latest"
$latestRaw = Join-Path $latest "raw"
$appRaw = Join-Path $app "raw"
Copy-Item -Force (Join-Path $latest "collection_data_dashboard.html") (Join-Path $app "collection_data_dashboard.html")
Copy-Item -Force (Join-Path $latest "collection_dashboard.json") (Join-Path $app "collection_dashboard.json")
Copy-Item -Force (Join-Path $latest "dashboard_overview.json") (Join-Path $app "dashboard_overview.json")
Copy-Item -Force (Join-Path $latest "sources_manifest.json") (Join-Path $app "sources_manifest.json")
Copy-Item -Force (Join-Path $latest "run.log") (Join-Path $app "run.log")
if (Test-Path -LiteralPath $latestRaw) {
    if (-not (Test-Path -LiteralPath $appRaw)) {
        New-Item -ItemType Directory -Path $appRaw | Out-Null
    }
    Copy-Item -Force -Path (Join-Path $latestRaw "*") -Destination $appRaw
}

Write-Host "看板已生成：" (Join-Path $app "collection_data_dashboard.html")
