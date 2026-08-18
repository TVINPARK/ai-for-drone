"""Автоназначение ROI по стандартному макету HUD."""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path
import cv2
import numpy as np

from ..core.config import load_config, save_config, config_path
from ..core.io import imread_u
from ..ocr.preprocess import stretch

PAD = 2
WINDOWS = {
    "pilot":     (0.00, 0.60, 0.000, 0.030, "union",   0.40, 0.05, None),
    "datetime":  (0.00, 0.25, 0.028, 0.060, "union",   0.12, 0.04, None),
    "battery":   (0.02, 0.25, 0.055, 0.100, "union",   0.12, 0.05, None),
    "mode":      (0.00, 0.15, 0.085, 0.140, "union",   0.08, 0.05, None),
    "limit":     (0.85, 1.00, 0.030, 0.100, "union",   0.12, 0.04, "top"),
    "speed":     (0.00, 0.20, 0.450, 0.600, "tallest", 0.08, 0.08, None),
    "alt":       (0.75, 0.90, 0.450, 0.600, "tallest", 0.05, 0.06, None),
    "laps":      (0.00, 0.12, 0.900, 1.000, "union",   0.06, 0.04, "bottom"),
    "cur_time":  (0.10, 0.30, 0.900, 1.000, "union",   0.09, 0.04, "bottom"),
    "best_time": (0.80, 1.00, 0.900, 1.000, "union",   0.12, 0.04, "bottom"),
}

def _text_mask(gray):
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    th = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
    return ((th > 40).astype(np.uint8)) * 255

def _word_boxes(mask):
    m = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [list(cv2.boundingRect(c)) for c in cnts]

def gray_of(img):
    return cv2.cvtColor(stretch(img), cv2.COLOR_BGR2GRAY)

def _panel_rects(img, ymin_frac, ymax_frac, min_w_frac=0.10):
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    dark = ((hsv[..., 2] < 110).astype(np.uint8)) * 255
    dark[:int(H * ymin_frac), :] = 0
    dark[int(H * ymax_frac):, :] = 0
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w >= min_w_frac * W and h >= 18:
            out.append((x, y, w, h))
    return out

def _text_band(tmask, panel):
    px, py, pw, ph = panel
    sub = tmask[py:py + ph, px:px + pw]
    rows = (sub > 0).sum(axis=1)
    if rows.max() == 0:
        return None
    thr = 0.25 * rows.max()
    bands, y = [], 0
    while y < ph:
        if rows[y] > thr:
            y2 = y
            while y2 + 1 < ph and rows[y2 + 1] > thr:
                y2 += 1
            bands.append((y, y2 + 1))
            y = y2 + 1
        else:
            y += 1
    best, best_score = None, -1.0
    for a, b in bands:
        h = b - a
        if not (12 <= h <= max(14, 0.7 * ph)):
            continue
        center_dist = abs((a + b) / 2 - ph / 2)
        score = float(rows[a:b].sum()) * (1.0 if center_dist <= 0.25 * ph else 0.5)
        if score > best_score:
            best_score, best = score, (a, b)
    return (py + best[0] - 2, py + best[1] + 2) if best else None

def assign_rois(img, windows=WINDOWS, pad=PAD):
    gray = gray_of(img)
    H, W = gray.shape
    tmask = _text_mask(gray)
    boxes = _word_boxes(tmask)
    panels = {"bottom": _panel_rects(img, 0.90, 1.00),
              "top":    _panel_rects(img, 0.00, 0.15)}
    bands = {}
    for zone, rects in panels.items():
        bands[zone] = [b for r in rects if (b := _text_band(tmask, r)) is not None]
    rois = {}
    for name, (x0, x1, y0, y1, mode, mw, mh, zone) in windows.items():
        cands = []
        for x, y, w, h in boxes:
            cx, cy = x + w / 2, y + h / 2
            if not (x0 <= cx / W <= x1 and y0 <= cy / H <= y1):
                continue
            if w > mw * W or h > mh * H:
                continue
            if float((tmask[y:y + h, x:x + w] > 0).mean()) < 0.12:
                continue
            if zone and bands[zone] and not any(b0 - 2 <= cy <= b1 + 2 for b0, b1 in bands[zone]):
                continue
            cands.append((x, y, w, h))
        if not cands:
            continue
        if mode == "union":
            x = min(b[0] for b in cands)
            y = min(b[1] for b in cands)
            x2 = max(b[0] + b[2] for b in cands)
            y2 = max(b[1] + b[3] for b in cands)
            b = (x, y, x2 - x, y2 - y)
        else:
            b = max(cands, key=lambda b: (b[2] if mode == "widest" else b[3]))
        x, y, w, h = b
        rois[name] = [int(max(0, x - pad)), int(max(0, y - pad)),
                      int(w + 2 * pad), int(h + 2 * pad)]
    return rois

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    img = imread_u(args.image)
    if img is None:
        raise SystemExit("не читается image")
    rois = assign_rois(img)
    p = config_path() if args.config is None else Path(args.config)
    if p.exists():
        shutil.copyfile(p, str(p) + ".bak")
    H, W = img.shape[:2]
    print("image %dx%d" % (W, H))
    for name, r in rois.items():
        print("%-10s -> %s" % (name, r))
    missing = [k for k in WINDOWS if k not in rois]
    if missing:
        print("NOT FOUND:", ", ".join(missing))
    cfg["rois"].update(rois)
    cfg["screen"] = {"width": int(W), "height": int(H)}
    save_config(cfg, p)
    print("saved ->", p)

if __name__ == "__main__":
    main()
