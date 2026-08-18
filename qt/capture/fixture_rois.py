"""Грубые ROI по долям экрана (макет HUD из эталона, не зависит от разрешения).
   Затем snap доводит каждый прямоугольник до точного текстового блока.
   python -m qt.capture.fixture_rois --image tests/fixtures/screen_01.png"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path

from ..core.config import load_config, save_config, config_path
from ..core.io import imread_u

# (x, y, w, h) — доли ширины/высоты кадра, по эталонному скриншоту
FRACTIONS = {
    "pilot":     (0.017, 0.007, 0.230, 0.017),
    "datetime":  (0.023, 0.034, 0.080, 0.017),
    "battery":   (0.068, 0.063, 0.056, 0.015),
    "mode":      (0.023, 0.093, 0.050, 0.025),
    "limit":     (0.938, 0.053, 0.028, 0.016),
    "speed":     (0.065, 0.505, 0.030, 0.040),
    "alt":       (0.822, 0.514, 0.012, 0.022),
    "laps":      (0.042, 0.953, 0.024, 0.016),
    "cur_time":  (0.138, 0.952, 0.050, 0.017),
    "best_time": (0.920, 0.952, 0.053, 0.017),
}
PAD = 0.6  # расширение грубого бокса во все стороны (доля от его w/h)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    img = imread_u(args.image)
    if img is None:
        raise SystemExit("не читается image")
    H, W = img.shape[:2]

    cfg = load_config(args.config)
    p = config_path() if args.config is None else Path(args.config)
    if p.exists():
        shutil.copyfile(p, str(p) + ".bak")

    for name, (fx, fy, fw, fh) in FRACTIONS.items():
        w = fw * W * (1 + PAD)
        h = fh * H * (1 + PAD)
        x = fx * W - (w - fw * W) / 2
        y = fy * H - (h - fh * H) / 2
        cfg["rois"][name] = [int(max(0, x)), int(max(0, y)), int(w), int(h)]
    cfg["screen"] = {"width": int(W), "height": int(H)}
    print(f"coarse ROIs for {W}x{H} saved -> {save_config(cfg, p)}")

if __name__ == "__main__":
    main()