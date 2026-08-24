param(
    [Parameter(Position=0)]
    [string]$Repo = (Get-Location).Path,
    [switch]$ShareTools
)
$ErrorActionPreference = "Stop"
$D = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Get-Command python -ErrorAction SilentlyContinue
if ($Python) {
    $A = @("$D\install.py", $Repo)
    if ($ShareTools) { $A += "--share-tools" }
    & $Python.Source @A
    exit $LASTEXITCODE
}
$Py = Get-Command py -ErrorAction SilentlyContinue
if ($Py) {
    $A = @("-3", "$D\install.py", $Repo)
    if ($ShareTools) { $A += "--share-tools" }
    & $Py.Source @A
    exit $LASTEXITCODE
}
Write-Error "Python 3 is required."
exit 1
