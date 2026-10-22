"""존냥이 그리기. 이미지 파일 없이 QPainter 도형으로만 그린다.

200x180 설계 캔버스에 그리고 위젯 크기에 맞춰 늘린다. 색은 persona.yaml appearance에서 온다.
표정(pose): idle happy confused alert ask sleep think listen
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen

CANVAS_W, CANVAS_H = 200.0, 180.0
POSES = ("idle", "happy", "confused", "alert", "ask", "sleep", "think", "listen")

DEFAULT_COLORS = {
    "body": "#F6B46B", "stripe": "#E08A3C", "belly": "#FFF4E3", "outline": "#8A5A36",
    "ear_inner": "#FFB8C6", "eye": "#3A2E2E", "blush": "#FF9AAE", "nose": "#F2789A",
}


@dataclass
class CatFrame:
    """한 프레임을 그리는 데 필요한 상태."""
    pose: str = "idle"
    t: float = 0.0               # 초 단위 시간 (숨쉬기·꼬리 흔들기)
    pose_t: float = 0.0          # 이 표정이 된 지 몇 초
    blink: float = 0.0           # 0 = 뜬 눈, 1 = 감은 눈
    look: tuple[float, float] = (0.0, 0.0)   # 눈동자 방향 (-1~1)
    heart_t: float | None = None  # 쓰다듬기 하트가 뜬 지 몇 초


class CatPainter:
    def __init__(self, colors: dict | None = None):
        c = {**DEFAULT_COLORS, **{k: v for k, v in (colors or {}).items() if isinstance(v, str)}}
        self.c = {k: QColor(v) for k, v in c.items()}

    def _pen(self, color: QColor, width: float) -> QPen:
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return pen

    # ── 진입점 ──
    def paint(self, p: QPainter, rect: QRectF, f: CatFrame) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(rect.width() / CANVAS_W, rect.height() / CANVAS_H)
        p.translate(rect.center().x() - CANVAS_W * scale / 2, rect.center().y() - CANVAS_H * scale / 2)
        p.scale(scale, scale)

        jump, shake = self._motion(f)
        self._shadow(p, jump)
        p.translate(shake, -jump)
        breath = math.sin(f.t * (1.2 if f.pose == "sleep" else 2.2))
        self._tail(p, f)
        self._body(p, breath)
        p.save()
        tilt = {"ask": -9.0, "confused": 6.0}.get(f.pose, 0.0)
        sleep_drop = 5.0 if f.pose == "sleep" else 0.0
        p.translate(100, 120)
        p.rotate(tilt)
        p.translate(-100, -120 + breath * 1.4 + sleep_drop)
        self._ears(p, f)
        self._head(p)
        self._face(p, f)
        p.restore()
        p.translate(-shake, jump)
        self._marks(p, f)
        p.restore()

    def _motion(self, f: CatFrame) -> tuple[float, float]:
        if f.pose == "alert" and f.pose_t < 1.6:
            return abs(math.sin(f.pose_t * 9)) * 12 * (1 - f.pose_t / 1.6), math.sin(f.pose_t * 40) * 2
        if f.pose == "happy" and f.pose_t < 0.8:
            return abs(math.sin(f.pose_t * 8)) * 6, 0.0
        return 0.0, 0.0

    # ── 몸 ──
    def _shadow(self, p: QPainter, jump: float) -> None:
        w = 104 - jump * 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawEllipse(QPointF(100, 170), w / 2, 6)

    def _tail(self, p: QPainter, f: CatFrame) -> None:
        speed = 0.8 if f.pose == "sleep" else 2.0 if f.pose in ("happy", "alert") else 1.3
        sway = math.sin(f.t * speed) * (4 if f.pose == "sleep" else 12)
        path = QPainterPath(QPointF(132, 152))
        path.cubicTo(QPointF(170, 158), QPointF(178 + sway * 0.3, 128), QPointF(166 + sway, 98))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(self._pen(self.c["outline"], 17))
        p.drawPath(path)
        p.setPen(self._pen(self.c["body"], 13))
        p.drawPath(path)
        tip = QPainterPath(path.pointAtPercent(0.78))
        tip.lineTo(path.pointAtPercent(1.0))
        p.setPen(self._pen(self.c["stripe"], 13))
        p.drawPath(tip)

    def _body(self, p: QPainter, breath: float) -> None:
        p.setPen(self._pen(self.c["outline"], 2.5))
        p.setBrush(self.c["body"])
        h = 70 + breath * 1.5
        p.drawEllipse(QRectF(54, 167 - h, 92, h))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.c["belly"])
        p.drawEllipse(QRectF(76, 128, 48, 36))
        p.setPen(self._pen(self.c["outline"], 2.5))
        p.setBrush(self.c["body"])
        for x in (78, 122):
            p.drawEllipse(QPointF(x, 163), 13, 8)
        p.setPen(self._pen(self.c["outline"], 1.5))
        for x in (78, 122):
            p.drawLine(QPointF(x - 3, 160), QPointF(x - 3, 165))
            p.drawLine(QPointF(x + 3, 160), QPointF(x + 3, 165))

    # ── 머리 ──
    def _ears(self, p: QPainter, f: CatFrame) -> None:
        perk = 1.12 if f.pose in ("listen", "alert") else 0.9 if f.pose == "sleep" else 1.0
        twitch = 0.0
        if f.pose in ("idle", "think") and (f.t % 7.0) < 0.25:
            twitch = math.sin((f.t % 7.0) / 0.25 * math.pi) * 10
        for side in (-1, 1):
            p.save()
            base = QPointF(100 + side * 34, 46)
            p.translate(base)
            p.rotate(side * (8 + (twitch if side == 1 else 0)))
            p.scale(1.0, perk)
            outer = QPainterPath(QPointF(-20, 8))
            outer.lineTo(QPointF(side * 2, -40))
            outer.lineTo(QPointF(22, 6))
            outer.closeSubpath()
            inner = QPainterPath(QPointF(-11, 2))
            inner.lineTo(QPointF(side * 2, -28))
            inner.lineTo(QPointF(12, 1))
            inner.closeSubpath()
            p.setPen(self._pen(self.c["outline"], 2.5))
            p.setBrush(self.c["body"])
            p.drawPath(outer)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.c["ear_inner"])
            p.drawPath(inner)
            p.restore()

    def _head(self, p: QPainter) -> None:
        p.setPen(self._pen(self.c["outline"], 2.5))
        p.setBrush(self.c["body"])
        p.drawEllipse(QRectF(36, 28, 128, 100))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.c["belly"])
        p.drawEllipse(QRectF(72, 86, 56, 36))
        p.setPen(self._pen(self.c["stripe"], 5))
        for (x1, y1), (x2, y2) in (((89, 34), (91, 47)), ((100, 31), (100, 46)), ((111, 34), (109, 47))):
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.setPen(self._pen(self.c["stripe"], 4))
        for side in (-1, 1):
            p.drawLine(QPointF(100 + side * 60, 74), QPointF(100 + side * 50, 76))
            p.drawLine(QPointF(100 + side * 61, 84), QPointF(100 + side * 51, 84))

    def _face(self, p: QPainter, f: CatFrame) -> None:
        eye = self.c["eye"]
        lx, ly = f.look
        # 볼 터치
        p.setPen(Qt.PenStyle.NoPen)
        blush = QColor(self.c["blush"])
        blush.setAlpha(170 if f.pose in ("happy", "ask") else 120)
        p.setBrush(blush)
        p.drawEllipse(QPointF(64, 100), 10, 5.5)
        p.drawEllipse(QPointF(136, 100), 10, 5.5)

        pose = f.pose
        for side, cx in ((-1, 76.0), (1, 124.0)):
            cy = 82.0
            if pose == "sleep":
                self._closed_eye(p, cx, cy)
            elif pose == "happy":
                self._happy_eye(p, cx, cy)
            elif pose == "confused" and side == 1:
                p.setPen(self._pen(eye, 4))
                p.drawLine(QPointF(cx - 7, cy - 3), QPointF(cx + 6, cy + 1))
            else:
                big = pose == "alert"
                ox, oy = (3.0, -3.0) if pose == "think" else (lx * 3.0, ly * 2.0)
                openness = max(0.08, 1.0 - f.blink)
                w, h = (11.0, 13.0) if big else (8.5, 11.0)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(eye)
                p.drawEllipse(QPointF(cx + ox, cy + oy), w, h * openness)
                if openness > 0.5:
                    p.setBrush(QColor(255, 255, 255, 235))
                    p.drawEllipse(QPointF(cx + ox - w * 0.35, cy + oy - h * 0.4), w * 0.38, w * 0.38)
                    p.drawEllipse(QPointF(cx + ox + w * 0.35, cy + oy + h * 0.35), w * 0.16, w * 0.16)

        # 코
        nose = QPainterPath(QPointF(94, 95))
        nose.quadTo(QPointF(100, 92), QPointF(106, 95))
        nose.quadTo(QPointF(103, 100), QPointF(100, 101))
        nose.quadTo(QPointF(97, 100), QPointF(94, 95))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.c["nose"])
        p.drawPath(nose)

        # 입 (ω)
        p.setPen(self._pen(self.c["outline"], 2.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        mouth = QPainterPath(QPointF(100, 101))
        mouth.quadTo(QPointF(100, 107), QPointF(94, 107))
        mouth.quadTo(QPointF(90, 107), QPointF(89, 103))
        mouth.moveTo(QPointF(100, 101))
        mouth.quadTo(QPointF(100, 107), QPointF(106, 107))
        mouth.quadTo(QPointF(110, 107), QPointF(111, 103))
        p.drawPath(mouth)
        if pose in ("happy", "alert"):
            p.setPen(self._pen(self.c["outline"], 2))
            p.setBrush(QColor("#E05A6E"))
            p.drawChord(QRectF(94, 104, 12, 10 if pose == "alert" else 8), 180 * 16, 180 * 16)

        # 수염
        p.setPen(self._pen(QColor(self.c["outline"].red(), self.c["outline"].green(),
                                  self.c["outline"].blue(), 150), 1.6))
        for side in (-1, 1):
            p.drawLine(QPointF(100 + side * 30, 98), QPointF(100 + side * 52, 93))
            p.drawLine(QPointF(100 + side * 30, 103), QPointF(100 + side * 53, 104))

    def _closed_eye(self, p: QPainter, cx: float, cy: float) -> None:
        p.setPen(self._pen(self.c["eye"], 3.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(cx - 8, cy))
        path.quadTo(QPointF(cx, cy + 7), QPointF(cx + 8, cy))
        p.drawPath(path)

    def _happy_eye(self, p: QPainter, cx: float, cy: float) -> None:
        p.setPen(self._pen(self.c["eye"], 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(cx - 8, cy + 4))
        path.quadTo(QPointF(cx, cy - 8), QPointF(cx + 8, cy + 4))
        p.drawPath(path)

    def _mark_text(self, p: QPainter, at: QPointF, text: str, size: int, color: QColor) -> None:
        """배경화면 색과 상관없이 보이게 흰 테두리를 두른 글자."""
        font = QFont()
        font.setBold(True)
        font.setPixelSize(size)
        path = QPainterPath()
        path.addText(at, font, text)
        halo = QColor(255, 255, 255, color.alpha())
        p.setPen(self._pen(halo, 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(path)

    # ── 머리 위 기호 (?, !, zZ, …, 하트) ──
    def _marks(self, p: QPainter, f: CatFrame) -> None:
        if f.pose in ("confused", "ask"):
            color = QColor("#F5A524") if f.pose == "ask" else QColor("#8C7BD9")
            self._mark_text(p, QPointF(160, 34 + math.sin(f.t * 3) * 2), "?", 30, color)
        elif f.pose == "alert":
            self._mark_text(p, QPointF(162, 32), "!", 32, QColor("#E5484D"))
        elif f.pose == "sleep":
            for i in range(3):
                phase = (f.t * 0.5 + i / 3) % 1.0
                c = QColor(self.c["outline"])
                c.setAlpha(int(230 * (1 - phase)))
                self._mark_text(p, QPointF(150 + phase * 18 + i * 6, 46 - phase * 30 - i * 6), "z", 12 + i * 4, c)
        elif f.pose == "think":
            for i in range(3):
                a = 0.35 + 0.65 * max(0.0, math.sin(f.t * 4 - i * 0.9))
                c = QColor(self.c["outline"])
                c.setAlpha(int(255 * a))
                p.setPen(self._pen(QColor(255, 255, 255, int(255 * a)), 2))
                p.setBrush(c)
                p.drawEllipse(QPointF(156 + i * 10, 30), 3.5, 3.5)
        if f.heart_t is not None and f.heart_t < 1.4:
            k = f.heart_t / 1.4
            c = QColor("#FF6B8B")
            c.setAlpha(int(255 * (1 - k)))
            self._heart(p, QPointF(52 - k * 6, 30 - k * 26), 8 + k * 3, c)

    def _heart(self, p: QPainter, at: QPointF, size: float, color: QColor) -> None:
        x, y, s = at.x(), at.y(), size
        path = QPainterPath(QPointF(x, y + s * 0.9))
        path.cubicTo(QPointF(x - s * 1.4, y), QPointF(x - s * 0.6, y - s * 1.0), QPointF(x, y - s * 0.3))
        path.cubicTo(QPointF(x + s * 0.6, y - s * 1.0), QPointF(x + s * 1.4, y), QPointF(x, y + s * 0.9))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        p.drawPath(path)
