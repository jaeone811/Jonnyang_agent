"""실제 OS 어댑터. Windows 전용 호출은 전부 여기에만 있다."""

from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path

import psutil

from jonnyang.platform.base import BatteryInfo, DiskInfo, Platform, Unsupported


class PsutilSysInfo:
    def __init__(self):
        psutil.cpu_percent(interval=None)  # 첫 호출은 의미 없는 0.0이라 미리 한 번 부른다

    def cpu_percent(self) -> float:
        return psutil.cpu_percent(interval=0.3)

    def memory(self) -> tuple[int, int, float]:
        vm = psutil.virtual_memory()
        return vm.total - vm.available, vm.total, vm.percent

    def disks(self) -> list[DiskInfo]:
        out = []
        for part in psutil.disk_partitions(all=False):
            if "cdrom" in part.opts or not part.fstype:
                continue
            try:
                du = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            out.append(DiskInfo(part.mountpoint, du.used, du.total, du.percent))
        return out

    def battery(self) -> BatteryInfo | None:
        b = psutil.sensors_battery()
        if b is None:
            return None
        secs = b.secsleft if b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) else None
        return BatteryInfo(b.percent, b.power_plugged, secs)


class WindowsVolume:
    """pycaw>=20251023 API. GetSpeakers()가 AudioDevice 래퍼를 돌려준다.

    comtypes는 import한 스레드에서만 COM을 초기화하므로 메인 스레드에서만 부른다.
    """

    def _endpoint(self):
        from pycaw.pycaw import AudioUtilities

        return AudioUtilities.GetSpeakers().EndpointVolume

    def get(self) -> int:
        return round(self._endpoint().GetMasterVolumeLevelScalar() * 100)

    def set(self, percent: int) -> None:
        self._endpoint().SetMasterVolumeLevelScalar(max(0, min(100, percent)) / 100, None)

    def is_muted(self) -> bool:
        return bool(self._endpoint().GetMute())

    def set_mute(self, muted: bool) -> None:
        self._endpoint().SetMute(int(muted), None)


class UnsupportedVolume:
    def _fail(self, *args) -> int:
        raise Unsupported("volume")

    get = set = is_muted = set_mute = _fail


class WindowsLauncher:
    def open(self, target: str) -> None:
        if target.startswith("~") or "%" in target or re.match(r"^[A-Za-z]:[\\/]", target):
            target = os.path.normpath(os.path.expandvars(os.path.expanduser(target)))
        os.startfile(target)  # type: ignore[attr-defined]


class UnsupportedLauncher:
    def open(self, target: str) -> None:
        raise Unsupported("launcher")


# Windows Known Folder ID (KnownFolders.h). 바탕화면·문서가 OneDrive로 옮겨져 있어도 실제 위치를 알려준다.
KNOWN_FOLDERS = {
    "Desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "Documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "Downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "Music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "Pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "Videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}


def _known_folder_windows(name: str) -> Path | None:
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    u = uuid.UUID(KNOWN_FOLDERS[name])
    guid = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
    out = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32   # type: ignore[attr-defined]
    hr = shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out))
    try:
        return Path(out.value) if hr == 0 and out.value else None
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)   # type: ignore[attr-defined]


def resolve_folder(target: str) -> Path:
    """'known:Downloads' → 실제 다운로드 폴더, '~/x'·'%USERPROFILE%\\x' → 펼친 경로."""
    if target.startswith("known:"):
        name = target.split(":", 1)[1]
        if sys.platform == "win32" and name in KNOWN_FOLDERS:
            try:
                found = _known_folder_windows(name)
            except OSError:
                found = None
            if found:
                return found
        return Path.home() / name
    return Path(os.path.normpath(os.path.expandvars(os.path.expanduser(target))))


class SystemFiles:
    def folder(self, target: str) -> Path:
        return resolve_folder(target)

    def trash(self, paths: list[str]) -> None:
        from send2trash import send2trash

        send2trash(paths)


class WindowsBeeper:
    def beep(self) -> None:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)


class BellBeeper:
    def beep(self) -> None:
        sys.stdout.write("\a")
        sys.stdout.flush()


def system_platform() -> Platform:
    if sys.platform == "win32":
        return Platform(WindowsVolume(), WindowsLauncher(), PsutilSysInfo(), WindowsBeeper(), SystemFiles())
    return Platform(UnsupportedVolume(), UnsupportedLauncher(), PsutilSysInfo(), BellBeeper(), SystemFiles())
