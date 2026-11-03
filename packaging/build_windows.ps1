[CmdletBinding()]
param([switch]$NoInstall, [switch]$SkipSmoke, [string]$OutputDirectory = 'dist')
# Production only. SkipSmoke remains accepted for existing delivery commands.
# No application self-check or test is launched, with or without that flag.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
Push-Location $repoRoot
try {
    $ErrorActionPreference = 'Continue'
    if (-not $NoInstall) {
        & $pythonExe -m pip install -r packaging/requirements-windows.lock
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    }
    $sourceCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record source commit.' }
    $sourceChanges = @(& git status --porcelain --untracked-files=normal)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record source working tree.' }
    & $pythonExe -m PyInstaller packaging/seedbank.spec --noconfirm --clean --distpath $OutputDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Production packaging failed.' }
    $builtExecutable = Join-Path $OutputDirectory 'seedbank.exe'
    $receipt = [ordered]@{
        source_commit = $sourceCommit
        source_worktree_clean = ($sourceChanges.Count -eq 0)
        source_changes = $sourceChanges
        runtime_sha256 = (Get-FileHash -LiteralPath $builtExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
        bytes = (Get-Item -LiteralPath $builtExecutable).Length
        built_at_utc = [DateTime]::UtcNow.ToString('o')
        application_executed = $false
        tests_executed = $false
    }
    [IO.File]::WriteAllText((Join-Path (Resolve-Path $OutputDirectory).Path 'runtime-build.json'),
        ($receipt | ConvertTo-Json -Depth 4) + "`n", [Text.UTF8Encoding]::new($false))
    Write-Host ('Produced ' + $builtExecutable + '. Not executed or tested.')
} finally { Pop-Location }
