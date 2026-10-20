"""테스트용 가짜 OS. 실제 볼륨/앱/알림음은 건드리지 않는다."""

from __future__ import annotations

from jonnyang.platform.base import BatteryInfo, DiskInfo, Platform


class FakeVolume:
    def __init__(self, level: int = 40, muted: bool = False):
        self.level = level
        self.muted = muted

    def get(self) -> int:
        return self.level

    def set(self, percent: int) -> None:
        self.level = percent

    def is_muted(self) -> bool:
        return self.muted

    def set_mute(self, muted: bool) -> None:
        self.muted = muted


class FakeLauncher:
    def __init__(self):
        self.opened: list[str] = []

    def open(self, target: str) -> None:
        self.opened.append(target)


class FakeSysInfo:
    def __init__(self, battery: BatteryInfo | None = BatteryInfo(76.0, False, 3 * 3600 + 20 * 60)):
        self._battery = battery

    def cpu_percent(self) -> float:
        return 12.5

    def memory(self) -> tuple[int, int, float]:
        return 6 * 1024**3, 16 * 1024**3, 37.5

    def disks(self) -> list[DiskInfo]:
        return [DiskInfo("C:\\", 300 * 1024**3, 500 * 1024**3, 60.0)]

    def battery(self) -> BatteryInfo | None:
        return self._battery


class FakeBeeper:
    def __init__(self):
        self.count = 0

    def beep(self) -> None:
        self.count += 1


def fake_platform() -> Platform:
    return Platform(FakeVolume(), FakeLauncher(), FakeSysInfo(), FakeBeeper())
