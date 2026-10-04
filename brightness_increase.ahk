; Open Action Center
Send("#{a}")
Sleep(500)

; Move mouse to approximate position des Helligkeitsreglers
; (Position musst du an dein Display anpassen)
MouseMove, 1000, 1050  ; Beispiel-Koordinaten, anpassen
Sleep, 200

; Klick auf den Regler (links = dunkler, rechts = heller)
Click
Sleep, 200

; Bewege Maus nach rechts, um Helligkeit zu erhöhen
MouseMove, 50, 0, 10, R  ; relative Bewegung nach rechts
Click
Sleep, 200

; Close Action Center
Send("{Esc}")
