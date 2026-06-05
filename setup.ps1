# Build all generated dashboard pages on Windows.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/6] Install Python dependencies"
pip install -r requirements.txt

Write-Host "[2/6] Fetch buoy data"
python fetch_buoys.py

Write-Host "[3/6] Build wave warning dashboard"
python build_dashboard.py

Write-Host "[4/6] Build fishing habitat dashboard"
python build_fishing.py

Write-Host "[5/6] Build high-resolution and forecast layers"
python build_hires.py
python build_forecast.py

Write-Host "[6/6] Build platform shell"
python build_platform.py

Write-Host "Done. Open dashboard/platform.html"
