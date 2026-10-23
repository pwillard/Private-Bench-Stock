# Run ecDB locally on Windows for testing.
#   .\run_local.ps1                       -> http://127.0.0.1:8080  (uses .\instance\ecdb.sqlite3)
#   .\run_local.ps1 -Media C:\dev\claude\ecdb\html   (serve sheets/appnotes/img/parts from the old site folder)
param(
    [string]$Media = "",
    [int]$Port = 8080
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}
if ($Media) { $env:ECDB_MEDIA_ROOT = $Media }
.\.venv\Scripts\python.exe manage.py serve --host 127.0.0.1 --port $Port
