"""설정 파일 위치와 로딩. 프로그램은 config/*.yaml을 읽기만 한다."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def config_dir() -> Path:
    return Path(os.environ.get("JONNYANG_CONFIG_DIR", REPO_ROOT / "config"))


def data_dir() -> Path:
    return Path(os.environ.get("JONNYANG_DATA_DIR", REPO_ROOT / "data"))


def load_yaml(name: str, directory: Path | None = None) -> dict[str, Any]:
    path = (directory or config_dir()) / name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
