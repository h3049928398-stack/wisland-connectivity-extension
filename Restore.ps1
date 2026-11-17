param(
    [Parameter(Mandatory=$true)][string]$WislandRoot,
    [string]$Backup,
    [switch]$Check
)
$ErrorActionPreference = 'Stop'
$targetRoot = (Resolve-Path -LiteralPath $WislandRoot).Path
$pythonPath = Join-Path $targetRoot '.venv\Scripts\python.exe'
$restoreArgs = @('-B', (Join-Path $PSScriptRoot 'install.py'), $targetRoot, '--restore')
if ($Backup) { $restoreArgs += @('--backup', $Backup) }
if ($Check) { $restoreArgs += '--check' }
& $pythonPath @restoreArgs
if ($LASTEXITCODE -ne 0) { throw 'Restore validation failed; no unknown file will be overwritten.' }
