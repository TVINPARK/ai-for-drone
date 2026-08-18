"""Калибровка ROI и стиков мышью. Запуск:
   python -m qt.capture.calibrate --image tests/fixtures/screen_01.png
   python -m qt.capture.calibrate            # live-кадр из игры
Управление (ASCII, т.к. cv2.putText без кириллицы):
   ЛКМ-drag = ROI; в stick-режиме 1-й клик = центр, 2-й = радиус; ПКМ = сброс стика
   Tab/z = след./пред. поле; r/l/g = режим ROI/левый/правый стик
   c = сэмпл цвета точки; f = автоточнение центра креста; u = новый кадр; s = сохранить; q = выход
"""
from __future__ import annotations
import argparse
import time
import numpy as np
import cv2

from ..core.config import load_config, save_config
from ..core.frame import HUD_ROI_FIELDS
from ..core.io import imread_u
from .source import create_source

HELP = [
    "mode={mode} active={active}",
    "[Tab] next field [z] prev | [r] ROI  [l] stick-L  [g] stick-R",
    "LMB drag=ROI | stick: click1=center click2=radius | RMB=reset stick",
    "[c] dot color  [f] refine center  [u] grab  [s] save  [q] quit",
]

def refine_cross_center(crop: np.ndarray):
    """Точный центр креста по симметрии линий: строка/столбец с максимумом светлых
    пикселей вне центральной зоны (где точка). Возвращает ((cx, cy), conf)."""
    if crop is None or crop.size < 100:
        return (0, 0), 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    thr = np.percentile(gray, 85)
    mask = (gray > thr).astype(np.uint8)
    h, w = mask.shape
    cy0, cx0 = h // 2, w // 2
    band = max(6, min(h, w) // 8)
    if cx0 - band < 0 or cx0 + band >= w or cy0 - band < 0 or cy0 + band >= h:
        return (cx0, cy0), 0.0
    row_scores = mask[:, :cx0 - band].sum(1) + mask[:, cx0 + band:].sum(1)
    col_scores = mask[:cy0 - band, :].sum(0) + mask[cy0 + band:, :].sum(0)
    cy, cx = int(np.argmax(row_scores)), int(np.argmax(col_scores))
    conf = float(row_scores[cy] + col_scores[cx]) / max(1, int(mask.sum()))
    return (cx, cy), conf

class Calibrator:
    def __init__(self, cfg: dict, image=None, live_source=None):
        self.cfg = cfg
        self.frame = image
        self.src = live_source
        self.win = "qt-calibrate"
        self.mode = "roi"            # roi | left | right
        self.active = 0
        self.drag = None
        self.mouse = (0, 0)
        self.stage = {"left": 0, "right": 0}
        self.scale = 1.0             # даунскейл превью; маппинг мыши = 1/scale

    # ---------- служебное ----------
    def _refresh(self):
        if self.src is None:
            return
        for _ in range(30):
            _, img = self.src.grab()
            if img is not None:
                self.frame = img
                return
            time.sleep(0.1)

    def _to_img(self, x: int, y: int):
        # превью показывается с фиксированным даунскейлом self.scale — маппинг точный
        return int(round(x / self.scale)), int(round(y / self.scale))

    def _sample_color(self):
        if self.mode == "roi":
            print("sample: переключитесь в stick-режим (l/g)"); return
        x, y = self.mouse
        patch = self.frame[max(0, y - 2):y + 3, max(0, x - 2):x + 3]
        med = np.median(patch.reshape(-1, 3), axis=0).astype(np.uint8)   # BGR
        hsv = cv2.cvtColor(med.reshape(1, 1, 3), cv2.COLOR_BGR2HSV)[0, 0].astype(int)
        st = self.cfg["sticks"][self.mode]
        st["dot_rgb"] = [int(med[2]), int(med[1]), int(med[0])]
        st["dot_hsv_lo"] = [int(hsv[0]) - 12, max(0, int(hsv[1]) - 70), max(0, int(hsv[2]) - 90)]
        st["dot_hsv_hi"] = [int(hsv[0]) + 12, min(255, int(hsv[1]) + 70), 255]
        print(f"sampled {self.mode}: BGR={med.tolist()} HSV={hsv.tolist()}")

    def _refine(self):
        if self.mode == "roi":
            return
        st = self.cfg["sticks"][self.mode]
        cx, cy = st["center"]
        if (cx, cy) == (0, 0):
            print("refine: сначала задайте центр кликом"); return
        half = st["radius_px"] + 15
        H, W = self.frame.shape[:2]
        x0, y0 = max(0, cx - half), max(0, cy - half)
        crop = self.frame[y0:min(H, cy + half), x0:min(W, cx + half)]
        (dx, dy), conf = refine_cross_center(crop)
        if conf > 0.15:
            st["center"] = [x0 + dx, y0 + dy]
            print(f"refined {self.mode} -> {st['center']} conf={conf:.2f}")
        else:
            print(f"refine не удался (conf={conf:.2f}), оставлен ручной центр")

    def _save(self):
        H, W = self.frame.shape[:2]
        self.cfg["screen"] = {"width": int(W), "height": int(H)}
        print(f"saved -> {save_config(self.cfg)}")

    # ---------- мышь ----------
    def _on_mouse(self, event, x, y, flags, param):
        if self.frame is None:
            return
        x, y = self._to_img(x, y)
        self.mouse = (x, y)
        if self.mode == "roi":
            if event == cv2.EVENT_LBUTTONDOWN:
                self.drag = ((x, y), (x, y))
            elif event == cv2.EVENT_MOUSEMOVE and self.drag:
                self.drag = (self.drag[0], (x, y))
            elif event == cv2.EVENT_LBUTTONUP and self.drag:
                (x0, y0), (x1, y1) = self.drag
                if abs(x1 - x0) > 8 and abs(y1 - y0) > 8:
                    self.cfg["rois"][HUD_ROI_FIELDS[self.active]] = [
                        min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)]
                self.drag = None
        elif event == cv2.EVENT_LBUTTONDOWN:
            st = self.cfg["sticks"][self.mode]
            if self.stage[self.mode] == 0:
                st["center"] = [x, y]
                self.stage[self.mode] = 1
            else:
                cx, cy = st["center"]
                st["radius_px"] = max(10, int(round(np.hypot(x - cx, y - cy))))
                self.stage[self.mode] = 2
        elif event == cv2.EVENT_RBUTTONDOWN:
            self.cfg["sticks"][self.mode]["center"] = [0, 0]
            self.stage[self.mode] = 0

    # ---------- отрисовка ----------
    def _render(self):
        out = self.frame.copy()
        for i, name in enumerate(HUD_ROI_FIELDS):
            r = self.cfg["rois"].get(name)
            if not r:
                continue
            x, y, w, h = r
            col = (0, 0, 255) if (self.mode == "roi" and i == self.active) else (0, 255, 0)
            cv2.rectangle(out, (x, y), (x + w, y + h), col, 1)
            cv2.putText(out, name, (x, max(11, y - 3)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1)
        if self.drag:
            (x0, y0), (x1, y1) = self.drag
            cv2.rectangle(out, (x0, y0), (x1, y1), (0, 255, 255), 1)
        for side in ("left", "right"):
            st = self.cfg["sticks"][side]
            cx, cy = st["center"]
            if (cx, cy) != (0, 0):
                cv2.circle(out, (cx, cy), st["radius_px"], (255, 200, 0), 1)
                cv2.drawMarker(out, (cx, cy), (255, 200, 0), cv2.MARKER_CROSS, 10, 1)
                cv2.putText(out, side, (cx + 6, cy - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 200, 0), 1)
        H, W = out.shape[:2]
        panel = out[0:86, 0:W]
        panel[:] = (panel.astype(np.int32) // 2).astype(np.uint8)
        active = HUD_ROI_FIELDS[self.active] if self.mode == "roi" else self.mode
        for i, line in enumerate(HELP):
            cv2.putText(out, line.format(mode=self.mode, active=active),
                        (8, 16 + i * 18), cv2.FONT_HERSHEY_PLAIN, 0.9, (255, 255, 255), 1)
        return out

    # ---------- цикл ----------
    def run(self):
        while self.frame is None:
            self._refresh()
            if self.frame is None:
                time.sleep(0.05)
        H, W = self.frame.shape[:2]
        self.scale = min(1.0, 1600.0 / W, 900.0 / H)
        cv2.namedWindow(self.win, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.win, self._on_mouse)
        while True:
            view = self._render()
            if self.scale < 1.0:
                view = cv2.resize(view, (int(W * self.scale), int(H * self.scale)))
            cv2.imshow(self.win, view)
            k = cv2.waitKey(5) & 0xFF
            if k == 255:
                continue
            c = chr(k) if 32 <= k < 127 else ""
            if k == 9:
                self.active = (self.active + 1) % len(HUD_ROI_FIELDS)
            elif c == "z":
                self.active = (self.active - 1) % len(HUD_ROI_FIELDS)
            elif c == "r":
                self.mode = "roi"
            elif c == "l":
                self.mode = "left"
            elif c == "g":
                self.mode = "right"
            elif c == "u":
                self._refresh()
            elif c == "c":
                self._sample_color()
            elif c == "f":
                self._refine()
            elif c == "s":
                self._save()
            elif c == "q":
                break
        cv2.destroyAllWindows()

def main():
    ap = argparse.ArgumentParser(description="Калибровка ROI и стиков")
    ap.add_argument("--image", help="калибровка по скриншоту вместо live-кадра")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    src = None
    if args.image:
        img = imread_u(args.image)
        if img is None:
            raise SystemExit(f"не читается файл: {args.image}")
    else:
        src = create_source(cfg)
        img = None
    cal = Calibrator(cfg, image=img, live_source=src)
    try:
        cal.run()
    finally:
        if src is not None:
            src.stop()

if __name__ == "__main__":
    main()