"""Автодоводка ROI к ближайшему светлому текстовому блоку значения.
   python -m qt.capture.snap --image tests/fixtures/screen_01.png"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path
import cv2
import numpy as np

from ..core.config import load_config, save_config, config_path
from ..core.frame import HUD_ROI_FIELDS
from ..core.io import imread_u
from ..ocr.preprocess import stretch

def _bright_mask(gray: np.ndarray) -> np.ndarray:
    """Значения полей — яркие; подписи — серые. Порог: второй Otsu/kmeans по переднему плану."""
    t1, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
    fg = gray > t1
    vals = gray[fg]
    if vals.size < 50:
        return np.zeros_like(gray, np.uint8)
    z = vals.astype(np.float32).reshape(-1, 1)
    _, _, centers = cv2.kmeans(z, 2, None,
                               (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0),
                               3, cv2.KMEANS_PP_CENTERS)
    c0, c1 = sorted(float(c) for c in centers.ravel())
    thr = (c0 + c1) / 2.0 if (c1 - c0) >= 40 else t1   # одномодально — берём весь передний план
    return ((gray >= thr) & fg).astype(np.uint8) * 255

def _candidates(gray_win: np.ndarray):
    m = _bright_mask(gray_win)
    m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=1)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [list(cv2.boundingRect(c)) for c in cnts]
    boxes.sort(key=lambda b: b[0])
    merged = []
    for b in boxes:  # слить части одного значения ("25,2V 1,1A", "1 / 2")
        if merged:
            px, py, pw, ph = merged[-1]
            gap = b[0] - (px + pw)
            vover = min(py + ph, b[1] + b[3]) - max(py, b[1])
            if gap <= 1.5 * min(ph, b[3]) and vover > 0.5 * min(ph, b[3]):
                ny = min(py, b[1])
                merged[-1] = [px, ny, max(px + pw, b[0] + b[2]) - px,
                              max(py + ph, b[1] + b[3]) - ny]
                continue
        merged.append(b)
    return merged

def snap_rect(gray: np.ndarray, rect, search: int = 400):
    x, y, w, h = [int(v) for v in rect]
    H, W = gray.shape
    x0, y0 = max(0, x - search), max(0, y - search)
    x1, y1 = min(W, x + w + search), min(H, y + h + search)
    cands = _candidates(gray[y0:y1, x0:x1])
    cx, cy = x + w / 2, y + h / 2
    best, best_d = None, 1e18
    for bx, by, bw, bh in cands:
        if not (0.25 * w <= bw <= 3.0 * w and 0.25 * h <= bh <= 3.0 * h):
            continue
        d = (x0 + bx + bw / 2 - cx) ** 2 + (y0 + by + bh / 2 - cy) ** 2
        if d < best_d:
            best_d, best = d, (x0 + bx, y0 + by, bw, bh)
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--search", type=int, default=400)
    args = ap.parse_args()

    cfg = load_config(args.config)
    img = imread_u(args.image)
    if img is None:
        raise SystemExit("не читается image")
    H, W = img.shape[:2]
    gray = cv2.cvtColor(stretch(img), cv2.COLOR_BGR2GRAY)
    print(f"image: {W}x{H}")

    p = config_path() if args.config is None else Path(args.config)
    if p.exists():
        shutil.copyfile(p, str(p) + ".bak")

    print(f"{'field':10s} {'old':>26s} -> {'new':>26s}  p99new")
    for name in HUD_ROI_FIELDS:
        r = cfg["rois"].get(name)
        if not r:
            continue
        s = snap_rect(gray, r, args.search)
        if s:
            cfg["rois"][name] = [int(v) for v in s]
        else:
            print(f"{name:10s} KEEP (кандидат не найден)")
        new = cfg["rois"][name]
        x, y, w, h = [int(v) for v in new]
        crop_g = gray[y:y + h, x:x + w]
        p99 = float(np.percentile(crop_g, 99)) if crop_g.size else 0.0
        print(f"{name:10s} {str(tuple(int(v) for v in r)):>26s} -> {str(tuple(new)):>26s}  {p99:6.1f}"
              + ("" if p99 > 150 or name == "pilot" else "   <-- ПУСТО!"))
    save_config(cfg, p)
    print(f"saved -> {p} (backup: {p}.bak)")

if __name__ == "__main__":
    main()