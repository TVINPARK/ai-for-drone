"""Unicode-безопасные imread/imwrite для Windows."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import cv2

def imread_u(path, flags=cv2.IMREAD_COLOR):
    p = Path(path)
    if not p.exists():
        return None
    data = np.fromfile(str(p), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)

def imwrite_u(path, img, params=None):
    ext = Path(path).suffix or ".png"
    ok, buf = cv2.imencode(ext, img, params or [])
    if not ok:
        return False
    buf.tofile(str(path))
    return True
