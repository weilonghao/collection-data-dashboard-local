$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "source"
$app = Join-Path $root "app"
$publishConfigPath = Join-Path $root "config\feishu_publish.json"
$publishResultPath = Join-Path $app "feishu_publish_result.json"
$logPath = Join-Path $app "scheduled_refresh.log"

function Write-RefreshLog {
    param([string]$Message)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $logPath -Value $line -Encoding UTF8
}

function Join-ProcessArguments {
    param([string[]]$Arguments)
    $quoted = foreach ($arg in $Arguments) {
        if ($null -eq $arg) {
            '""'
        }
        elseif ($arg -match '[\s"]') {
            '"' + ($arg.Replace('\', '\\').Replace('"', '\"')) + '"'
        }
        else {
            $arg
        }
    }
    return ($quoted -join " ")
}

function Invoke-CheckedCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $FilePath
    $psi.Arguments = Join-ProcessArguments $Arguments
    $psi.WorkingDirectory = $WorkingDirectory
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $psi.Environment["LARK_CLI_NO_PROXY"] = "1"

    $process = [System.Diagnostics.Process]::Start($psi)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    if ($process.ExitCode -ne 0) {
        throw "Command failed ($($process.ExitCode)): $FilePath $($Arguments -join ' ')`nSTDOUT:`n$stdout`nSTDERR:`n$stderr"
    }

    [pscustomobject]@{
        ExitCode = $process.ExitCode
        Stdout = $stdout
        Stderr = $stderr
    }
}

function ConvertFrom-JsonOutput {
    param([string]$Text)
    $start = $Text.IndexOf("{")
    $end = $Text.LastIndexOf("}")
    if ($start -lt 0 -or $end -lt $start) {
        throw "Command did not return a JSON object: $Text"
    }
    return $Text.Substring($start, $end - $start + 1) | ConvertFrom-Json
}

function Get-ConfigString {
    param(
        [object]$Config,
        [string]$Name
    )
    $property = $Config.PSObject.Properties[$Name]
    if ($null -eq $property -or $null -eq $property.Value) {
        return ""
    }
    return [string]$property.Value
}

function Get-WikiTokenFromUrl {
    param([string]$Url)
    if ($Url -match "/wiki/([^/?#]+)") {
        return $Matches[1]
    }
    throw "Target wiki URL does not contain a /wiki/ token: $Url"
}

function Get-HtmlFigureBlockIds {
    param([string]$Content)
    $options = [System.Text.RegularExpressions.RegexOptions]::IgnoreCase -bor [System.Text.RegularExpressions.RegexOptions]::Singleline
    $pattern = '<figure\b(?=[^>]*\bid="([^"]+)")[\s\S]*?<source\b[^>]*(?:\bmime="text/html"|\.html\b)[^>]*>[\s\S]*?</figure>'
    $ids = New-Object System.Collections.Generic.List[string]
    foreach ($match in [System.Text.RegularExpressions.Regex]::Matches($Content, $pattern, $options)) {
        $id = $match.Groups[1].Value
        if (-not [string]::IsNullOrWhiteSpace($id) -and -not $ids.Contains($id)) {
            [void]$ids.Add($id)
        }
    }
    return [string[]]$ids
}

try {
    $stage = "start"
    Write-RefreshLog "start collection dashboard refresh"
    $env:LARK_CLI_NO_PROXY = "1"

    $stage = "load_publish_config"
    if (-not (Test-Path -LiteralPath $publishConfigPath)) {
        throw "Missing publish config: $publishConfigPath"
    }
    $publishConfig = Get-Content -Raw -Encoding UTF8 -LiteralPath $publishConfigPath | ConvertFrom-Json
    $targetWikiUrl = Get-ConfigString $publishConfig "target_wiki_url"
    $targetDocUrl = Get-ConfigString $publishConfig "target_doc_url"
    $targetDocToken = Get-ConfigString $publishConfig "target_doc_token"
    if ([string]::IsNullOrWhiteSpace($targetWikiUrl) -and [string]::IsNullOrWhiteSpace($targetDocUrl) -and [string]::IsNullOrWhiteSpace($targetDocToken)) {
        throw "config/feishu_publish.json must include target_wiki_url, target_doc_url, or target_doc_token"
    }

    $stage = "generate_dashboard"
    Push-Location $source
    try {
        $anchorDate = Get-Date -Format "yyyy-MM-dd"
        $generateResult = Invoke-CheckedCommand `
            -FilePath "python" `
            -Arguments @(
                "backend\jobs\generate_collection_dashboard.py",
                "--config", "config\collection_dashboard.yaml",
                "--anchor-date", $anchorDate
            ) `
            -WorkingDirectory $source
        $generation = ConvertFrom-JsonOutput $generateResult.Stdout
        if ($generation.status -ne "collection_dashboard_generated") {
            throw "Dashboard generation returned unexpected status: $($generation.status)"
        }
    }
    finally {
        Pop-Location
    }

    $stage = "copy_outputs"
    $latest = Join-Path $source "data\collection-dashboard\latest"
    foreach ($name in @(
        "collection_data_dashboard.html",
        "collection_dashboard.json",
        "dashboard_overview.json",
        "sources_manifest.json",
        "run.log"
    )) {
        $src = Join-Path $latest $name
        if (Test-Path -LiteralPath $src) {
            Copy-Item -Force -LiteralPath $src -Destination (Join-Path $app $name)
        }
    }

    $stage = "verify_generated_html"
    $htmlPath = Join-Path $app "collection_data_dashboard.html"
    if (-not (Test-Path -LiteralPath $htmlPath)) {
        throw "Generated HTML not found: $htmlPath"
    }
    $htmlUploadName = Split-Path -Leaf $htmlPath

    $targetDocTitle = ""
    if (-not [string]::IsNullOrWhiteSpace($targetWikiUrl)) {
        $stage = "resolve_target_wiki"
        $targetWikiToken = Get-WikiTokenFromUrl $targetWikiUrl
        $wikiNode = Invoke-CheckedCommand `
            -FilePath "lark-cli.cmd" `
            -Arguments @(
                "wiki", "spaces", "get_node",
                "--params", "{`"token`":`"$targetWikiToken`"}",
                "--format", "json"
            ) `
            -WorkingDirectory $root
        $wikiNodePayload = ConvertFrom-JsonOutput $wikiNode.Stdout
        $node = $wikiNodePayload.data.node
        if ($node.obj_type -ne "docx") {
            throw "Target wiki node must resolve to docx, got obj_type=$($node.obj_type)"
        }
        $targetDocToken = [string]$node.obj_token
        $targetDocTitle = [string]$node.title
        if ([string]::IsNullOrWhiteSpace($targetDocUrl) -and $targetWikiUrl -match "^(https?://[^/]+)") {
            $targetDocUrl = "$($Matches[1])/docx/$targetDocToken"
        }
    }
    elseif (-not [string]::IsNullOrWhiteSpace($targetDocUrl) -and $targetDocUrl -match "/docx/([^/?#]+)") {
        $targetDocToken = $Matches[1]
    }
    if ([string]::IsNullOrWhiteSpace($targetDocToken)) {
        throw "Could not resolve target document token"
    }

    $stage = "fetch_target_document"
    $targetDoc = Invoke-CheckedCommand `
        -FilePath "lark-cli.cmd" `
        -Arguments @(
            "docs", "+fetch",
            "--api-version", "v2",
            "--doc", $targetDocToken,
            "--detail", "full",
            "--format", "json"
        ) `
        -WorkingDirectory $root
    $targetDocPayload = ConvertFrom-JsonOutput $targetDoc.Stdout
    $targetDocContent = [string]$targetDocPayload.data.document.content
    if ([string]::IsNullOrWhiteSpace($targetDocTitle)) {
        if ($targetDocContent -match '<title\b[^>]*>(.*?)</title>') {
            $targetDocTitle = $Matches[1]
        }
        else {
            $targetDocTitle = "collection data dashboard"
        }
    }

    $stage = "delete_existing_html_file_blocks"
    $deletedHtmlBlockIds = Get-HtmlFigureBlockIds $targetDocContent
    if ($deletedHtmlBlockIds.Count -gt 0) {
        [void](Invoke-CheckedCommand `
            -FilePath "lark-cli.cmd" `
            -Arguments @(
                "docs", "+update",
                "--api-version", "v2",
                "--doc", $targetDocToken,
                "--command", "block_delete",
                "--block-id", ($deletedHtmlBlockIds -join ",")
            ) `
            -WorkingDirectory $root)
    }

    $stage = "insert_latest_html_file"
    $mediaInsert = Invoke-CheckedCommand `
        -FilePath "lark-cli.cmd" `
        -Arguments @(
            "docs", "+media-insert",
            "--doc", $targetDocToken,
            "--file", "app\collection_data_dashboard.html",
            "--type", "file",
            "--file-view", "preview"
        ) `
        -WorkingDirectory $root
    $mediaInsertPayload = ConvertFrom-JsonOutput $mediaInsert.Stdout
    $insertedBlockId = [string]$mediaInsertPayload.data.block_id
    $htmlFileToken = [string]$mediaInsertPayload.data.file_token

    $generatedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $result = [pscustomobject]@{
        status = "ok"
        stage = "complete"
        generated_at = $generatedAt
        local_html = $htmlPath
        target_wiki_url = $targetWikiUrl
        target_doc_url = $targetDocUrl
        target_doc_token = $targetDocToken
        target_doc_title = $targetDocTitle
        uploaded_html_name = $htmlUploadName
        uploaded_html_token = $htmlFileToken
        inserted_block_id = $insertedBlockId
        deleted_html_block_ids = $deletedHtmlBlockIds
        record_count = $generation.record_count
        vehicle_daily_status_count = $generation.vehicle_daily_status_count
        diagnostics_count = $generation.diagnostics_count
    }
    $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $publishResultPath -Encoding UTF8
    Write-RefreshLog "success replaced html in $targetDocToken"
    $result | ConvertTo-Json -Depth 10
}
catch {
    $errorResult = [pscustomobject]@{
        status = "failed"
        stage = $stage
        failed_at = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        error = $_.Exception.Message
    }
    $errorResult | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $publishResultPath -Encoding UTF8
    Write-RefreshLog "failed at $stage $($_.Exception.Message)"
    throw
}
