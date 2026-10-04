"""Minimaler DirectShow-Zugriff auf IAMCameraControl (Belichtung) per ctypes.

OpenCV kann den Kamera-Treiber nach manuellen Belichtungseingriffen nicht
zurück in den Automatikmodus versetzen; dieses Modul setzt dafür das
Flag KSPROPERTY_CAMERACONTROL_FLAGS_AUTO direkt über die COM-Schnittstelle.
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_long, c_ulong, c_void_p
from ctypes import wintypes
from typing import Optional

CAMERA_CONTROL_EXPOSURE = 4
FLAG_AUTO = 0x1
FLAG_MANUAL = 0x2

S_OK = 0
COINIT_APARTMENTTHREADED = 0x2


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, text: str) -> None:
        super().__init__()
        ole32.CLSIDFromString(ctypes.c_wchar_p("{" + text + "}"), byref(self))


ole32 = ctypes.OleDLL("ole32")
ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, POINTER(GUID)]

CLSID_SYSTEM_DEVICE_ENUM = "62BE5D10-60EB-11d0-BD3B-00A0C911CE86"
IID_ICREATE_DEV_ENUM = "29840822-5B84-11D0-BD3B-00A0C911CE86"
CLSID_VIDEO_INPUT_CATEGORY = "860BB310-5D01-11d0-BD3B-00A0C911CE86"
IID_IBASE_FILTER = "56a86895-0ad4-11ce-b03a-0020af0ba770"
IID_IAM_CAMERA_CONTROL = "C6E13370-30AC-11d0-A18C-00A0C9118956"


def _method(pointer: c_void_p, index: int, *argtypes):
    """Liefert die COM-Methode mit gegebenem vtable-Index als aufrufbare Funktion."""
    vtable = ctypes.cast(pointer, POINTER(POINTER(c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
    return prototype(vtable[index])


def _release(pointer: Optional[c_void_p]) -> None:
    if pointer:
        ctypes.WINFUNCTYPE(c_ulong, c_void_p)(
            ctypes.cast(pointer, POINTER(POINTER(c_void_p))).contents[2]
        )(pointer)


class CameraExposureControl:
    """Belichtungssteuerung einer DirectShow-Kamera (Index wie bei OpenCV CAP_DSHOW)."""

    def __init__(self, device_index: int) -> None:
        self._control = c_void_p()
        self._filter = c_void_p()
        ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        self._bind(device_index)

    def _bind(self, device_index: int) -> None:
        enumerator_factory = c_void_p()
        ole32.CoCreateInstance(
            byref(GUID(CLSID_SYSTEM_DEVICE_ENUM)), None, 1,
            byref(GUID(IID_ICREATE_DEV_ENUM)), byref(enumerator_factory),
        )
        monikers = c_void_p()
        hresult = _method(enumerator_factory, 3, POINTER(GUID), POINTER(c_void_p), c_ulong)(
            enumerator_factory, byref(GUID(CLSID_VIDEO_INPUT_CATEGORY)), byref(monikers), 0
        )
        _release(enumerator_factory)
        if hresult != S_OK or not monikers:
            raise RuntimeError("Keine Videoeingabegeräte gefunden")
        try:
            moniker = c_void_p()
            for _ in range(device_index + 1):
                _release(moniker)
                moniker = c_void_p()
                fetched = c_ulong()
                if _method(monikers, 3, c_ulong, POINTER(c_void_p), POINTER(c_ulong))(
                    monikers, 1, byref(moniker), byref(fetched)
                ) != S_OK or not fetched.value:
                    raise RuntimeError(f"Kamera {device_index} nicht gefunden")
            _method(moniker, 8, c_void_p, c_void_p, POINTER(GUID), POINTER(c_void_p))(
                moniker, None, None, byref(GUID(IID_IBASE_FILTER)), byref(self._filter)
            )
            _release(moniker)
        finally:
            _release(monikers)
        _method(self._filter, 0, POINTER(GUID), POINTER(c_void_p))(
            self._filter, byref(GUID(IID_IAM_CAMERA_CONTROL)), byref(self._control)
        )

    def exposure_range(self) -> tuple[int, int, int, int]:
        """(Minimum, Maximum, Schrittweite, Standard) in log2-Sekunden."""
        values = [c_long() for _ in range(4)]
        caps = c_long()
        _method(self._control, 3, c_long, *[POINTER(c_long)] * 5)(
            self._control, CAMERA_CONTROL_EXPOSURE, *[byref(entry) for entry in values], byref(caps)
        )
        return tuple(entry.value for entry in values)

    def get_exposure(self) -> tuple[int, bool]:
        """(Belichtung in log2-Sekunden, Automatik aktiv)."""
        value, flags = c_long(), c_long()
        _method(self._control, 5, c_long, POINTER(c_long), POINTER(c_long))(
            self._control, CAMERA_CONTROL_EXPOSURE, byref(value), byref(flags)
        )
        return value.value, bool(flags.value & FLAG_AUTO)

    def set_manual(self, exposure_log2_seconds: int) -> None:
        _method(self._control, 4, c_long, c_long, c_long)(
            self._control, CAMERA_CONTROL_EXPOSURE, int(exposure_log2_seconds), FLAG_MANUAL
        )

    def set_auto(self) -> None:
        value, _ = self.get_exposure()
        _method(self._control, 4, c_long, c_long, c_long)(
            self._control, CAMERA_CONTROL_EXPOSURE, value, FLAG_AUTO
        )

    def close(self) -> None:
        _release(self._control)
        _release(self._filter)
        self._control = c_void_p()
        self._filter = c_void_p()
