import cv2
import numpy as np
import subprocess

import os

#print(os.path.exists("ClickMonitorDDC_7_2.exe"))

def get_webcam_brightness():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise Exception("Webcam not accessible")
    
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise Exception("Failed to read frame")
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = np.mean(gray)
    return brightness

def brightness_to_percent(brightness):
    brightness = max(30, min(brightness, 200))
    percent = int((brightness - 30) / (200 - 30) * 100)
    return max(0, min(percent, 100))

def set_brightness_with_clickmonitorddc(percent):
    subprocess.run([
        r"C:\Users\pault\Desktop\Bildschirmhelligkeit\ClickMonitorDDC_7_2.exe",
        f"d{percent}"
    ])

# Main
try:
    webcam_brightness = get_webcam_brightness()
    brightness_percent = brightness_to_percent(webcam_brightness)
    set_brightness_with_clickmonitorddc(brightness_percent)
    print(f"Set brightness to {brightness_percent}% based on webcam")
except Exception as e:
    print(f"Error: {e}")
