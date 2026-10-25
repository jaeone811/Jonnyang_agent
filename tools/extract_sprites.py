"""사용자 고해상도 자세 시트(assets/source/pose_sheet_hd.webp)에서 펫 그림을 잘라 src/jonnyang/gui/sprites/에 저장한다.

- 시트 한 장에 자세 6개가 3x2로 놓여 있고 배경은 이미 투명하다(알파 채널). 칸마다 고양이 상자를 찾아 자른다.
- 표정마다 그림 한 장만 쓴다. 움직임(숨쉬기·깡총·흔들기)과 효과(하트·반짝이·물음표)는 gui/sprite.py가 코드로 더한다.
- 고양이 둘레의 아주 옅은 번짐(알파가 거의 0)은 지우고, 따로 떨어진 작은 얼룩도 버린다.
- 모든 그림은 같은 크기 캔버스(manifest.yaml의 frame)에, 같은 배율로, 발끝을 같은 높이(baseline)에 맞춰 놓는다.
  3배 크기로 저장해서 고해상도 화면에서도 선명하게 한다.
- 예전 시트(animation_sheet.webp, pose_sheet.webp)와 concept_art.webp는 참고용 원본으로만 남겨 둔다.

사용법: python tools/extract_sprites.py [--sheet 미리보기.png]
필요: Pillow, numpy (개발용. 프로그램 실행에는 필요 없다)
"""

from __future__ import annotations

import argparse
import sys
from collections import deque
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "source"
OUT = ROOT / "src" / "jonnyang" / "gui" / "sprites"
SOURCE = "pose_sheet_hd.webp"

OUT_SCALE = 3                    # 저장 배율 (화면 좌표 1 = 이미지 3px)
FRAME_W, FRAME_H = 150, 130      # 화면 좌표 기준 캔버스
BASELINE = 124                   # 발끝 높이
UNIT = 0.217                     # 시트 1px → 화면 좌표 (정면 자세 키가 약 96이 되게)
ALPHA_LO, ALPHA_HI = 16, 240     # 알파를 이 구간으로 다시 펼친다 (LO 이하 번짐은 투명, HI 이상은 불투명)
MIN_PART = 40                    # 이보다 작은 따로 떨어진 덩어리는 얼룩으로 보고 버린다

# 시트 칸 경계 (픽셀). 자세끼리 겹치지 않는 선.
GRID_X = [0, 520, 1036, 1536]
GRID_Y = [0, 528, 1024]
# 이름: (줄, 칸)
POSES = {
    "front": (0, 0),            # 정면: 기본 자세 (대기·기쁨·질문·알림·혼란)
    "files": (0, 1),            # 상자 정리 (파일 작업)
    "search": (0, 2),           # 홀로그램 창 (검색 중)
    "book": (1, 0),             # 책 열기
    "sleep": (1, 1),            # 잠
    "float": (1, 2),            # 공중에 뜬 자세 (끌고 다닐 때)
}
# 공중에 떠 있는 자세는 발끝을 바닥선보다 조금 위에 둔다
LIFT = {"float": 6}


def components(mask: np.ndarray) -> list[np.ndarray]:
    """8방향으로 이어진 덩어리들 (각각 (y, x) 좌표 배열)."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    out = []
    for sy, sx in zip(*np.nonzero(mask), strict=True):
        if lab[sy, sx]:
            continue
        lab[sy, sx] = len(out) + 1
        q = deque([(sy, sx)])
        pts = []
        while q:
            y, x = q.popleft()
            pts.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = len(out) + 1
                        q.append((ny, nx))
        out.append(np.array(pts))
    return out


def clean(cell: np.ndarray) -> np.ndarray:
    """RGBA 칸 → 옅은 번짐과 얼룩을 지운 RGBA, 고양이 상자만큼 잘라서."""
    rgb = cell[..., :3]
    a = cell[..., 3].astype(np.float64)
    alpha = np.clip((a - ALPHA_LO) / (ALPHA_HI - ALPHA_LO), 0, 1)
    for pts in components(alpha > 0):
        if len(pts) < MIN_PART:
            alpha[pts[:, 0], pts[:, 1]] = 0
    ys, xs = np.nonzero(alpha > 0)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return np.dstack([rgb, alpha * 255]).astype(np.uint8)[y0:y1, x0:x1]


def bbox(alpha: np.ndarray, thr: int = 60) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(alpha > thr)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def head_center_x(alpha: np.ndarray) -> float:
    """머리(위쪽 절반)의 가로 중심. 꼬리·소품 때문에 전체 상자 중심은 치우친다."""
    x0, y0, x1, y1 = bbox(alpha)
    top = alpha[y0:(y0 + y1) // 2, :].astype(np.float64)
    xs = np.arange(alpha.shape[1])
    return float((top.sum(0) * xs).sum() / max(1.0, top.sum()))


def place(img: np.ndarray, lift: int = 0) -> Image.Image:
    """그림을 캔버스에 놓는다: 머리 가운데를 캔버스 가운데에, 발끝을 바닥선에."""
    cx = head_center_x(img[..., 3])
    bottom = bbox(img[..., 3])[3]
    k = UNIT * OUT_SCALE
    h, w = img.shape[:2]
    # 알파를 곱한 상태(RGBa)로 줄여야 가장자리에 투명 픽셀 색(검정·흰색)이 번지지 않는다
    small = Image.fromarray(img, "RGBA").convert("RGBa").resize((round(w * k), round(h * k)), Image.LANCZOS)
    small = small.convert("RGBA")
    cw, ch = FRAME_W * OUT_SCALE, FRAME_H * OUT_SCALE
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ox = round(cw / 2 - cx * k)
    oy = round((BASELINE - lift) * OUT_SCALE - bottom * k)
    canvas.alpha_composite(small, (max(0, ox), max(0, oy)), (max(0, -ox), max(0, -oy)))
    return canvas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", help="모든 그림을 한 장에 모은 미리보기 PNG 경로")
    args = ap.parse_args()
    sheet = np.asarray(Image.open(SRC / SOURCE).convert("RGBA"))

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    manifest: dict = {"frame": [FRAME_W, FRAME_H], "scale": OUT_SCALE, "baseline": BASELINE, "animations": {}}
    images: dict[str, Image.Image] = {}
    for name, (row, col) in POSES.items():
        cell = sheet[GRID_Y[row]:GRID_Y[row + 1], GRID_X[col]:GRID_X[col + 1]]
        images[name] = place(clean(cell), LIFT.get(name, 0))
        images[name].save(OUT / f"{name}.png", optimize=True)
        manifest["animations"][name] = 1
    header = "# tools/extract_sprites.py가 만든 파일 (직접 고치지 말고 도구를 다시 돌린다)\n"
    with open(OUT / "manifest.yaml", "w", encoding="utf-8") as f:
        f.write(header + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False))
    if args.sheet:
        cw, ch = FRAME_W * OUT_SCALE, FRAME_H * OUT_SCALE
        prev = Image.new("RGBA", (cw * len(images), ch), (60, 64, 90, 255))
        for i, img in enumerate(images.values()):
            prev.alpha_composite(img, (i * cw, 0))
        prev.save(args.sheet)
    total = sum(p.stat().st_size for p in OUT.glob("*.png"))
    print(f"그림 {len(images)}장, {total / 1024:.0f}KB → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
