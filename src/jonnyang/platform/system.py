"""실제 OS 어댑터. Windows 전용 호출은 전부 여기에만 있다."""

from __future__ import annotations

import os
import re
import sys

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
        return Platform(WindowsVolume(), WindowsLauncher(), PsutilSysInfo(), WindowsBeeper())
    return Platform(UnsupportedVolume(), UnsupportedLauncher(), PsutilSysInfo(), BellBeeper())
