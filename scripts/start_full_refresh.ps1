[CmdletBinding()]
param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logDir = Join-Path $repoRoot "output\refresh"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$scheduleAt = (Get-Date).AddMinutes(1)

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

if (-not $PythonPath) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonPath = $venvPython
    } else {
        $PythonPath = "python"
    }
}

$stdoutLog = Join-Path $logDir "full-refresh-$timestamp.stdout.log"
$stderrLog = Join-Path $logDir "full-refresh-$timestamp.stderr.log"
$metadataPath = Join-Path $logDir "full-refresh-$timestamp.json"
$latestMetadataPath = Join-Path $logDir "latest-full-refresh.json"
$launcherCmdPath = Join-Path $logDir "full-refresh-$timestamp.cmd"
$taskName = "BI-Float-Full-Refresh-$timestamp"
$workerScript = Join-Path $PSScriptRoot "run_full_refresh_job.ps1"
$commandLine = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{0}" -PythonPath "{1}" -StdoutLog "{2}" -StderrLog "{3}" -MetadataPath "{4}" -LatestMetadataPath "{5}" -TaskName "{6}"' -f `
    $workerScript,
    $PythonPath,
    $stdoutLog,
    $stderrLog,
    $metadataPath,
    $latestMetadataPath,
    $taskName

$launcherScript = @(
    "@echo off",
    "cd /d ""$repoRoot""",
    $commandLine
)
Set-Content -Path $launcherCmdPath -Value $launcherScript -Encoding ASCII

$metadata = [ordered]@{
    task_name = $taskName
    status = "queued"
    started_at = ""
    finished_at = ""
    exit_code = $null
    workdir = $repoRoot
    python = $PythonPath
    arguments = @("scripts/refresh_data.py", "refresh", "--full")
    command_line = $commandLine
    launcher_cmd = $launcherCmdPath
    stdout_log = $stdoutLog
    stderr_log = $stderrLog
    metadata_path = $metadataPath
}

$metadataJson = $metadata | ConvertTo-Json -Depth 4
Set-Content -Path $metadataPath -Value $metadataJson -Encoding UTF8
Set-Content -Path $latestMetadataPath -Value $metadataJson -Encoding UTF8

$createCommand = 'schtasks /Create /TN "{0}" /SC ONCE /SD {1} /ST {2} /TR "\"{3}\"" /RL LIMITED /F' -f `
    $taskName,
    $scheduleAt.ToString("MM/dd/yyyy"),
    $scheduleAt.ToString("HH:mm"),
    $launcherCmdPath
$createOutput = & cmd.exe /d /c $createCommand 2>&1

if ($LASTEXITCODE -ne 0) {
    throw "Failed to create scheduled task. $($createOutput -join ' ')"
}

$runCommand = 'schtasks /Run /TN "{0}"' -f $taskName
$runOutput = & cmd.exe /d /c $runCommand 2>&1

if ($LASTEXITCODE -ne 0) {
    throw "Failed to start scheduled task. $($runOutput -join ' ')"
}

Write-Output "Started full refresh in the background."
Write-Output "Task: $taskName"
Write-Output "Stdout: $stdoutLog"
Write-Output "Stderr: $stderrLog"
Write-Output "Metadata: $metadataPath"
