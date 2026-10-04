import subprocess

# Pfad zur AutoHotkey exe und Script
ahk_exe = r"C:\Users\pault\Desktop\Bildschirmhelligkeit\autohotkey\v2\AutoHotkey64.exe"
ahk_script = r"C:\Users\pault\Desktop\Bildschirmhelligkeit\brightness_increase.ahk"

subprocess.run([ahk_exe, ahk_script])
