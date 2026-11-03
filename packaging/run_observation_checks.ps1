[CmdletBinding()]
param([string]$Python, [string]$LogDirectory)
# User entry only: artificial packs, fake transports and software Qt.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $productionPython = Join-Path $repoRoot 'build/release-env/Scripts/python.exe'
    if (Test-Path -LiteralPath $productionPython) { $Python = $productionPython }
    elseif ($env:PYTHON) { $Python = $env:PYTHON }
    else { $Python = 'python' }
}
if (-not $LogDirectory) { $LogDirectory = Join-Path $repoRoot 'artifacts' }
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$logFile = Join-Path $LogDirectory ('observation-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$settings = @{
    PYTHONUTF8 = '1'
    PYTHONDONTWRITEBYTECODE = '1'
    SEEDBANK_OFFLINE_REGRESSION = '1'
    PYTHONPATH = (Join-Path $PSScriptRoot 'test_support') + [IO.Path]::PathSeparator + (Join-Path $repoRoot 'tools/seed')
}
$previous = @{}
foreach ($name in $settings.Keys) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
}
$resultCode = 1
Push-Location $repoRoot
try {
    $ErrorActionPreference = 'Continue'
    Write-Host ('Log: ' + $logFile)
    & $Python (Join-Path $repoRoot 'tools/seed/run_observation_tests.py') 2>&1 | Tee-Object -FilePath $logFile | Out-Host
    $resultCode = $LASTEXITCODE
    ('Exit code: ' + $resultCode) | Tee-Object -FilePath $logFile -Append | Out-Host
} finally {
    Pop-Location
    foreach ($name in $settings.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
exit $resultCode
