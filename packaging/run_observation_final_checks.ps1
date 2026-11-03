[CmdletBinding()]
param([string]$Python, [string]$LogDirectory)
# User entry only: corrected counter case, then the previously skipped security suite.
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
$logFile = Join-Path $LogDirectory ('observation-final-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.log')
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
    ('Frozen source: ' + $repoRoot) | Tee-Object -FilePath $logFile | Out-Host
    'Stage 1: corrected runtime counter case' | Tee-Object -FilePath $logFile -Append | Out-Host
    & $Python (Join-Path $repoRoot 'tools/seed/run_integration_tests.py') --observation-status-followup 2>&1 | Tee-Object -FilePath $logFile -Append | Out-Host
    $resultCode = $LASTEXITCODE
    ('Stage 1 exit code: ' + $resultCode) | Tee-Object -FilePath $logFile -Append | Out-Host
    if ($resultCode -eq 0) {
        'Stage 2: full offline security suite' | Tee-Object -FilePath $logFile -Append | Out-Host
        & $Python (Join-Path $repoRoot 'tools/seed/run_security_tests.py') 2>&1 | Tee-Object -FilePath $logFile -Append | Out-Host
        $resultCode = $LASTEXITCODE
        ('Stage 2 exit code: ' + $resultCode) | Tee-Object -FilePath $logFile -Append | Out-Host
    } else {
        'Security suite not started because stage 1 failed.' | Tee-Object -FilePath $logFile -Append | Out-Host
    }
    ('Exit code: ' + $resultCode) | Tee-Object -FilePath $logFile -Append | Out-Host
} finally {
    Pop-Location
    foreach ($name in $settings.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
exit $resultCode
