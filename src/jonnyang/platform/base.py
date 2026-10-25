"""OS 기능 어댑터 인터페이스. 스킬은 이 인터페이스만 쓴다."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class Unsupported(Exception):
    """이 OS나 환경에서는 못 하는 기능."""


class VolumeControl(Protocol):
    def get(self) -> int: ...
    def set(self, percent: int) -> None: ...
    def is_muted(self) -> bool: ...
    def set_mute(self, muted: bool) -> None: ...


class Launcher(Protocol):
    def open(self, target: str) -> None: ...


@dataclass
class DiskInfo:
    mount: str
    used: int
    total: int
    percent: float


@dataclass
class BatteryInfo:
    percent: float
    plugged: bool | None
    secs_left: int | None      # None = 알 수 없음 또는 충전 중


class SysInfo(Protocol):
    def cpu_percent(self) -> float: ...
    def memory(self) -> tuple[int, int, float]: ...      # used, total, percent
    def disks(self) -> list[DiskInfo]: ...
    def battery(self) -> BatteryInfo | None: ...


class Beeper(Protocol):
    def beep(self) -> None: ...


class FileOps(Protocol):
    def folder(self, target: str) -> Path: ...          # 별칭 대상("known:Downloads", "~/x", "C:\\x") → 실제 경로
    def trash(self, paths: list[str]) -> None: ...      # 휴지통으로 (영구삭제 없음)


class NoFiles:
    def folder(self, target: str) -> Path:
        raise Unsupported("files")

    def trash(self, paths: list[str]) -> None:
        raise Unsupported("files")


@dataclass
class Platform:
    volume: VolumeControl
    launcher: Launcher
    sysinfo: SysInfo
    beeper: Beeper
    files: FileOps = field(default_factory=NoFiles)
