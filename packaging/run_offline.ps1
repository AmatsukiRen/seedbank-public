[CmdletBinding()]
param([ValidateSet('core','integrations','plugins','security')][string]$Suite = 'core')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$script = @{ core = 'run_core_regressions.py'; integrations = 'run_integration_tests.py'; plugins = 'run_plugin_tests.py'; security = 'run_security_tests.py' }[$Suite]
$logDir = Join-Path $repoRoot 'artifacts'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ('offline-' + $Suite + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
Write-Host ('Log: ' + $logFile)
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:SEEDBANK_OFFLINE_REGRESSION = '1'
$guard = Join-Path $PSScriptRoot 'test_support'
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $guard + [IO.Path]::PathSeparator + (Join-Path $repoRoot 'tools\seed')
Push-Location $repoRoot
try {
    $ErrorActionPreference = 'Continue'
    & $pythonExe (Join-Path $repoRoot ('tools\seed\' + $script)) 2>&1 | Tee-Object -FilePath $logFile | Out-Host
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
Write-Host ('Exit code: ' + $resultCode)
exit $resultCode
