[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [string]$Python,
    [string]$Model
)
# Explicit user entry: no build, deployment, model service or publishing.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimePath = (Resolve-Path -LiteralPath $Executable).Path
if (-not $Python) {
    if ($env:PYTHON) { $Python = $env:PYTHON }
    elseif (Test-Path -LiteralPath (Join-Path $repoRoot 'build/release-env/Scripts/python.exe')) {
        $Python = Join-Path $repoRoot 'build/release-env/Scripts/python.exe'
    }
    elseif (Test-Path -LiteralPath (Join-Path $repoRoot '.venv/Scripts/python.exe')) {
        $Python = Join-Path $repoRoot '.venv/Scripts/python.exe'
    }
    else { $Python = 'python' }
}
$stamp = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$artifacts = Join-Path $repoRoot 'artifacts'
New-Item -ItemType Directory -Path $artifacts -Force | Out-Null
$logPath = Join-Path $artifacts ('candidate-check-' + $stamp + '.log')
$reportPath = Join-Path $artifacts ('candidate-check-' + $stamp)
$resultCode = 1
$previousUtf8 = $env:PYTHONUTF8
$env:PYTHONUTF8 = '1'
Push-Location $repoRoot
Start-Transcript -Path $logPath | Out-Null
try {
    Write-Host ('Runtime: ' + $runtimePath)
    Write-Host ('Log: ' + $logPath)
    # Let unittest's stderr remain normal output under Windows PowerShell 5.1.
    $ErrorActionPreference = 'Continue'
    & $Python (Join-Path $PSScriptRoot 'test_qt_distribution.py')
    if ($LASTEXITCODE -ne 0) { throw 'Qt packaging regression failed.' }
    & $Python (Join-Path $PSScriptRoot 'verify_candidate.py') $runtimePath
    if ($LASTEXITCODE -ne 0) { throw 'Executable content/icon check failed.' }
    & $Python (Join-Path $PSScriptRoot 'verify_notice_bundle.py') $runtimePath
    if ($LASTEXITCODE -ne 0) { throw 'Qt notice bundle check failed.' }
    $arguments = @((Join-Path $PSScriptRoot 'run_packaged_checks.py'), $runtimePath, $reportPath)
    if ($Model) { $arguments += @('--model', (Resolve-Path -LiteralPath $Model).Path) }
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Isolated application check failed.' }
    $resultCode = 0
    Write-Host 'PASS: packaging, notices and isolated application checks.'
    if (-not $Model) { Write-Host 'Native Live2D was NOT checked: no model argument supplied.' }
} catch {
    Write-Host ('FAIL: ' + $_.Exception.Message)
} finally {
    Write-Host ('Exit code: ' + $resultCode)
    Write-Host ('Log: ' + $logPath)
    Write-Host ('Application report, when created: ' + (Join-Path $reportPath 'report.json'))
    Stop-Transcript | Out-Null
    Pop-Location
    $env:PYTHONUTF8 = $previousUtf8
}
exit $resultCode
