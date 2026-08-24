param([Parameter(Position=0)][string]$Repo = (Get-Location).Path)
$ErrorActionPreference = "Stop"
$D = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Get-Command python -ErrorAction SilentlyContinue
if ($Python) { & $Python.Source "$D\privacy_check.py" $Repo; exit $LASTEXITCODE }
$Py = Get-Command py -ErrorAction SilentlyContinue
if ($Py) { & $Py.Source -3 "$D\privacy_check.py" $Repo; exit $LASTEXITCODE }
Write-Error "Python 3 is required."
exit 1
