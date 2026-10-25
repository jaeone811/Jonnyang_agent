"""테스트용 가짜 OS. 실제 볼륨/앱/알림음은 건드리지 않는다."""

from __future__ import annotations

import shutil
from pathlib import Path

from jonnyang.platform.base import BatteryInfo, DiskInfo, Platform, Unsupported


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


class FakeFiles:
    """임시 폴더 안에서만 동작한다. 'known:Downloads' → root/Downloads, '~' → root. 휴지통은 root/.trash로 옮긴다."""

    def __init__(self, root: Path | None = None):
        self.root = root
        self.trashed: list[str] = []

    def folder(self, target: str) -> Path:
        if self.root is None:
            raise Unsupported("files")
        if target.startswith("known:"):
            return self.root / target.split(":", 1)[1]
        if target.startswith("~"):
            return self.root / target[1:].lstrip("/\\")
        return Path(target)

    def trash(self, paths: list[str]) -> None:
        bin_dir = self.root / ".trash"
        bin_dir.mkdir(parents=True, exist_ok=True)
        for p in paths:
            shutil.move(p, bin_dir / Path(p).name)
            self.trashed.append(p)


def fake_platform(files_root: Path | None = None) -> Platform:
    return Platform(FakeVolume(), FakeLauncher(), FakeSysInfo(), FakeBeeper(), FakeFiles(files_root))
