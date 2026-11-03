[CmdletBinding()]
param([string]$Python)
# Explicit user entry. No build, deployment, real life pack, service or publication.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $productionPython = Join-Path $repoRoot 'build/release-env/Scripts/python.exe'
    if (Test-Path -LiteralPath $productionPython) { $Python = $productionPython }
    elseif ($env:PYTHON) { $Python = $env:PYTHON }
    else { $Python = 'python' }
}
$logDir = Join-Path $repoRoot 'artifacts'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir ('workbuddy-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
$settings = @{
    PYTHONUTF8 = '1'
    PYTHONDONTWRITEBYTECODE = '1'
    SEEDBANK_OFFLINE_REGRESSION = '1'
    QT_QPA_PLATFORM = 'offscreen'
    QT_QUICK_BACKEND = 'software'
    PYTHONPATH = (Join-Path $PSScriptRoot 'test_support') + [IO.Path]::PathSeparator + (Join-Path $repoRoot 'tools/seed')
}
$previous = @{}
foreach ($name in $settings.Keys) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
}
$tests = @(
    'test_workbuddy_transport',
    'test_codex_transport',
    'test_provider_presets',
    'test_quick.QuickTest.test_workbuddy_settings_save_and_usage_do_not_contact_model',
    'test_quick.QuickTest.test_codex_settings_draft_fields_and_usage_do_not_contact_model'
)
$resultCode = 1
Push-Location $repoRoot
try {
    $ErrorActionPreference = 'Continue'
    Write-Host ('Log: ' + $logFile)
    & $Python -m unittest -v @tests 2>&1 | Tee-Object -FilePath $logFile | Out-Host
    $resultCode = $LASTEXITCODE
    ('Exit code: ' + $resultCode) | Tee-Object -FilePath $logFile -Append | Out-Host
} finally {
    Pop-Location
    foreach ($name in $settings.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
exit $resultCode
