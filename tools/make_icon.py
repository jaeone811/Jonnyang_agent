"""exe 아이콘(.ico)을 고양이 그림으로 만든다. Pillow 필요 (빌드할 때만).

사용법: python tools/make_icon.py build/jonnyang.ico
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jonnyang.core.config import load_yaml, sprite_dir  # noqa: E402
from jonnyang.gui.sprite import make_painter  # noqa: E402


def main(out: Path) -> None:
    QApplication.instance() or QApplication([])
    img = QImage(256, 256, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    persona = load_yaml("persona.yaml")
    make_painter(sprite_dir(), persona.get("sprites"), persona.get("appearance")).paint_icon(p, QRectF(0, 0, 256, 256))
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    pil = Image.open(io.BytesIO(bytes(buf.data())))
    out.parent.mkdir(parents=True, exist_ok=True)
    pil.save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"wrote {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "build" / "jonnyang.ico"))
