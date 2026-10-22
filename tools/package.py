"""PyInstaller 결과 폴더를 배포용으로 정리하고 zip으로 묶는다.

사용법: python tools/package.py dist/Jonnyang
결과: dist/Jonnyang-<버전>-win64/ (폴더) 와 dist/Jonnyang-<버전>-win64.zip
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jonnyang import __version__  # noqa: E402


def main(built: Path) -> Path:
    name = f"Jonnyang-{__version__}-win64"
    out = built.parent / name
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(built, out / "Jonnyang")
    # 사람이 고치는 설정은 exe 옆에 둔다 (exe 안에 묶인 기본값보다 우선)
    shutil.copytree(ROOT / "config", out / "Jonnyang" / "config")
    shutil.copy(ROOT / "packaging" / "사용법.txt", out / "Jonnyang" / "사용법.txt")
    archive = shutil.make_archive(str(out), "zip", root_dir=out)
    print(f"folder: {out}\nzip: {archive}")
    return Path(archive)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist" / "Jonnyang"))
