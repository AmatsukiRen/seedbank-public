[CmdletBinding()]
param([string]$Executable, [string]$Output, [string]$Model = '')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $Executable) { $Executable = Join-Path $repoRoot 'dist\seedbank.exe' }
$resolvedExe = (Resolve-Path -LiteralPath $Executable).Path
if (-not $Output) { $Output = Join-Path $repoRoot ('artifacts\showcase-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$resolvedOutput = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $resolvedOutput) { throw 'Choose a new output directory; existing captures are never overwritten.' }
$env:PYTHONUTF8 = '1'
if ($Model) {
    $resolvedModel = (Resolve-Path -LiteralPath $Model).Path
    $arguments = @('--capture-showcase', ('"' + $resolvedOutput + '"'), ('"' + $resolvedModel + '"'))
} else {
    $arguments = @('--capture-showcase', ('"' + $resolvedOutput + '"'))
}
$process = Start-Process -FilePath $resolvedExe -ArgumentList $arguments -WindowStyle Hidden -PassThru
$process.WaitForExit()
if ($process.ExitCode -ne 0) { throw ('Capture failed; inspect ' + $resolvedOutput) }
Write-Host ('Captured five actual pages: ' + $resolvedOutput)
