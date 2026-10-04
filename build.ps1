$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Eine laufende Instanz sperrt die EXE und würde das Überschreiben verhindern.
Get-Process AutoBrightness -ErrorAction SilentlyContinue | Stop-Process -Force

try {
    python -m pip install -r requirements-dev.txt
    python -c "from autobrightness.icon import write_ico; write_ico('AutoBrightness.ico')"
    python -m PyInstaller --noconfirm --onefile --windowed --distpath . --icon AutoBrightness.ico --name AutoBrightness `
        --collect-data customtkinter --collect-submodules screen_brightness_control `
        main.pyw
}
finally {
    # Übrig bleiben soll ausschließlich AutoBrightness.exe.
    Remove-Item -Recurse -Force dist, build, AutoBrightness.spec, AutoBrightness.ico, .pytest_cache -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "Fertig: AutoBrightness.exe"
