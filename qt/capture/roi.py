"""Реестр ROI: кропы с клиппингом по границам кадра + оверлей для превью."""
from __future__ import annotations
import numpy as np
import cv2

class RoiRegistry:
    def __init__(self, cfg: dict):
        self.rois = {k: [int(v) for v in r] for k, r in cfg.get("rois", {}).items()}

    def has(self, name: str) -> bool:
        return name in self.rois

    def rect(self, name: str):
        return tuple(self.rois[name])

    def crop(self, img: np.ndarray, name: str) -> np.ndarray:
        x, y, w, h = self.rois[name]
        H, W = img.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(H, y + h)
        return np.ascontiguousarray(img[y0:y1, x0:x1])

    def draw(self, img: np.ndarray, active=None) -> np.ndarray:
        out = img.copy()
        for name, (x, y, w, h) in self.rois.items():
            col = (0, 0, 255) if name == active else (0, 255, 0)
            cv2.rectangle(out, (x, y), (x + w, y + h), col, 1)
            cv2.putText(out, name, (x, max(11, y - 3)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1)
        return out