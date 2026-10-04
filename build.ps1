$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Eine laufende Instanz sperrt die EXE und würde das Überschreiben verhindern.
Get-Process AutoBrightness -ErrorAction SilentlyContinue | Stop-Process -Force

try {
    python -m pip install -r requirements-dev.txt
    python -m PyInstaller --noconfirm --onefile --windowed --distpath . --name AutoBrightness `
        --collect-data customtkinter --collect-submodules screen_brightness_control `
        main.pyw
}
finally {
    # Übrig bleiben soll ausschließlich dist\AutoBrightness.exe.
    Remove-Item -Recurse -Force dist, build, AutoBrightness.spec, .pytest_cache -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "Fertig: dist\AutoBrightness.exe"
