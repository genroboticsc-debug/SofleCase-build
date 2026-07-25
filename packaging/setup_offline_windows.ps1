param(
    [string]$PythonExe = "$PSScriptRoot\portable_python\python-3.12.10-embed-amd64\python.exe",
    [string]$VenvDir = "$PSScriptRoot\venv"
)

$ErrorActionPreference = "Stop"
$Wheelhouse = Join-Path $PSScriptRoot "wheelhouse\windows_cp312_amd64"
$Requirements = Join-Path $PSScriptRoot "requirements-exact-windows-cp312.txt"

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}
if (-not (Test-Path $Wheelhouse)) {
    throw "Windows wheelhouse not found: $Wheelhouse"
}

# The embeddable distribution disables site-packages by default. Enable it.
$PythonHome = Split-Path $PythonExe
$Pth = Get-ChildItem $PythonHome -Filter "python312._pth" | Select-Object -First 1
if ($Pth) {
    $Lines = Get-Content $Pth.FullName
    $Lines = $Lines | ForEach-Object {
        if ($_ -eq "#import site") { "import site" } else { $_ }
    }
    Set-Content -Path $Pth.FullName -Value $Lines -Encoding ASCII
}

& $PythonExe "$PSScriptRoot\portable_python\get-pip.py" --no-index --find-links $Wheelhouse pip setuptools wheel
& $PythonExe -m pip install --no-index --find-links $Wheelhouse -r $Requirements
& $PythonExe -m pip check

Write-Host "Offline CAD environment ready."
& $PythonExe -c "import build123d, OCP; print('build123d', build123d.__version__); print('OCP/OpenCascade import OK')"
