"""Источники кадров: dxcam (Desktop Duplication, GPU) с фолбэком на mss."""
from __future__ import annotations
import threading
import time
import cv2
from collections import deque
import numpy as np

from ..core.frame import Frame

class VideoCaptureSource:
    """Источник кадров из видеофайла."""
    name = "video"
    
    def __init__(self, video_path: str):
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise IOError(f"Не удалось открыть видеофайл: {video_path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        
    def grab(self):
        ret, frame = self.cap.read()
        if not ret:
            return time.perf_counter(), None
        t = time.perf_counter()
        return t, frame
    
    def stop(self):
        self.cap.release()


class MssSource:
    name = "mss"
    def __init__(self, monitor=0):
        import mss
        self._sct = mss.mss()
        idx = monitor + 1  # 0 = первичный монитор (monitors[1]); 0-й индекс mss = весь virtual screen
        self._mon = self._sct.monitors[idx] if idx < len(self._sct.monitors) else self._sct.monitors[0]

    def grab(self):
        t = time.perf_counter()
        shot = self._sct.grab(self._mon)
        arr = np.frombuffer(shot.raw, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        return t, np.ascontiguousarray(arr[:, :, :3])  # BGRA -> BGR

    def stop(self):
        self._sct.close()

class DxCamSource:
    name = "dxcam"
    def __init__(self, monitor=0, fps_target=0):
        import sys
        if sys.platform != "win32":
            raise ImportError("DxCam only works on Windows")
        import dxcam
        self._cam = dxcam.create(output_idx=monitor)
        self._cam.start(target_fps=fps_target if fps_target > 0 else 240, video_mode=True)

    def grab(self):
        t = time.perf_counter()
        f = self._cam.get_latest_frame()
        if f is None:
            return t, None
        return t, np.ascontiguousarray(f[:, :, ::-1])  # RGB -> BGR

    def stop(self):
        try:
            self._cam.stop()
        except Exception:
            pass

def create_source(cfg: dict):
    cap = cfg.get("capture", {})
    backend = cap.get("backend", "auto")
    mon = int(cap.get("monitor", 0))
    fps = int(cap.get("fps_target", 0))
    if backend in ("auto", "dxcam"):
        try:
            return DxCamSource(monitor=mon, fps_target=fps)
        except Exception as e:
            if backend == "dxcam":
                raise
            print(f"[capture] dxcam недоступен ({e}); fallback на mss")
    return MssSource(monitor=mon)

class CaptureThread(threading.Thread):
    """Поток захвата: раскладывает кадры в очереди, считает FPS, следит за чёрным кадром."""
    def __init__(self, source, queues, name="qt-capture"):
        super().__init__(daemon=True, name=name)
        self.source = source
        self.queues = queues
        self._stop = threading.Event()
        self._times = deque(maxlen=512)
        self.frames = 0
        self.black_frames_warn = False

    def run(self):
        while not self._stop.is_set():
            t, img = self.source.grab()
            if img is None:
                time.sleep(0.0005)
                continue
            self.frames += 1
            self._times.append(t)
            if self.frames % 30 == 0 and float(img.mean()) < 8.0:
                self.black_frames_warn = True  # похоже на exclusive fullscreen
            item = Frame(t=t, img=img)
            for q in self.queues:
                q.put(item)

    @property
    def fps(self) -> float:
        now = time.perf_counter()
        recent = [x for x in self._times if now - x < 2.0]
        if len(recent) < 2:
            return 0.0
        return (len(recent) - 1) / (recent[-1] - recent[0])

    def stop(self):
        self._stop.set()