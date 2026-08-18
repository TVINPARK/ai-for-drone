"""Конфигурация: дефолты + load/save (deep-merge, чтобы старые конфиги доживали)."""
from __future__ import annotations
import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "capture": {"backend": "auto", "monitor": 0, "fps_target": 0},
    "screen": {"width": 0, "height": 0},
    "rois": {},
    "sticks": {
        "left":  {"center": [0, 0], "radius_px": 60, "dot_rgb": [255, 255, 255],
                  "dot_hsv_lo": [0, 0, 180], "dot_hsv_hi": [180, 80, 255]},
        "right": {"center": [0, 0], "radius_px": 60, "dot_rgb": [255, 255, 255],
                  "dot_hsv_lo": [0, 0, 180], "dot_hsv_hi": [180, 80, 255]},
    },
    "ocr": {"engine": "template", "tess_cmd": "tesseract",
            "hz_fast": 10.0, "hz_slow": 1.0,
            "median_window": 5, "hold_last_valid_s": 1.0},
    "events": {"crash_speed_drop_s": 0.3, "hud_lost_s": 2.0, "timer_stuck_s": 3.0},
    "report": {"sectors_n": 3, "out_dir": "reports"},
    "db": {"path": "telemetry.db", "batch_ms": 500},
}

def config_path() -> Path:
    return Path(os.environ.get("QT_CONFIG", "config.json"))

def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def load_config(path=None) -> dict:
    p = Path(path) if path else config_path()
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return _deep_merge(DEFAULT_CONFIG, json.load(f))
    return json.loads(json.dumps(DEFAULT_CONFIG))

def save_config(cfg: dict, path=None) -> Path:
    p = Path(path) if path else config_path()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return p