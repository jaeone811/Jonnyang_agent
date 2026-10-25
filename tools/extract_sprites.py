"""사용자 스프라이트 시트(assets/source)에서 펫 프레임을 잘라 src/jonnyang/gui/sprites/에 저장한다.

- 표정마다 깨끗한 그림 한 장만 고른다(CELLS, POSES). 애니메이션 시트의 칸들은 다리가 빈 칸, 배경이 덜 지워진
  칸이 섞여 있고 계속 넘기면 정신없어서, 움직임은 gui/sprite.py가 코드로 더한다.
- animation_sheet.webp: 칸(격자) 하나 = 한 프레임. pose_sheet.webp: 자세가 흩어진 시트, 상자 좌표로 자른다
  (알파 채널은 흐릿해서 흰 배경에 합성해서 쓴다).
- 배경: 칸 테두리에서 시작해 배경색과 비슷한 픽셀을 채우기(flood fill)로 지운다. 고양이 외곽선이 경계가 된다.
  자세 시트는 외곽선 바깥의 옅은 빛 번짐 띠를 몇 겹 벗긴다(peel). 가장자리는 1px 깎고 살짝 흐리게.
- 프레임 번호 글자, 작은 얼룩은 버린다. 여러 칸을 쓰면 첫 프레임에 맞춰 위치를 맞춘다(덜덜 떨림 방지).
- 모든 프레임은 같은 크기 캔버스(manifest.yaml의 frame)에, 발끝을 같은 높이(baseline)에 맞춰 놓는다.
  2배 크기로 저장해서 고해상도 화면에서도 덜 뭉개지게 한다.

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
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "source"
OUT = ROOT / "src" / "jonnyang" / "gui" / "sprites"

OUT_SCALE = 2                    # 저장 배율 (화면 좌표 1 = 이미지 2px)
FRAME_W, FRAME_H = 150, 130      # 화면 좌표 기준 캔버스
BASELINE = 124                   # 발끝 높이
BG_THRESHOLD = 14                # 배경색과의 최대 차이 (채널별)
POSE_THRESHOLD = 24              # 자세 시트는 고양이 둘레에 옅은 빛 번짐이 있어서 더 넓게 지운다
POSE_PEEL = 3                    # 자세 시트: 외곽선 바깥에 남는 옅은 띠를 몇 겹 벗길지
PEEL_LIGHT = 200                 # 이보다 밝은(세 채널 모두) 가장자리 픽셀을 띠로 본다

# animation_sheet.webp 격자 (픽셀 좌표, 칸 테두리 선 위치)
SHEET_COLS = [198, 345, 486, 625, 767, 907, 1049, 1191, 1333, 1527]
SHEET_ROWS = [(9, 116), (127, 233), (242, 348), (357, 459), (467, 568), (578, 676), (685, 778), (786, 861),
              (869, 936), (943, 1016)]
# 표정마다 그림 한 장만 쓴다(프레임을 계속 바꾸면 정신없고, 다리가 빈 칸·배경이 덜 지워진 칸이 섞여 있었다).
# 움직임(숨쉬기·깡총·흔들기)과 효과(하트·반짝이·물음표)는 코드(gui/sprite.py)가 더한다.
# animation_sheet.webp에서 고르는 칸: 이름: (줄, 칸, 크기 보정)
CELLS = {
    "sleep": (3, 2, 1.0),       # 잠 (깨끗한 칸)
}
# pose_sheet.webp 상자 (위, 왼쪽, 아래, 오른쪽) 와 크기 보정
POSES = {
    "front": ((58, 22, 206, 138), 0.70),       # 정면: 기본 자세 (대기·기쁨·질문·알림·혼란)
    "float": ((482, 346, 630, 470), 0.70),     # 공중부양 (끌고 다닐 때)
    "search": ((718, 448, 838, 592), 0.70),    # 검색 중 (노트북)
    "files": ((714, 596, 842, 720), 0.70),     # 파일 정리
    "book": ((726, 16, 838, 142), 0.70),       # 책 열기
}
# 공중에 떠 있는 자세는 발끝을 바닥선보다 조금 위에 둔다
LIFT = {"float": 6}


def flood_background(cell: np.ndarray, thr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """테두리에서 이어진 배경 영역(True)과 배경색, 배경색과의 차이를 돌려준다."""
    h, w, _ = cell.shape
    border = np.concatenate([cell[0], cell[-1], cell[:, 0], cell[:, -1]])
    ref = np.median(border, 0)
    diff = np.abs(cell - ref).max(2)
    ok = diff < thr
    seen = np.zeros((h, w), bool)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if ok[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if ok[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and ok[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    return seen, ref, diff


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


def cut(cell: np.ndarray, drop_bottom: int = 0, thr: int = BG_THRESHOLD, peel: int = 0) -> np.ndarray:
    """RGB 칸 → RGBA (배경 투명). drop_bottom: 아래쪽 이만큼 안에만 있는 덩어리(프레임 번호)는 버린다.
    peel: 바깥에서부터 밝은 픽셀(옅은 빛 번짐 띠)을 이만큼 겹 벗긴다. 진한 외곽선에서 멈춘다."""
    h, w, _ = cell.shape
    bg, ref, diff = flood_background(cell, thr)
    fg = ~bg
    keep = np.zeros_like(fg)
    parts = [pts for pts in components(fg) if len(pts) >= 8]
    body_bottom = max(parts, key=len)[:, 0].max() if parts else h
    for pts in parts:
        top = pts[:, 0].min()
        if drop_bottom and (top >= h - drop_bottom or (top >= body_bottom - 4 and len(pts) < 200)):
            continue                     # 프레임 번호 (고양이 발밑에 따로 떨어진 작은 글자)
        keep[pts[:, 0], pts[:, 1]] = True
    # 외곽선 안에 갇힌 넓은 배경(다리 사이 등)도 지운다. 흰 털(다리)까지 지우지 않게 아주 배경색에 가까운 것만.
    for pts in components(~keep):
        if len(pts) > 60 and diff[pts[:, 0], pts[:, 1]].mean() < 3:
            keep[pts[:, 0], pts[:, 1]] = False
    light = cell.min(2) > PEEL_LIGHT
    for _ in range(peel):
        inner = np.asarray(Image.fromarray((keep * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))) > 0
        keep &= ~(keep & ~inner & light)
    if peel:                             # 벗기고 남은 가는 부스러기
        for pts in components(keep):
            if len(pts) < 40:
                keep[pts[:, 0], pts[:, 1]] = False
    # 가장자리: 바깥 1px(배경과 섞인 옅은 테두리)을 깎고 살짝 흐리게 해서 계단 모양을 없앤다.
    # 투명한 쪽 픽셀 색은 주변 고양이 색으로 채워서, 흐린 가장자리가 하얗게 번지지 않게 한다.
    core = Image.fromarray((keep * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))
    alpha = np.asarray(core.filter(ImageFilter.GaussianBlur(0.7))).astype(np.float64) / 255
    alpha[alpha < 0.04] = 0
    rgb = cell.astype(np.float64)
    weight = np.asarray(core).astype(np.float64) / 255
    blur = [np.asarray(Image.fromarray((rgb[..., i] * weight).astype(np.uint8)).filter(ImageFilter.BoxBlur(2)))
            for i in range(3)]
    wsum = np.asarray(Image.fromarray((weight * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(2))) / 255
    fill = np.dstack(blur).astype(np.float64) / np.maximum(wsum, 1e-3)[..., None]
    outside = (weight < 0.5)[..., None]
    rgb = np.where(outside, fill, rgb)
    rgba = np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8)
    return rgba


def bbox(alpha: np.ndarray, thr: int = 60) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(alpha > thr)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def head_center_x(alpha: np.ndarray) -> float:
    """머리(위쪽 절반)의 가로 중심. 꼬리 때문에 전체 상자 중심은 흔들린다."""
    x0, y0, x1, y1 = bbox(alpha)
    top = alpha[y0:(y0 + y1) // 2, :].astype(np.float64)
    xs = np.arange(alpha.shape[1])
    return float((top.sum(0) * xs).sum() / max(1.0, top.sum()))


def best_shift(ref: np.ndarray, img: np.ndarray, rx: int = 8, ry: int = 6) -> tuple[int, int]:
    """img를 (dx, dy)만큼 옮겼을 때 ref와 가장 많이 겹치는 위치."""
    a = ref.astype(np.float64) / 255
    b = img.astype(np.float64) / 255
    best, arg = -1.0, (0, 0)
    for dy in range(-ry, ry + 1):
        for dx in range(-rx, rx + 1):
            s = np.minimum(a, np.roll(np.roll(b, dy, 0), dx, 1)).sum()
            if s > best:
                best, arg = s, (dx, dy)
    return arg


def place(frames: list[np.ndarray], scale: float, lift: int = 0, align: bool = True) -> list[Image.Image]:
    """같은 애니메이션의 프레임들을 맞춰서 캔버스에 놓는다."""
    h = max(f.shape[0] for f in frames)
    w = max(f.shape[1] for f in frames)
    m = 10                               # 정렬할 때 밀려나도 반대편으로 감기지 않게 여백을 둔다
    pad = [np.pad(f, ((m, h - f.shape[0] + m), (m, w - f.shape[1] + m), (0, 0))) for f in frames]
    h, w = h + 2 * m, w + 2 * m
    if align and len(pad) > 1:
        moved = [pad[0]]
        for f in pad[1:]:
            dx, dy = best_shift(pad[0][..., 3], f[..., 3])
            moved.append(np.roll(np.roll(f, dy, 0), dx, 1))
        pad = moved
    first = pad[0][..., 3]
    cx = head_center_x(first)
    bottom = max(bbox(f[..., 3])[3] for f in pad)
    k = scale * OUT_SCALE
    cw, ch = FRAME_W * OUT_SCALE, FRAME_H * OUT_SCALE
    out = []
    for f in pad:
        img = Image.fromarray(f, "RGBA")
        img = img.resize((round(w * k), round(h * k)), Image.LANCZOS)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=40, threshold=2))
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ox = round(cw / 2 - cx * k)
        oy = round((BASELINE - lift) * OUT_SCALE - bottom * k)
        canvas.alpha_composite(img, (max(0, ox), max(0, oy)), (max(0, -ox), max(0, -oy)))
        out.append(canvas)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", help="모든 프레임을 한 장에 모은 미리보기 PNG 경로")
    args = ap.parse_args()
    anim_sheet = np.asarray(Image.open(SRC / "animation_sheet.webp").convert("RGB")).astype(np.int32)
    pose_src = Image.open(SRC / "pose_sheet.webp").convert("RGBA")
    flat = Image.new("RGBA", pose_src.size, (255, 255, 255, 255))
    flat.alpha_composite(pose_src)
    pose_sheet = np.asarray(flat.convert("RGB")).astype(np.int32)

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    manifest: dict = {"frame": [FRAME_W, FRAME_H], "scale": OUT_SCALE, "baseline": BASELINE, "animations": {}}
    strips: dict[str, list[Image.Image]] = {}
    for name, (row, col, scale) in CELLS.items():
        y0, y1 = SHEET_ROWS[row]
        cell = cut(anim_sheet[y0 + 3:y1 - 2, SHEET_COLS[col] + 3:SHEET_COLS[col + 1] - 2], drop_bottom=13)
        strips[name] = place([cell], scale, LIFT.get(name, 0), align=False)
    for name, ((y0, x0, y1, x1), scale) in POSES.items():
        cell = cut(pose_sheet[y0:y1, x0:x1], thr=POSE_THRESHOLD, peel=POSE_PEEL)
        strips[name] = place([cell], scale, LIFT.get(name, 0), align=False)
    for name, frames in strips.items():
        fw, fh = frames[0].size
        strip = Image.new("RGBA", (fw * len(frames), fh), (0, 0, 0, 0))
        for i, f in enumerate(frames):
            strip.alpha_composite(f, (i * fw, 0))
        strip.save(OUT / f"{name}.png", optimize=True)
        manifest["animations"][name] = len(frames)
    header = "# tools/extract_sprites.py가 만든 파일 (직접 고치지 말고 도구를 다시 돌린다)\n"
    with open(OUT / "manifest.yaml", "w", encoding="utf-8") as f:
        f.write(header + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False))
    if args.sheet:
        cw, ch = FRAME_W * OUT_SCALE, FRAME_H * OUT_SCALE
        rows = list(strips.items())
        prev = Image.new("RGBA", (cw * 9, ch * len(rows)), (60, 64, 90, 255))
        for r, (_, frames) in enumerate(rows):
            for i, f in enumerate(frames):
                prev.alpha_composite(f, (i * cw, r * ch))
        prev.save(args.sheet)
    total = sum(p.stat().st_size for p in OUT.glob("*.png"))
    print(f"{len(strips)}개 애니메이션, {sum(map(len, strips.values()))}프레임, {total / 1024:.0f}KB → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
