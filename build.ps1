$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Eine laufende Instanz sperrt die EXE und würde das Überschreiben verhindern.
Get-Process LuxPC -ErrorAction SilentlyContinue | Stop-Process -Force

try {
    python -m pip install -r requirements-dev.txt
    python -c "from luxpc.icon import write_ico; write_ico('LuxPC.ico')"
    python -m PyInstaller --noconfirm --onefile --windowed --distpath . --icon LuxPC.ico --name LuxPC `
        --collect-data customtkinter --collect-submodules screen_brightness_control `
        main.pyw
}
finally {
    # Übrig bleiben soll ausschließlich LuxPC.exe.
    Remove-Item -Recurse -Force dist, build, LuxPC.spec, LuxPC.ico, .pytest_cache -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "Fertig: LuxPC.exe"
