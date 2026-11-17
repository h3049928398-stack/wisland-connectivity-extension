param(
    [Parameter(Mandatory=$true)][string]$WislandRoot,
    [string]$AirDropExecutable,
    [switch]$Check,
    [switch]$SkipDependencies
)
$ErrorActionPreference = 'Stop'
$targetRoot = (Resolve-Path -LiteralPath $WislandRoot).Path
$pythonPath = Join-Path $targetRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'wisland Python environment not found.' }
if (-not $Check -and -not $SkipDependencies) {
    & $pythonPath -m pip install -r (Join-Path $PSScriptRoot 'requirements-extension.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
$installArgs = @('-B', (Join-Path $PSScriptRoot 'install.py'), $targetRoot)
if ($AirDropExecutable) { $installArgs += @('--airdrop-executable', $AirDropExecutable) }
if ($Check) { $installArgs += '--check' }
& $pythonPath @installArgs
if ($LASTEXITCODE -ne 0) { throw 'Extension validation or installation failed.' }
