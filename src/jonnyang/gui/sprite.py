"""그림(스프라이트) 고양이. 사용자 컨셉 아트·스프라이트 시트에서 잘라낸 프레임을 넘겨 가며 그린다.

- 프레임은 gui/sprites/*.png (tools/extract_sprites.py가 만든다).
  파일 하나 = 애니메이션 하나, 가로로 프레임이 이어져 있다.
  manifest.yaml에 프레임 크기(화면 좌표)·저장 배율·발끝 높이·애니메이션별 프레임 수가 있다.
- 표정(pose) → 애니메이션·속도·움직임은 persona.yaml `sprites.poses` (없는 표정은 아래 DEFAULT_POSES).
- 한 장짜리 자세는 숨쉬기·둥실·깡총 같은 움직임을 코드로 더해서 살아 있게 보이게 한다.
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

DEFAULT_POSES: dict[str, dict[str, Any]] = {
    "idle": {"anim": "idle", "fps": 5},
    "listen": {"anim": "wait", "motion": "breathe"},
    "happy": {"anim": "happy", "fps": 8, "motion": "hop"},
    "love": {"anim": "love", "motion": "hop breathe"},
    "alert": {"anim": "surprise", "fps": 8, "motion": "hop shake"},
    "confused": {"anim": "error", "fps": 6},
    "sad": {"anim": "error", "fps": 4},
    "ask": {"anim": "front", "motion": "breathe", "mark": "?"},
    "sleep": {"anim": "sleep", "fps": 2.5, "clock": "t", "shadow": 84},
    "think": {"anim": "search", "motion": "breathe", "mark": "dots"},
    "search": {"anim": "coding", "fps": 6},
    "book": {"anim": "magic", "fps": 7, "motion": "float"},
    "files": {"anim": "files", "motion": "breathe", "mark": "dots"},
    "drag": {"anim": "float", "motion": "float", "shadow": 50},
}


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
        return bool(self.frames("idle"))

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
        self.extras = [str(x) for x in (spec.get("idle_extras") or []) if sheet.has(str(x))]
        self.extra_every = float(spec.get("idle_extra_every", 24))
        self.extra_sec = float(spec.get("idle_extra_sec", 2.4))
        self.fallback = CatPainter(colors)       # 그림이 없는 표정·파일이 없을 때 + 하트·물음표 그리기

    @property
    def available(self) -> bool:
        return self.sheet.available

    def anim_for(self, f: CatFrame) -> tuple[str, dict[str, Any]]:
        """이 프레임에 쓸 애니메이션 이름과 설정."""
        spec = self.poses.get(f.pose) or self.poses["idle"]
        name = str(spec.get("anim", "idle"))
        if f.pose == "idle" and self.extras and self.extra_every > 0:
            # 가만히 있으면 가끔 윙크·하품·기지개 (시간으로 정해서 상태가 필요 없다)
            cycle = int(f.pose_t // self.extra_every)
            if cycle >= 1 and f.pose_t % self.extra_every < self.extra_sec:
                return self.extras[(cycle - 1) % len(self.extras)], {"motion": "breathe"}
        if not self.sheet.has(name):
            name = "idle"
        return name, spec

    def frame_index(self, f: CatFrame, name: str, spec: dict[str, Any]) -> int:
        n = max(1, len(self.sheet.frames(name)))
        clock = f.t if spec.get("clock") == "t" else f.pose_t
        return int(max(0.0, clock) * float(spec.get("fps", 6))) % n

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
        dx, dy, sy = self._motion(f, str(spec.get("motion", "")))
        base = self.sheet.baseline
        self._shadow(p, base, float(spec.get("shadow", 64)), dy)
        p.translate(dx, dy + base * (1 - sy))     # 세로로 늘였다 줄일 때 발끝은 그대로
        p.scale(1.0, sy)
        p.drawPixmap(QRectF(0, 0, fw, fh), pix, QRectF(pix.rect()))
        p.scale(1.0, 1 / sy)
        self._marks(p, f, str(spec.get("mark", "")))
        p.restore()

    @staticmethod
    def _motion(f: CatFrame, motion: str) -> tuple[float, float, float]:
        dx = dy = 0.0
        sy = 1.0
        if "breathe" in motion:
            sy = 1.0 + 0.014 * math.sin(f.t * 2.4)
        if "float" in motion:
            dy -= 3.0 + 3.0 * math.sin(f.t * 2.4)
        if "hop" in motion and f.pose_t < 0.9:
            dy -= abs(math.sin(f.pose_t * 7)) * 9 * (1 - f.pose_t / 0.9)
        if "shake" in motion and f.pose_t < 1.2:
            dx += math.sin(f.pose_t * 40) * 2 * (1 - f.pose_t / 1.2)
        return dx, dy, sy

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

    def _marks(self, p: QPainter, f: CatFrame, mark: str) -> None:
        c = self.fallback
        if mark == "?":
            c._mark_text(p, QPointF(110, 40 + math.sin(f.t * 3) * 2), "?", 24, c.c["mark"])
        elif mark == "dots":
            for i in range(3):
                a = 0.35 + 0.65 * max(0.0, math.sin(f.t * 4 - i * 0.9))
                p.setPen(c._pen(QColor(255, 255, 255, int(255 * a)), 1.6))
                p.setBrush(c._alpha("mark", int(255 * a)))
                p.drawEllipse(QPointF(106 + i * 8, 36), 3.0, 3.0)
        if f.heart_t is not None and f.heart_t < 1.4:       # 쓰다듬으면 하트가 올라간다
            k = f.heart_t / 1.4
            col = QColor("#FF6B9A")
            col.setAlpha(int(255 * (1 - k)))
            c._heart(p, QPointF(40 - k * 6, 40 - k * 24), 7 + k * 3, col)

    def paint_icon(self, p: QPainter, rect: QRectF) -> None:
        """트레이·exe 아이콘: 정면 자세의 얼굴 부분을 크게."""
        frames = self.sheet.frames("front") or self.sheet.frames("idle")
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
        if sp.sheet.counts and (Path(directory) / "idle.png").is_file():
            return sp
    return CatPainter(colors)
