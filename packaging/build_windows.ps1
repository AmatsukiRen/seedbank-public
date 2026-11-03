[CmdletBinding()]
param([switch]$NoInstall, [switch]$SkipSmoke)
# Production only. SkipSmoke remains accepted for existing delivery commands.
# No application self-check or test is launched, with or without that flag.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
Push-Location $repoRoot
try {
    $ErrorActionPreference = 'Continue'
    if (-not $NoInstall) {
        & $pythonExe -m pip install -e './tools/seed[desktop,channels]' 'PyInstaller==6.22.3'
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    }
    & $pythonExe -m PyInstaller packaging/seedbank.spec --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw 'Production packaging failed.' }
    Write-Host 'Produced dist/seedbank.exe. Not executed or tested.'
} finally { Pop-Location }
