"""Препроцессинг HUD-кропов."""
from __future__ import annotations
import numpy as np
import cv2

def stretch(crop: np.ndarray) -> np.ndarray:
    g = crop.astype(np.float32)
    lo, hi = np.percentile(g, 2), np.percentile(g, 99.8)
    if hi - lo < 1:
        hi = lo + 1
    return np.clip((g - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)

def _strip_lines(bw: np.ndarray) -> np.ndarray:
    out = bw.copy()
    row_fill = (out > 0).mean(axis=1)
    col_fill = (out > 0).mean(axis=0)
    out[row_fill > 0.9, :] = 0
    out[:, col_fill > 0.9] = 0
    return out

def _cut_tail(comp: np.ndarray) -> np.ndarray:
    ys, xs = np.where(comp > 0)
    if ys.size == 0:
        return comp
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    h = y1 - y0
    if h < 8:
        return comp
    body = comp[y0:y0 + int(0.5 * h), :]
    widths = (body > 0).sum(axis=1)
    widths = widths[widths > 0]
    if widths.size == 0:
        return comp
    med = float(np.median(widths))
    out = comp.copy()
    for y in range(y0 + int(0.7 * h), y1):
        if (out[y] > 0).sum() > 1.3 * med:
            out[y, :] = 0
    return out

def _debridging(bw: np.ndarray) -> np.ndarray:
    mask = (bw > 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return bw
    widths = [stats[i, cv2.CC_STAT_WIDTH] for i in range(1, n)]
    wmed = sorted(widths)[len(widths) // 2]
    out = np.zeros_like(bw)
    kern = np.ones((3, 3), np.uint8)
    for i in range(1, n):
        comp = ((labels == i).astype(np.uint8)) * 255
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        merged = w > 1.25 * max(1, h) or w > 2.2 * wmed
        if merged:
            comp = cv2.morphologyEx(comp, cv2.MORPH_OPEN, kern)
            comp = _cut_tail(comp)
        out = np.maximum(out, comp)
    return out

def prepare(crop: np.ndarray, spec: dict) -> np.ndarray:
    st = stretch(crop)
    color = spec.get("color")
    if color:
        hsv = cv2.cvtColor(st, cv2.COLOR_BGR2HSV)
        m = cv2.inRange(hsv, np.array(color["lo"], np.uint8), np.array(color["hi"], np.uint8))
        if int((m > 0).sum()) >= 20:
            # NEAREST: сохраняет тонкие (1px) перекладины без размазывания
            up = cv2.resize(m, None, fx=spec.get("scale", 4), fy=spec.get("scale", 4),
                            interpolation=cv2.INTER_NEAREST)
            return _debridging(_strip_lines(((up > 127).astype(np.uint8)) * 255))
    gray = cv2.cvtColor(st, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(gray, None, fx=spec.get("scale", 4), fy=spec.get("scale", 4),
                    interpolation=cv2.INTER_CUBIC)
    _, bw = cv2.threshold(up, 0, 255, cv2.THRESH_OTSU)
    if float((bw > 0).mean()) > 0.5:
        bw = 255 - bw
    return _debridging(_strip_lines(bw))

def hud_present(bw: np.ndarray) -> bool:
    return float((bw > 0).mean()) > 0.02
