"""그림(스프라이트) 고양이. 사용자 컨셉 아트·스프라이트 시트에서 잘라낸 그림으로 그린다.

- 그림은 gui/sprites/*.png (tools/extract_sprites.py가 만든다). 파일 하나에 프레임이 가로로 이어져 있을 수
  있지만, 기본은 표정마다 깨끗한 한 장이다. 프레임을 계속 넘기면 정신없어서 그림은 가만히 두고,
  숨쉬기·깡총·흔들기·기울이기 같은 움직임과 반짝이·하트·물음표 같은 효과를 코드로 더한다.
- 클릭(쓰다듬기)은 그림을 바꾸지 않고 몸을 눌렀다 펴는 크기 변화 + 하트만 보여준다(CatFrame.heart_t).
- 표정(pose) → 그림·움직임·효과는 persona.yaml `sprites.poses` (없는 표정은 아래 DEFAULT_POSES).
- 그림 파일이 없거나 깨졌으면 painter.py의 도형 고양이로 그린다 (CatPainter와 같은 paint() 모양).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QRadialGradient

from jonnyang.gui.painter import CatFrame, CatPainter

# anim: 그림 이름 / motion: breathe(숨쉬기) float(둥실) hop(깡총) shake(흔들) tilt(갸웃) droop(시무룩)
# mark: ? ! dots(생각 중) swirl(어지러움) z(잠) sweat(땀) / effect: sparkle(반짝이) hearts(하트)
DEFAULT_POSES: dict[str, dict[str, Any]] = {
    "idle": {"anim": "front", "motion": "breathe"},
    "listen": {"anim": "front", "motion": "breathe"},
    "happy": {"anim": "front", "motion": "hop breathe", "effect": "sparkle"},
    "love": {"anim": "front", "motion": "hop breathe", "effect": "hearts"},
    "alert": {"anim": "front", "motion": "hop shake", "mark": "!"},
    "confused": {"anim": "front", "motion": "tilt breathe", "mark": "swirl"},
    "sad": {"anim": "front", "motion": "droop", "mark": "sweat"},
    "ask": {"anim": "front", "motion": "tilt breathe", "mark": "?"},
    "sleep": {"anim": "sleep", "motion": "breathe", "mark": "z", "shadow": 84},
    "think": {"anim": "front", "motion": "breathe", "mark": "dots"},
    "search": {"anim": "search", "motion": "breathe", "mark": "dots"},
    "book": {"anim": "book", "motion": "float", "effect": "sparkle"},
    "files": {"anim": "files", "motion": "breathe", "mark": "dots"},
    "drag": {"anim": "float", "motion": "float", "shadow": 50},
}
POKE_SEC = 0.6                   # 클릭하면 이만큼 몸을 눌렀다 편다
HEART_SEC = 1.4


class SpriteSheet:
    """gui/sprites 폴더를 읽는다. QPixmap은 처음 그릴 때 만든다 (QApplication이 있어야 해서)."""

    def __init__(self, directory: Path):
        self.dir = Path(directory)
        self.frame_w, self.frame_h, self.scale, self.baseline = 150, 130, 2, 124
        self.counts: dict[str, int] = {}
        self._cache: dict[str, list[QPixmap]] = {}
        try:
            with open(self.dir / "manifest.yaml", encoding="utf-8") as f:
                m = yaml.safe_load(f) or {}
            self.frame_w, self.frame_h = (int(v) for v in m.get("frame", (150, 130)))
            self.scale = int(m.get("scale", 2))
            self.baseline = float(m.get("baseline", 124))
            self.counts = {str(k): int(v) for k, v in (m.get("animations") or {}).items()}
        except (OSError, yaml.YAMLError, TypeError, ValueError):
            self.counts = {}

    @property
    def available(self) -> bool:
        return bool(self.frames("front"))

    def has(self, name: str) -> bool:
        return name in self.counts

    def frames(self, name: str) -> list[QPixmap]:
        if name in self._cache:
            return self._cache[name]
        out: list[QPixmap] = []
        n = self.counts.get(name, 0)
        img = QImage(str(self.dir / f"{name}.png")) if n else QImage()
        fw, fh = self.frame_w * self.scale, self.frame_h * self.scale
        if not img.isNull() and img.width() >= fw * n and img.height() >= fh:
            out = [QPixmap.fromImage(img.copy(i * fw, 0, fw, fh)) for i in range(n)]
        self._cache[name] = out
        return out


class SpritePainter:
    """CatPainter 대신 쓰는 그림 고양이. paint(p, rect, CatFrame)."""

    def __init__(self, sheet: SpriteSheet, spec: dict | None = None, colors: dict | None = None):
        self.sheet = sheet
        spec = spec or {}
        self.poses = {**DEFAULT_POSES, **{str(k): dict(v) for k, v in (spec.get("poses") or {}).items()
                                          if isinstance(v, dict)}}
        self.fallback = CatPainter(colors)       # 그림이 없는 표정·파일이 없을 때 + 하트·물음표 그리기

    @property
    def available(self) -> bool:
        return self.sheet.available

    def anim_for(self, f: CatFrame) -> tuple[str, dict[str, Any]]:
        """이 프레임에 쓸 애니메이션 이름과 설정."""
        spec = self.poses.get(f.pose) or self.poses["idle"]
        name = str(spec.get("anim", "front"))
        if not self.sheet.has(name):
            name = "front" if self.sheet.has("front") else next(iter(self.sheet.counts), name)
        return name, spec

    def frame_index(self, f: CatFrame, name: str, spec: dict[str, Any]) -> int:
        n = max(1, len(self.sheet.frames(name)))
        clock = f.t if spec.get("clock") == "t" else f.pose_t
        return int(max(0.0, clock) * float(spec.get("fps", 0))) % n     # fps가 없으면 첫 장 고정

    def paint(self, p: QPainter, rect: QRectF, f: CatFrame) -> None:
        name, spec = self.anim_for(f)
        frames = self.sheet.frames(name)
        if not frames:
            self.fallback.paint(p, rect, f)
            return
        pix = frames[self.frame_index(f, name, spec)]
        fw, fh = self.sheet.frame_w, self.sheet.frame_h
        k = min(rect.width() / fw, rect.height() / fh)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(rect.center().x() - fw * k / 2, rect.bottom() - fh * k)
        p.scale(k, k)                             # 이제 좌표는 프레임 캔버스(fw x fh) 기준
        dx, dy, sx, sy, angle = self._motion(f, str(spec.get("motion", "")))
        base, mid = self.sheet.baseline, fw / 2
        self._shadow(p, base, float(spec.get("shadow", 64)) * sx, dy)
        p.save()
        p.translate(mid + dx, base + dy)          # 발끝 가운데를 기준으로 늘이고 기울인다
        p.rotate(angle)
        p.scale(sx, sy)
        p.translate(-mid, -base)
        p.drawPixmap(QRectF(0, 0, fw, fh), pix, QRectF(pix.rect()))
        p.restore()
        p.translate(dx, dy)
        self._effects(p, f, str(spec.get("mark", "")), str(spec.get("effect", "")))
        p.restore()

    @staticmethod
    def _motion(f: CatFrame, motion: str) -> tuple[float, float, float, float, float]:
        """(가로 이동, 세로 이동, 가로 배율, 세로 배율, 기울기). 전부 작고 느리게."""
        dx = dy = angle = 0.0
        sx = sy = 1.0
        if "breathe" in motion:
            sy += 0.012 * math.sin(f.t * 2.2)
        if "float" in motion:
            dy -= 3.0 + 3.0 * math.sin(f.t * 2.0)
        if "hop" in motion and f.pose_t < 0.7:
            dy -= abs(math.sin(f.pose_t * math.pi / 0.35)) * 7 * (1 - f.pose_t / 0.7)
        if "shake" in motion and f.pose_t < 1.0:
            dx += math.sin(f.pose_t * 38) * 2.2 * (1 - f.pose_t)
        if "tilt" in motion:
            angle += -5.0 * min(1.0, f.pose_t / 0.25)          # 고개 갸웃 (몸 전체를 살짝)
        if "droop" in motion:
            k = min(1.0, f.pose_t / 0.4)
            sy -= 0.035 * k
            sx += 0.02 * k
        if f.heart_t is not None and f.heart_t < POKE_SEC:     # 클릭: 눌렸다가 통통 튀어 오른다
            u = f.heart_t / POKE_SEC
            wave = math.sin(u * math.pi * 2) * (1 - u)
            sx += 0.07 * wave
            sy -= 0.07 * wave
        return dx, dy, sx, sy, angle

    def _shadow(self, p: QPainter, base: float, width: float, lift: float) -> None:
        w = max(20.0, width + lift * 1.5)          # 뜨면(lift<0) 그림자가 작아진다
        g = QRadialGradient(QPointF(0, 0), 1.0)
        g.setColorAt(0, QColor(60, 50, 120, 70))
        g.setColorAt(1, QColor(60, 50, 120, 0))
        p.save()
        p.translate(self.sheet.frame_w / 2, base + 1)
        p.scale(w / 2, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(0, 0), 1.0, 1.0)
        p.restore()

    def _effects(self, p: QPainter, f: CatFrame, mark: str, effect: str) -> None:
        """머리 옆 표시(물음표 등)와 주변 효과. 좌표는 프레임 캔버스 기준 (머리 오른쪽 위 ≈ (110, 30))."""
        c = self.fallback
        bob = math.sin(f.t * 3) * 1.5
        if mark == "?":
            c._mark_text(p, QPointF(108, 38 + bob), "?", 24, c.c["mark"])
        elif mark == "!":
            c._mark_text(p, QPointF(110, 38), "!", 26, QColor("#FF5C8A"))
        elif mark == "swirl":
            c._swirl(p, QPointF(116, 26), f.t)
        elif mark == "sweat":
            drop = (f.t * 0.8) % 1.0
            col = QColor("#7FB4FF")
            col.setAlpha(int(230 * (1 - drop)))
            p.setPen(c._pen(QColor(255, 255, 255, col.alpha()), 1.2))
            p.setBrush(col)
            p.drawEllipse(QPointF(104, 40 + drop * 10), 3.0, 4.0)
        elif mark == "dots":
            for i in range(3):
                a = 0.35 + 0.65 * max(0.0, math.sin(f.t * 4 - i * 0.9))
                p.setPen(c._pen(QColor(255, 255, 255, int(255 * a)), 1.6))
                p.setBrush(c._alpha("mark", int(255 * a)))
                p.drawEllipse(QPointF(106 + i * 8, 34), 3.0, 3.0)
        elif mark == "z":
            for i in range(3):
                phase = (f.t * 0.4 + i / 3) % 1.0
                col = c._alpha("mark", int(230 * (1 - phase)))
                c._mark_text(p, QPointF(104 + phase * 14 + i * 5, 70 - phase * 26 - i * 5), "z", 10 + i * 3, col)
        if effect == "sparkle":
            for i, (x, y) in enumerate(((36, 40), (116, 52), (30, 88), (122, 92))):
                k = max(0.0, math.sin(f.t * 3 + i * 1.7))
                if k > 0.05:
                    c._sparkle(p, QPointF(x, y), 1.0 + 2.5 * k, c._alpha("sparkle", int(255 * k)))
        elif effect == "hearts":
            for i in range(2):
                k = (f.t * 0.45 + i / 2) % 1.0
                col = QColor("#FF6B9A")
                col.setAlpha(int(255 * (1 - k)))
                c._heart(p, QPointF(108 + i * 12, 52 - k * 26), 5 + i * 2, col)
        if f.heart_t is not None and f.heart_t < HEART_SEC:     # 쓰다듬으면 하트가 올라간다
            k = f.heart_t / HEART_SEC
            for i, (x, s) in enumerate(((42, 7), (110, 6))):
                col = QColor("#FF6B9A")
                col.setAlpha(int(255 * max(0.0, 1 - k - i * 0.15)))
                c._heart(p, QPointF(x + (i * 2 - 1) * k * 6, 44 - k * 26 - i * 4), s + k * 3, col)

    def paint_icon(self, p: QPainter, rect: QRectF) -> None:
        """트레이·exe 아이콘: 정면 자세의 얼굴 부분을 크게."""
        frames = self.sheet.frames("front")
        if not frames:
            self.fallback.paint_icon(p, rect)
            return
        pix = frames[0]
        s = self.sheet.scale
        src = QRectF(36 * s, 20 * s, 86 * s, 86 * s)        # 왕관~가슴 (프레임 캔버스 좌표)
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(rect, pix, src)
        p.restore()


def make_painter(directory: Path, spec: dict | None = None, colors: dict | None = None) -> SpritePainter | CatPainter:
    """그림 파일이 있으면 SpritePainter, 없거나 꺼져 있으면 도형 고양이."""
    spec = spec or {}
    if spec.get("enabled", True):
        sp = SpritePainter(SpriteSheet(directory), spec, colors)
        if sp.sheet.counts and (Path(directory) / "front.png").is_file():
            return sp
    return CatPainter(colors)
