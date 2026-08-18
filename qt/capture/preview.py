"""Live-превью: FPS, оверлей ROI и центров стиков. Проверка захвата и калибровки."""
from __future__ import annotations
import cv2

from ..core.config import load_config
from ..core.queue import DropOldestQueue, LatestSlot
from .roi import RoiRegistry
from .source import CaptureThread, create_source

def main():
    cfg = load_config()
    src = create_source(cfg)
    q_stick, q_ocr = DropOldestQueue(4), LatestSlot()
    thr = CaptureThread(src, [q_stick, q_ocr])
    thr.start()
    rois = RoiRegistry(cfg)
    print(f"backend={src.name}; 'q' в окне — стоп")
    try:
        while True:
            item = q_ocr.get(timeout=1.0)
            if item is None:
                continue
            view = rois.draw(item.img) if rois.rois else item.img.copy()
            for side in ("left", "right"):
                st = cfg["sticks"][side]
                if tuple(st["center"]) != (0, 0):
                    cv2.circle(view, tuple(st["center"]), st["radius_px"], (255, 200, 0), 1)
            cv2.putText(view, f"fps={thr.fps:.0f} frames={thr.frames} backend={src.name}",
                        (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
            H, W = view.shape[:2]
            scale = min(1.0, 1600 / W)
            if scale < 1.0:
                view = cv2.resize(view, (int(W * scale), int(H * scale)))
            cv2.imshow("qt-preview", view)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        thr.stop(); thr.join(timeout=2)
        src.stop()
        cv2.destroyAllWindows()
        print(f"done: frames={thr.frames} fps={thr.fps:.1f} black_warn={thr.black_frames_warn}")

if __name__ == "__main__":
    main()