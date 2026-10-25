"""설정 파일 위치와 로딩. 프로그램은 config/*.yaml을 읽기만 한다.

- 소스로 실행: 저장소의 config/, data/
- exe(PyInstaller)로 실행: exe 옆 config/ (사람이 고치는 파일, 없으면 exe에 묶인 기본값),
  데이터는 %LOCALAPPDATA%\\Jonnyang (exe 폴더를 새 버전으로 갈아끼워도 목록·리마인더가 남게)
- 환경변수 JONNYANG_CONFIG_DIR / JONNYANG_DATA_DIR가 있으면 그게 우선
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """사용자가 보는 프로그램 폴더 (exe가 있는 곳, 소스면 저장소)."""
    return Path(sys.executable).resolve().parent if frozen() else REPO_ROOT


def config_dir() -> Path:
    if "JONNYANG_CONFIG_DIR" in os.environ:
        return Path(os.environ["JONNYANG_CONFIG_DIR"])
    if frozen():
        beside = app_dir() / "config"
        return beside if beside.is_dir() else Path(getattr(sys, "_MEIPASS", app_dir())) / "config"
    return REPO_ROOT / "config"


def sprite_dir() -> Path:
    """펫 그림(스프라이트) 폴더. exe 옆에 sprites/가 있으면 그걸 쓴다(그림 바꿔 끼우기)."""
    if "JONNYANG_SPRITE_DIR" in os.environ:
        return Path(os.environ["JONNYANG_SPRITE_DIR"])
    if frozen():
        beside = app_dir() / "sprites"
        return beside if beside.is_dir() else Path(getattr(sys, "_MEIPASS", app_dir())) / "sprites"
    return Path(__file__).resolve().parents[1] / "gui" / "sprites"


def data_dir() -> Path:
    if "JONNYANG_DATA_DIR" in os.environ:
        return Path(os.environ["JONNYANG_DATA_DIR"])
    if frozen():
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "Jonnyang" if base else Path.home() / ".jonnyang"
    return REPO_ROOT / "data"


def load_yaml(name: str, directory: Path | None = None) -> dict[str, Any]:
    path = (directory or config_dir()) / name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
