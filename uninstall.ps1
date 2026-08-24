param(
    [Parameter(Position=0)]
    [string]$Repo = (Get-Location).Path,
    [switch]$KeepMemory,
    [switch]$NoBackup
)
$ErrorActionPreference = "Stop"
$D = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Get-Command python -ErrorAction SilentlyContinue
if ($Python) {
    $A = @("$D\uninstall.py", $Repo)
    if ($KeepMemory) { $A += "--keep-memory" }
    if ($NoBackup) { $A += "--no-backup" }
    & $Python.Source @A
    exit $LASTEXITCODE
}
$Py = Get-Command py -ErrorAction SilentlyContinue
if ($Py) {
    $A = @("-3", "$D\uninstall.py", $Repo)
    if ($KeepMemory) { $A += "--keep-memory" }
    if ($NoBackup) { $A += "--no-backup" }
    & $Py.Source @A
    exit $LASTEXITCODE
}
Write-Error "Python 3 is required."
exit 1
