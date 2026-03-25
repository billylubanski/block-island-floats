[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [Parameter(Mandatory = $true)][string]$StdoutLog,
    [Parameter(Mandatory = $true)][string]$StderrLog,
    [Parameter(Mandatory = $true)][string]$MetadataPath,
    [Parameter(Mandatory = $true)][string]$LatestMetadataPath,
    [string]$TaskName = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $PythonPath) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonPath = $venvPython
    } else {
        $PythonPath = "python"
    }
}

foreach ($path in @($StdoutLog, $StderrLog, $MetadataPath, $LatestMetadataPath)) {
    $directory = Split-Path -Parent $path
    if ($directory) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
}

function Write-RefreshMetadata {
    param(
        [Parameter(Mandatory = $true)][string]$Status,
        [int]$ExitCode = 0,
        [string]$FinishedAt = ""
    )

    $metadata = [ordered]@{
        task_name = $TaskName
        status = $Status
        started_at = $script:startedAt
        finished_at = $FinishedAt
        exit_code = $ExitCode
        powershell_pid = $PID
        workdir = $repoRoot
        python = $PythonPath
        arguments = @("scripts/refresh_data.py", "refresh", "--full")
        stdout_log = $StdoutLog
        stderr_log = $StderrLog
        metadata_path = $MetadataPath
    }

    $metadataJson = $metadata | ConvertTo-Json -Depth 4
    Set-Content -Path $MetadataPath -Value $metadataJson -Encoding UTF8
    Set-Content -Path $LatestMetadataPath -Value $metadataJson -Encoding UTF8
}

$script:startedAt = (Get-Date).ToString("o")

try {
    Write-RefreshMetadata -Status "running"
    Add-Content -Path $StdoutLog -Value "[$script:startedAt] Starting full refresh."

    & $PythonPath "scripts/refresh_data.py" "refresh" "--full" 1>> $StdoutLog 2>> $StderrLog
    $exitCode = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 0 }
    $finishedAt = (Get-Date).ToString("o")

    if ($exitCode -eq 0) {
        Add-Content -Path $StdoutLog -Value "[$finishedAt] Full refresh finished successfully."
        Write-RefreshMetadata -Status "completed" -ExitCode $exitCode -FinishedAt $finishedAt
        exit 0
    }

    Add-Content -Path $StderrLog -Value "[$finishedAt] Full refresh failed with exit code $exitCode."
    Write-RefreshMetadata -Status "failed" -ExitCode $exitCode -FinishedAt $finishedAt
    exit $exitCode
} catch {
    $finishedAt = (Get-Date).ToString("o")
    Add-Content -Path $StderrLog -Value "[$finishedAt] Launcher error: $($_.Exception.Message)"
    Write-RefreshMetadata -Status "failed" -ExitCode 1 -FinishedAt $finishedAt
    throw
}
