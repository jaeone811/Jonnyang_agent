"""데스크톱 펫 화면을 PNG로 뽑는다 (README·확인용). 화면 없이도 돈다.

사용법: QT_QPA_PLATFORM=offscreen python tools/render_pet.py docs/images
"""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from jonnyang.app import build_app  # noqa: E402
from jonnyang.core.storage import Storage  # noqa: E402
from jonnyang.gui.painter import POSES, CatFrame, CatPainter  # noqa: E402
from jonnyang.gui.window import WIN_H, WIN_W, PetWindow  # noqa: E402
from jonnyang.platform.fake import fake_platform  # noqa: E402


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 22, 14, 0)

    def __call__(self):
        return self.now


def wallpaper(w: int, h: int) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor("#3E5C76"))
    g.setColorAt(1, QColor("#1D2D44"))
    p.fillRect(img.rect(), g)
    p.end()
    return img


def shot(win: PetWindow, path: Path) -> None:
    QApplication.processEvents()
    pix = win.grab()
    img = wallpaper(WIN_W, WIN_H)
    p = QPainter(img)
    p.drawPixmap(QPoint(0, 0), pix)
    p.end()
    img.save(str(path))


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    clock = Clock()
    storage = Storage(":memory:")
    ctx, d = build_app(platform=fake_platform(), storage=storage, clock=clock, rng=random.Random(3), beep_gap=0)
    win = PetWindow(ctx.persona, storage, tray=False)
    win.move(0, 0)
    win.show()
    shot(win, out / "pet-loading.png")
    win.attach(ctx, d)
    win.submit("라면 타이머 4분")
    shot(win, out / "pet-reply.png")
    win.deadline = 0
    clock.now += timedelta(seconds=73)
    win.tick()
    shot(win, out / "pet-working.png")
    win.submit("쇼핑 목록에 우유랑 계란 추가해")
    win.submit("쇼핑 목록 비워줘")
    shot(win, out / "pet-confirm.png")
    win.submit("아니")
    clock.now += timedelta(minutes=3)
    ctx.scheduler.run_pending()
    app.processEvents()
    shot(win, out / "pet-alert.png")

    painter = CatPainter(ctx.persona.appearance)
    cols = 5
    rows = (len(POSES) + cols - 1) // cols
    sheet = QImage(180 * cols, 170 * rows, QImage.Format.Format_ARGB32)
    sheet.fill(QColor(0, 0, 0, 0))
    p = QPainter(sheet)
    for i, pose in enumerate(POSES):
        painter.paint(p, QRectF((i % cols) * 180, (i // cols) * 170, 180, 162),
                      CatFrame(pose=pose, t=1.0, pose_t=5.0))
    p.end()
    sheet.save(str(out / "pet-poses.png"))
    win.shutdown()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "docs" / "images"))
