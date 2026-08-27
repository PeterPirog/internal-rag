param(
    [Parameter(Position=0)]
    [string]$Repo = (Get-Location).Path,
    [switch]$ShareTools,
    [ValidateSet("warp", "opencode", "opencode2", "jetbrains")]
    [string]$Client,
    [switch]$Global,
    [switch]$Compaction,
    [string]$ServerName,
    [switch]$Unregister
)
$ErrorActionPreference = "Stop"
$D = Split-Path -Parent $MyInvocation.MyCommand.Path

# Skip the Microsoft Store "WindowsApps" python stub (it launches the Store /
# an interactive REPL instead of running scripts).
function Is-StoreStub([string]$Path) {
    return (($Path -match "windowsapps") -and ($Path -match "python"))
}

# Pick a real Python invocation: prefer the `py` launcher (`py -3`), then a
# non-stub `python` on PATH.
function Resolve-Python() {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py -and -not (Is-StoreStub $py.Source)) { return @($py.Source, "-3") }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and -not (Is-StoreStub $python.Source)) { return @($python.Source) }
    throw "Python 3 is required (no working 'py'/'python' interpreter found; the WindowsApps stub is ignored)."
}

$Python = Resolve-Python

$A = @("$D\install.py", $Repo)
if ($ShareTools)  { $A += "--share-tools" }
if ($Client)      { $A += @("--client", $Client) }
if ($Global)      { $A += "--global" }
if ($Compaction)  { $A += "--compaction" }
if ($ServerName)  { $A += @("--server-name", $ServerName) }
if ($Unregister)  { $A += "--unregister" }

# Non-interactive: install.py answers EOF on input() prompts (its built-in
# default) — no interactive blocking possible from a wrapper.
$Exe = $Python[0]
if ($Python.Count -gt 1) {
    $Rest = @($Python[1..($Python.Count-1)]) + $A
} else {
    $Rest = $A
}
# Let install.py output flow through untouched.
& $Exe @Rest
exit $LASTEXITCODE
