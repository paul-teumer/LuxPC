$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --onefile --windowed --name AutoBrightness `
    --collect-data customtkinter --collect-submodules screen_brightness_control `
    main.pyw
Write-Host "Fertig: dist\AutoBrightness.exe"
