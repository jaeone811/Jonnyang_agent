"""존냥이 그리기. 이미지 파일 없이 QPainter 도형으로만 그린다.

컨셉 아트 기준: 하얀 장모 고양이, 큰 파란 눈, 분홍 귀 안쪽, 금색 왕관(파란 보석), 남색 망토 + 금색 테두리,
가슴의 금색 브로치, 끝이 금빛인 꼬리. 200x180 설계 캔버스에 그리고 위젯 크기에 맞춰 늘린다.
색은 persona.yaml appearance에서 온다.

표정(pose):
  idle happy confused alert ask sleep think listen  ← 1단계부터 있던 것
  search(노트북) book(마법책) files(폴더 정리) sad love
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

CANVAS_W, CANVAS_H = 200.0, 180.0
POSES = ("idle", "happy", "confused", "alert", "ask", "sleep", "think", "listen",
         "search", "book", "files", "sad", "love")

DEFAULT_COLORS = {
    "fur": "#FFFFFF", "fur_shade": "#E6E3F6", "outline": "#9D98CC",
    "ear_inner": "#F8B5CD", "eye_top": "#1D2470", "eye_bottom": "#62A6FF", "eye_line": "#2A2458",
    "blush": "#FFB0C6", "nose": "#F28BA8", "mouth": "#7A5A8C", "tongue": "#FF8FA8",
    "cape": "#26306C", "cape_light": "#3B4796", "gold": "#F0C150", "gold_dark": "#B98A2C",
    "gem": "#3F7BFF", "tail_tip": "#F3C95E", "mark": "#5B8DEF", "sparkle": "#F5C443",
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

    def _alpha(self, key: str, a: int) -> QColor:
        c = QColor(self.c[key])
        c.setAlpha(a)
        return c

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
        sleeping = f.pose == "sleep"
        breath = math.sin(f.t * (1.2 if sleeping else 2.2))
        if f.pose == "book":
            self._magic_ring(p, f, back=True)
        self._tail(p, f)
        self._body(p, breath, sleeping)
        self._cape(p, breath, sleeping)
        if f.pose not in ("search", "book", "files"):
            self._paws(p, sleeping)
        p.save()
        tilt = {"ask": -8.0, "confused": 7.0, "think": -4.0, "sad": 4.0}.get(f.pose, 0.0)
        drop = 16.0 if sleeping else 3.0 if f.pose in ("search", "book", "files", "sad") else 0.0
        p.translate(100, 122)
        p.rotate(tilt + (-6.0 if sleeping else 0.0))
        p.translate(-100, -122 + breath * 1.3 + drop)
        self._ears(p, f)
        self._head(p)
        self._crown(p, f)
        self._face(p, f)
        p.restore()
        self._prop(p, f)
        p.translate(-shake, jump)
        self._marks(p, f)
        p.restore()

    def paint_icon(self, p: QPainter, rect: QRectF) -> None:
        """트레이·exe 아이콘 (얼굴이 꽉 차게 조금 크게 그린다)."""
        w, h = rect.width(), rect.height()
        self.paint(p, QRectF(rect.x() - w * 0.125, rect.y() - h * 0.03, w * 1.25, h * 1.125),
                   CatFrame(pose="happy", pose_t=5.0))

    def _motion(self, f: CatFrame) -> tuple[float, float]:
        if f.pose == "alert" and f.pose_t < 1.6:
            return abs(math.sin(f.pose_t * 9)) * 12 * (1 - f.pose_t / 1.6), math.sin(f.pose_t * 40) * 2
        if f.pose in ("happy", "love") and f.pose_t < 0.9:
            return abs(math.sin(f.pose_t * 7)) * 10 * (1 - f.pose_t / 0.9), 0.0
        if f.pose == "book":
            return 4 + math.sin(f.t * 2.4) * 3, 0.0          # 마법으로 살짝 떠 있다
        return 0.0, 0.0

    # ── 몸 ──
    def _shadow(self, p: QPainter, jump: float) -> None:
        w = 100 - jump * 2
        g = QRadialGradient(QPointF(100, 171), w / 2)
        g.setColorAt(0, QColor(60, 50, 120, 60))
        g.setColorAt(1, QColor(60, 50, 120, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(100, 171), w / 2, 7)

    def _tail(self, p: QPainter, f: CatFrame) -> None:
        speed = 0.8 if f.pose == "sleep" else 3.0 if f.pose in ("happy", "alert", "love") else 1.4
        sway = math.sin(f.t * speed) * (4 if f.pose == "sleep" else 11)
        if f.pose == "sleep":
            path = QPainterPath(QPointF(138, 160))
            path.cubicTo(QPointF(176, 166), QPointF(182 + sway * 0.3, 140), QPointF(160 + sway, 132))
        else:
            path = QPainterPath(QPointF(130, 156))
            path.cubicTo(QPointF(172, 160), QPointF(176 + sway * 0.4, 124), QPointF(160 + sway, 92))
        start, end = path.pointAtPercent(0), path.pointAtPercent(1)
        grad = QLinearGradient(start, end)
        grad.setColorAt(0.0, self.c["fur"])
        grad.setColorAt(0.45, self.c["fur"])
        grad.setColorAt(0.75, self.c["tail_tip"])
        grad.setColorAt(1.0, self.c["gold"])
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(self._pen(self.c["outline"], 24))
        p.drawPath(path)
        p.setPen(QPen(QBrush(grad), 20, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        # 끝의 털 뭉치
        tip = path.pointAtPercent(1.0)
        p.setPen(self._pen(self.c["gold_dark"], 1.6))
        for dx, dy in ((-4, -3), (2, -5), (5, 1)):
            p.drawLine(QPointF(tip.x() + dx * 0.4, tip.y() + dy * 0.4), QPointF(tip.x() + dx, tip.y() + dy))

    def _body(self, p: QPainter, breath: float, sleeping: bool) -> None:
        p.setPen(self._pen(self.c["outline"], 2.2))
        grad = QLinearGradient(QPointF(0, 110), QPointF(0, 170))
        grad.setColorAt(0, self.c["fur"])
        grad.setColorAt(1, self.c["fur_shade"])
        p.setBrush(QBrush(grad))
        if sleeping:
            p.drawEllipse(QRectF(46, 128 - breath * 1.2, 108, 42 + breath * 1.2))
            return
        h = 62 + breath * 1.4
        p.drawEllipse(QRectF(60, 168 - h, 80, h))

    def _paws(self, p: QPainter, sleeping: bool) -> None:
        p.setPen(self._pen(self.c["outline"], 2.0))
        p.setBrush(self.c["fur"])
        xs, y = ((70, 98), 162) if sleeping else ((86, 114), 163)
        for x in xs:
            p.drawEllipse(QPointF(x, y), 11, 7.5)
        p.setPen(self._pen(self.c["fur_shade"].darker(115), 1.3))
        for x in xs:
            for dx in (-3.5, 3.5):
                p.drawLine(QPointF(x + dx, y - 3), QPointF(x + dx, y + 1))

    def _cape(self, p: QPainter, breath: float, sleeping: bool) -> None:
        y0 = (130 if sleeping else 112) + breath * 0.6
        # 어깨를 덮고 양옆으로 흘러내리는 망토, 가운데는 V자로 열려 가슴 털이 보인다
        path = QPainterPath(QPointF(62, y0))
        path.cubicTo(QPointF(52, y0 + 18), QPointF(50, y0 + 36), QPointF(54, y0 + 48))
        path.quadTo(QPointF(64, y0 + 44), QPointF(72, y0 + 48))
        path.lineTo(QPointF(86, y0 + 30))
        path.lineTo(QPointF(100, y0 + 22))
        path.lineTo(QPointF(114, y0 + 30))
        path.lineTo(QPointF(128, y0 + 48))
        path.quadTo(QPointF(136, y0 + 44), QPointF(146, y0 + 48))
        path.cubicTo(QPointF(150, y0 + 36), QPointF(148, y0 + 18), QPointF(138, y0))
        path.quadTo(QPointF(100, y0 + 12), QPointF(62, y0))
        grad = QLinearGradient(QPointF(0, y0), QPointF(0, y0 + 48))
        grad.setColorAt(0, self.c["cape_light"])
        grad.setColorAt(1, self.c["cape"])
        p.setPen(self._pen(self.c["gold"], 2.6))
        p.setBrush(QBrush(grad))
        p.drawPath(path)
        # 가슴 털 한 줌 (브로치 아래)
        fluff = QPainterPath(QPointF(90, y0 + 30))
        for i, x in enumerate((92, 95, 98, 102, 105, 108, 110)):
            fluff.lineTo(QPointF(x, y0 + (42 if i % 2 == 0 else 37)))
        fluff.quadTo(QPointF(100, y0 + 26), QPointF(90, y0 + 30))
        p.setPen(self._pen(self.c["fur_shade"], 1.2))
        p.setBrush(self.c["fur"])
        p.drawPath(fluff)
        # 브로치
        bx, by = 100, y0 + 25
        p.setPen(self._pen(self.c["gold_dark"], 1.6))
        p.setBrush(self.c["gold"])
        p.drawEllipse(QPointF(bx, by), 8, 8)
        g = QRadialGradient(QPointF(bx - 1.5, by - 1.5), 6)
        g.setColorAt(0, QColor(self.c["gem"]).lighter(160))
        g.setColorAt(1, self.c["gem"])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(bx, by), 5, 5)
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawEllipse(QPointF(bx - 1.8, by - 1.8), 1.5, 1.5)

    # ── 머리 ──
    def _ears(self, p: QPainter, f: CatFrame) -> None:
        perk = {"listen": 1.12, "alert": 1.15, "sleep": 0.85, "sad": 0.8, "confused": 0.92}.get(f.pose, 1.0)
        droop = {"sad": 22.0, "sleep": 10.0, "confused": 8.0}.get(f.pose, 0.0)
        twitch = 0.0
        if f.pose in ("idle", "think", "search") and (f.t % 7.0) < 0.25:
            twitch = math.sin((f.t % 7.0) / 0.25 * math.pi) * 10
        for side in (-1, 1):
            p.save()
            p.translate(QPointF(100 + side * 36, 50))
            p.rotate(side * (14 + droop + (twitch if side == 1 else 0)))
            p.scale(1.0, perk)
            outer = QPainterPath(QPointF(-22, 10))
            outer.quadTo(QPointF(-10, -26), QPointF(side * 2, -44))
            outer.quadTo(QPointF(14, -24), QPointF(24, 8))
            outer.closeSubpath()
            inner = QPainterPath(QPointF(-16, 6))
            inner.quadTo(QPointF(-8, -22), QPointF(side * 2, -37))
            inner.quadTo(QPointF(11, -20), QPointF(17, 5))
            inner.closeSubpath()
            p.setPen(self._pen(self.c["outline"], 2.2))
            p.setBrush(self.c["fur"])
            p.drawPath(outer)
            g = QLinearGradient(QPointF(0, -33), QPointF(0, 4))
            g.setColorAt(0, self.c["ear_inner"])
            g.setColorAt(1, self._alpha("ear_inner", 90))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawPath(inner)
            p.setPen(self._pen(self.c["fur"], 1.6))       # 귀 속 털
            for dx in (-4, 2):
                p.drawLine(QPointF(dx, 4), QPointF(dx * 1.6 + side, -10))
            p.restore()

    def _head(self, p: QPainter) -> None:
        head = QPainterPath()
        head.addEllipse(QRectF(36, 30, 128, 102))
        tufts = QPainterPath(QPointF(40, 94))          # 볼 털 (양옆 삐죽)
        tufts.lineTo(QPointF(31, 102))
        tufts.lineTo(QPointF(42, 105))
        tufts.lineTo(QPointF(36, 113))
        tufts.lineTo(QPointF(52, 115))
        tufts.closeSubpath()
        tufts.moveTo(QPointF(160, 94))
        tufts.lineTo(QPointF(169, 102))
        tufts.lineTo(QPointF(158, 105))
        tufts.lineTo(QPointF(164, 113))
        tufts.lineTo(QPointF(148, 115))
        tufts.closeSubpath()
        tufts.moveTo(QPointF(90, 33))                  # 정수리 털
        tufts.lineTo(QPointF(96, 22))
        tufts.lineTo(QPointF(100, 31))
        tufts.lineTo(QPointF(106, 24))
        tufts.lineTo(QPointF(110, 33))
        tufts.closeSubpath()
        shape = head.united(tufts)
        grad = QRadialGradient(QPointF(92, 66), 92)
        grad.setColorAt(0.0, self.c["fur"])
        grad.setColorAt(0.75, self.c["fur"])
        grad.setColorAt(1.0, self.c["fur_shade"])
        p.setPen(self._pen(self.c["outline"], 2.2))
        p.setBrush(QBrush(grad))
        p.drawPath(shape)
        # 이마의 연보라 털 결
        p.setPen(self._pen(self._alpha("fur_shade", 255).darker(108), 2.2))
        for (x1, y1), (x2, y2) in (((88, 44), (91, 54)), ((112, 44), (109, 54))):
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _crown(self, p: QPainter, f: CatFrame) -> None:
        p.save()
        p.translate(100, 30)
        p.rotate(-6 if f.pose != "sleep" else -14)
        path = QPainterPath(QPointF(-20, 6))
        path.lineTo(QPointF(-22, -8))
        path.lineTo(QPointF(-12, -1))
        path.lineTo(QPointF(0, -18))
        path.lineTo(QPointF(12, -1))
        path.lineTo(QPointF(22, -8))
        path.lineTo(QPointF(20, 6))
        path.quadTo(QPointF(0, 10), QPointF(-20, 6))
        g = QLinearGradient(QPointF(0, -18), QPointF(0, 8))
        g.setColorAt(0, QColor(self.c["gold"]).lighter(118))
        g.setColorAt(1, self.c["gold"])
        p.setPen(self._pen(self.c["gold_dark"], 1.6))
        p.setBrush(QBrush(g))
        p.drawPath(path)
        p.setBrush(self.c["gold"])
        for x, y in ((-22, -8), (0, -18), (22, -8)):
            p.drawEllipse(QPointF(x, y), 2.6, 2.6)
        gem = QPainterPath(QPointF(0, -7))
        gem.lineTo(QPointF(4.5, -1))
        gem.lineTo(QPointF(0, 5))
        gem.lineTo(QPointF(-4.5, -1))
        gem.closeSubpath()
        p.setPen(self._pen(self.c["gold_dark"], 1.0))
        p.setBrush(self.c["gem"])
        p.drawPath(gem)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 210))
        p.drawEllipse(QPointF(-1.2, -2.5), 1.2, 1.6)
        for x in (-12, 12):
            p.setBrush(self.c["gem"])
            p.drawEllipse(QPointF(x, 3), 1.8, 1.8)
        p.restore()

    def _face(self, p: QPainter, f: CatFrame) -> None:
        pose = f.pose
        # 볼 터치
        p.setPen(Qt.PenStyle.NoPen)
        for cx in (64, 136):
            g = QRadialGradient(QPointF(cx, 104), 12)
            g.setColorAt(0, self._alpha("blush", 190 if pose in ("happy", "love", "ask") else 130))
            g.setColorAt(1, self._alpha("blush", 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(cx, 104), 13, 8)

        for side, cx in ((-1, 76.0), (1, 124.0)):
            cy = 86.0
            if pose == "sleep":
                self._arc_eye(p, cx, cy, down=True)
            elif pose == "happy" or (pose == "love" and side == 1):
                self._arc_eye(p, cx, cy, down=False)
            elif pose == "confused":
                self._chevron_eye(p, cx, cy, side)
            else:
                big = pose == "alert"
                if pose in ("search", "book", "files"):
                    look = (0.0, 0.7)                        # 손에 든 것을 본다
                elif pose == "think":
                    look = (0.6, -0.8)
                else:
                    look = f.look
                self._eye(p, cx, cy, side, look, max(0.06, 1.0 - f.blink), big, small_pupil=big)
                if pose == "sad" and side == -1:
                    self._tear(p, cx - 6, cy + 16, f.t)
        if pose == "sad":
            p.setPen(self._pen(self.c["eye_line"], 2.2))
            for side, cx in ((-1, 76.0), (1, 124.0)):
                p.drawLine(QPointF(cx - side * 10, 66), QPointF(cx + side * 4, 62))

        # 코
        nose = QPainterPath(QPointF(95, 101))
        nose.quadTo(QPointF(100, 98.5), QPointF(105, 101))
        nose.quadTo(QPointF(102.5, 105), QPointF(100, 105.5))
        nose.quadTo(QPointF(97.5, 105), QPointF(95, 101))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.c["nose"])
        p.drawPath(nose)
        self._mouth(p, pose)

        # 수염
        p.setPen(self._pen(self._alpha("outline", 140), 1.3))
        for side in (-1, 1):
            p.drawLine(QPointF(100 + side * 34, 104), QPointF(100 + side * 58, 99))
            p.drawLine(QPointF(100 + side * 34, 109), QPointF(100 + side * 59, 110))

    def _mouth(self, p: QPainter, pose: str) -> None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(self._pen(self.c["mouth"], 1.8))
        if pose in ("happy", "alert", "love", "listen"):
            open_h = {"alert": 11.0, "listen": 6.0}.get(pose, 9.0)
            m = QPainterPath(QPointF(93, 108))
            m.quadTo(QPointF(100, 106), QPointF(107, 108))
            m.quadTo(QPointF(106, 108 + open_h), QPointF(100, 108 + open_h))
            m.quadTo(QPointF(94, 108 + open_h), QPointF(93, 108))
            p.setBrush(QColor("#9B3E5C"))
            p.drawPath(m)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.c["tongue"])
            p.drawEllipse(QPointF(100, 108 + open_h * 0.75), 4.2, open_h * 0.3)
            return
        if pose == "sad":
            m = QPainterPath(QPointF(94, 112))
            m.quadTo(QPointF(100, 107), QPointF(106, 112))
            p.drawPath(m)
            return
        if pose == "confused":
            m = QPainterPath(QPointF(92, 111))
            m.cubicTo(QPointF(96, 107), QPointF(98, 115), QPointF(101, 111))
            m.cubicTo(QPointF(104, 107), QPointF(106, 115), QPointF(109, 111))
            p.drawPath(m)
            return
        m = QPainterPath(QPointF(100, 105.5))                # ω
        m.quadTo(QPointF(100, 111), QPointF(95, 111))
        m.quadTo(QPointF(91.5, 111), QPointF(91, 108))
        m.moveTo(QPointF(100, 105.5))
        m.quadTo(QPointF(100, 111), QPointF(105, 111))
        m.quadTo(QPointF(108.5, 111), QPointF(109, 108))
        p.drawPath(m)

    def _eye(self, p: QPainter, cx: float, cy: float, side: int, look: tuple[float, float], openness: float,
             big: bool, small_pupil: bool = False) -> None:
        w, h = (14.0, 17.5) if big else (12.5, 16.0)
        if openness < 0.3:
            self._arc_eye(p, cx, cy + 2, down=True)
            return
        ox, oy = look[0] * 2.5, look[1] * 2.0
        p.save()
        p.translate(cx, cy)
        p.scale(1.0, openness)
        g = QLinearGradient(QPointF(0, -h), QPointF(0, h))
        g.setColorAt(0.0, self.c["eye_top"])
        g.setColorAt(0.55, QColor(self.c["eye_bottom"]).darker(120))
        g.setColorAt(1.0, self.c["eye_bottom"])
        p.setPen(self._pen(self.c["eye_line"], 1.4))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(0, 0), w, h)
        pw, ph = (w * 0.32, h * 0.38) if small_pupil else (w * 0.5, h * 0.55)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.c["eye_top"]).darker(150))
        p.drawEllipse(QPointF(ox, oy - 1), pw, ph)
        p.setBrush(QColor(255, 255, 255, 240))
        p.drawEllipse(QPointF(ox - w * 0.38, oy - h * 0.42), w * 0.36, h * 0.3)
        p.drawEllipse(QPointF(ox + w * 0.38, oy + h * 0.38), w * 0.14, w * 0.14)
        p.setBrush(QColor(200, 230, 255, 170))
        p.drawEllipse(QPointF(ox + w * 0.1, oy + h * 0.62), w * 0.42, h * 0.14)
        p.restore()
        # 윗눈꺼풀 선 + 바깥쪽 속눈썹
        top = cy - h * openness
        lid = QPainterPath(QPointF(cx - w - 1, cy - h * openness * 0.35))
        lid.quadTo(QPointF(cx, top - 4), QPointF(cx + w + 1, cy - h * openness * 0.35))
        p.setPen(self._pen(self.c["eye_line"], 3.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(lid)
        ex = cx + side * (w + 1)
        p.drawLine(QPointF(ex, cy - h * openness * 0.35), QPointF(ex + side * 5, cy - h * openness * 0.55 - 3))

    def _arc_eye(self, p: QPainter, cx: float, cy: float, down: bool) -> None:
        p.setPen(self._pen(self.c["eye_line"], 3.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(cx - 10, cy + (0 if down else 4)))
        path.quadTo(QPointF(cx, cy + (8 if down else -9)), QPointF(cx + 10, cy + (0 if down else 4)))
        p.drawPath(path)

    def _chevron_eye(self, p: QPainter, cx: float, cy: float, side: int) -> None:
        """><  눈."""
        p.setPen(self._pen(self.c["eye_line"], 3.6))
        d = -side
        path = QPainterPath(QPointF(cx - d * 8, cy - 7))
        path.lineTo(QPointF(cx + d * 6, cy))
        path.lineTo(QPointF(cx - d * 8, cy + 7))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def _tear(self, p: QPainter, x: float, y: float, t: float) -> None:
        k = (t * 0.7) % 1.0
        path = QPainterPath(QPointF(x, y + k * 10 - 4))
        path.quadTo(QPointF(x + 4, y + k * 10 + 3), QPointF(x, y + k * 10 + 5))
        path.quadTo(QPointF(x - 4, y + k * 10 + 3), QPointF(x, y + k * 10 - 4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(120, 180, 255, int(220 * (1 - k * 0.6))))
        p.drawPath(path)

    # ── 손에 든 것 (노트북 / 마법책 / 폴더) ──
    def _prop(self, p: QPainter, f: CatFrame) -> None:
        if f.pose == "search":
            self._laptop(p, f)
        elif f.pose == "book":
            self._book(p, f)
        elif f.pose == "files":
            self._folders(p, f)

    def _paw_on(self, p: QPainter, x: float, y: float) -> None:
        p.setPen(self._pen(self.c["outline"], 2.0))
        p.setBrush(self.c["fur"])
        p.drawEllipse(QPointF(x, y), 9, 6.5)

    def _laptop(self, p: QPainter, f: CatFrame) -> None:
        # 화면 뒷면 (고양이 쪽에서 보면 뚜껑 뒤가 보인다)
        lid = QPainterPath(QPointF(68, 160))
        lid.lineTo(QPointF(72, 128))
        lid.lineTo(QPointF(128, 128))
        lid.lineTo(QPointF(132, 160))
        lid.closeSubpath()
        p.setPen(self._pen(QColor("#151B45"), 2))
        g = QLinearGradient(QPointF(0, 128), QPointF(0, 160))
        g.setColorAt(0, self.c["cape_light"])
        g.setColorAt(1, self.c["cape"])
        p.setBrush(QBrush(g))
        p.drawPath(lid)
        # 창 로고
        glow = QColor("#8FD3FF")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        for dx, dy in ((0, 0), (7, 0), (0, 7), (7, 7)):
            p.drawRect(QRectF(93 + dx, 136 + dy, 6, 6))
        # 키보드 받침
        base = QPainterPath(QPointF(60, 160))
        base.lineTo(QPointF(140, 160))
        base.lineTo(QPointF(146, 168))
        base.lineTo(QPointF(54, 168))
        base.closeSubpath()
        p.setPen(self._pen(QColor("#151B45"), 2))
        p.setBrush(self.c["cape"])
        p.drawPath(base)
        tap = math.sin(f.t * 14) > 0                   # 타닥타닥
        self._paw_on(p, 72, 157 + (2 if tap else 0))
        self._paw_on(p, 128, 157 + (0 if tap else 2))

    def _book(self, p: QPainter, f: CatFrame) -> None:
        cx, y = 100.0, 150.0
        for side in (-1, 1):
            page = QPainterPath(QPointF(cx, y))
            page.quadTo(QPointF(cx + side * 18, y - 8), QPointF(cx + side * 38, y - 3))
            page.lineTo(QPointF(cx + side * 36, y + 14))
            page.quadTo(QPointF(cx + side * 18, y + 8), QPointF(cx, y + 16))
            page.closeSubpath()
            p.setPen(self._pen(self.c["gold_dark"], 1.6))
            p.setBrush(self.c["cape"])
            p.drawPath(page.translated(0, 3))
            p.setBrush(QColor("#FFF8E6"))
            p.drawPath(page)
            p.setPen(self._pen(QColor(150, 140, 190, 150), 1.1))
            for i in range(3):
                yy = y + 3 + i * 3.5
                p.drawLine(QPointF(cx + side * 8, yy), QPointF(cx + side * 30, yy - 2))
        # 책에서 올라오는 빛
        for i in range(4):
            k = (f.t * 0.6 + i / 4) % 1.0
            c = QColor(self.c["sparkle"] if i % 2 else self.c["mark"])
            c.setAlpha(int(230 * (1 - k)))
            self._sparkle(p, QPointF(cx - 24 + i * 16, y - 6 - k * 34), 3 + 2 * (1 - k), c)
        self._paw_on(p, cx - 30, y + 10)
        self._paw_on(p, cx + 30, y + 10)

    def _magic_ring(self, p: QPainter, f: CatFrame, back: bool) -> None:
        p.save()
        p.translate(100, 160)
        p.scale(1.0, 0.32)
        for i, key in enumerate(("mark", "sparkle")):
            c = self._alpha(key, 120)
            pen = self._pen(c, 3.0 - i)
            pen.setDashPattern([6, 4])
            pen.setDashOffset(f.t * (8 if i == 0 else -6))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(0, 0), 70 - i * 10, 70 - i * 10)
        p.restore()

    def _folders(self, p: QPainter, f: CatFrame) -> None:
        bob = math.sin(f.t * 3) * 1.5
        for i, (x, color) in enumerate(((70, "#F3C95E"), (100, "#8FB8FF"), (130, "#F3C95E"))):
            y = 146 + (bob if i == 1 else -bob)
            path = QPainterPath(QPointF(x - 16, y))
            path.lineTo(QPointF(x - 16, y - 16))
            path.lineTo(QPointF(x - 6, y - 16))
            path.lineTo(QPointF(x - 2, y - 12))
            path.lineTo(QPointF(x + 16, y - 12))
            path.lineTo(QPointF(x + 16, y))
            path.closeSubpath()
            p.setPen(self._pen(QColor(color).darker(140), 1.6))
            p.setBrush(QColor(color))
            p.drawPath(path)
        self._paw_on(p, 84, 152)
        self._paw_on(p, 116, 152)

    # ── 머리 위 기호 ──
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

    def _sparkle(self, p: QPainter, at: QPointF, r: float, color: QColor) -> None:
        """네 갈래 반짝이."""
        x, y = at.x(), at.y()
        path = QPainterPath(QPointF(x, y - r * 2))
        path.quadTo(QPointF(x, y), QPointF(x + r * 2, y))
        path.quadTo(QPointF(x, y), QPointF(x, y + r * 2))
        path.quadTo(QPointF(x, y), QPointF(x - r * 2, y))
        path.quadTo(QPointF(x, y), QPointF(x, y - r * 2))
        p.setPen(self._pen(QColor(255, 255, 255, color.alpha()), 1.5))
        p.setBrush(color)
        p.drawPath(path)

    def _marks(self, p: QPainter, f: CatFrame) -> None:
        pose = f.pose
        if pose == "ask":
            self._mark_text(p, QPointF(158, 36 + math.sin(f.t * 3) * 2), "?", 30, self.c["mark"])
        elif pose == "confused":
            self._swirl(p, QPointF(166, 26), f.t)
        elif pose == "alert":
            self._mark_text(p, QPointF(160, 34), "!", 32, QColor("#FF5C8A"))
        elif pose == "sleep":
            for i in range(3):
                phase = (f.t * 0.5 + i / 3) % 1.0
                c = self._alpha("mark", int(230 * (1 - phase)))
                self._mark_text(p, QPointF(148 + phase * 18 + i * 6, 62 - phase * 30 - i * 6), "z", 12 + i * 4, c)
        elif pose in ("think", "search"):
            for i in range(3):
                a = 0.35 + 0.65 * max(0.0, math.sin(f.t * 4 - i * 0.9))
                p.setPen(self._pen(QColor(255, 255, 255, int(255 * a)), 2))
                p.setBrush(self._alpha("mark", int(255 * a)))
                p.drawEllipse(QPointF(154 + i * 10, 34), 3.5, 3.5)
        elif pose == "happy":
            for i, (x, y) in enumerate(((34, 40), (166, 52), (24, 84))):
                k = 0.6 + 0.4 * math.sin(f.t * 5 + i * 2)
                self._sparkle(p, QPointF(x, y), 3.5 * k + 1, self._alpha("sparkle", int(255 * k)))
        elif pose == "love":
            for i in range(2):
                k = (f.t * 0.5 + i / 2) % 1.0
                c = QColor("#FF6B9A")
                c.setAlpha(int(255 * (1 - k)))
                self._heart(p, QPointF(150 + i * 16, 50 - k * 28), 6 + i * 2, c)
        elif pose == "sad":
            p.setPen(self._pen(self._alpha("mark", 160), 2))
            for i in range(3):
                x = 150 + i * 8
                p.drawLine(QPointF(x, 30 + i * 2), QPointF(x - 2, 40 + i * 2))
        if f.heart_t is not None and f.heart_t < 1.4:
            k = f.heart_t / 1.4
            c = QColor("#FF6B9A")
            c.setAlpha(int(255 * (1 - k)))
            self._heart(p, QPointF(48 - k * 6, 34 - k * 26), 8 + k * 3, c)

    def _swirl(self, p: QPainter, at: QPointF, t: float) -> None:
        path = QPainterPath()
        for i in range(60):
            a = i / 60 * math.pi * 4 + t * 4
            r = 1 + i / 60 * 10
            pt = QPointF(at.x() + math.cos(a) * r, at.y() + math.sin(a) * r)
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(self._pen(QColor(255, 255, 255, 230), 5))
        p.drawPath(path)
        p.setPen(self._pen(QColor("#7B6FD6"), 2.4))
        p.drawPath(path)

    def _heart(self, p: QPainter, at: QPointF, size: float, color: QColor) -> None:
        x, y, s = at.x(), at.y(), size
        path = QPainterPath(QPointF(x, y + s * 0.9))
        path.cubicTo(QPointF(x - s * 1.4, y), QPointF(x - s * 0.6, y - s * 1.0), QPointF(x, y - s * 0.3))
        path.cubicTo(QPointF(x + s * 0.6, y - s * 1.0), QPointF(x + s * 1.4, y), QPointF(x, y + s * 0.9))
        p.setPen(self._pen(QColor(255, 255, 255, color.alpha()), 1.5))
        p.setBrush(QBrush(color))
        p.drawPath(path)
