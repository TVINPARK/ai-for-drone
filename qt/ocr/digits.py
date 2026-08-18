"""Самообучаемый шаблонный распознаватель символов HUD."""
from __future__ import annotations
import numpy as np
import cv2

CHAR_H, CHAR_W = 32, 20
PATTERNS = {
    "hms": (12, {2, 5, 8}),
    "mmss": (5, {2}),
    "dt": (16, {2, 5, 10, 13}),
    "battery": (9, {2, 6}),
    "laps": (3, set()),
}
SHORT_H = 0.70
MIN_H_RATIO = 0.2
MIN_H_ABS = 6

def _strip_lines(bw):
    out = bw.copy()
    row_fill = (out > 0).mean(axis=1)
    col_fill = (out > 0).mean(axis=0)
    out[row_fill > 0.9, :] = 0
    out[:, col_fill > 0.9] = 0
    return out

def segment(bw, min_h_ratio=MIN_H_RATIO, merge_gap=0):
    bw = _strip_lines(bw)
    cols = (bw > 0).sum(axis=0)
    raw, start = [], None
    for x in range(cols.shape[0]):
        if cols[x] > 0 and start is None:
            start = x
        elif cols[x] == 0 and start is not None:
            raw.append([start, x]); start = None
    if start is not None:
        raw.append([start, cols.shape[0]])
    merged = []
    for g in raw:
        if merged and g[0] - merged[-1][1] <= merge_gap:
            merged[-1][1] = g[1]
        else:
            merged.append(g)
    seg = []
    for x0, x1 in merged:
        ys = np.where(bw[:, x0:x1] > 0)[0]
        if ys.size:
            seg.append((x0, x1, int(ys.min()), int(ys.max())))
    if not seg:
        return []
    hmax = max(b - t for (_, _, t, b) in seg)
    floor = max(min_h_ratio * hmax, MIN_H_ABS)
    seg = [s for s in seg if (s[3] - s[2]) >= floor and (s[1] - s[0]) >= 2]
    if len(seg) >= 3:
        widths = sorted(x1 - x0 for (x0, x1, _, _) in seg)
        wmed = widths[len(widths) // 2]
        seg = [s for s in seg if (s[1] - s[0]) <= 4.0 * wmed]
    return seg

def window_for(segs, kind):
    if not segs or kind is None:
        return segs
    if kind in PATTERNS:
        n, small = PATTERNS[kind]
        if len(segs) >= n:
            for i in range(len(segs) - n + 1):
                w = segs[i:i + n]
                hmax = max(s[3] - s[2] for s in w)
                if hmax <= 0:
                    continue
                if all(((s[3] - s[2]) / hmax < SHORT_H) == (j in small) for j, s in enumerate(w)):
                    if kind == "laps" and (w[1][1] - w[1][0]) > 0.7 * max(w[0][1] - w[0][0], w[2][1] - w[2][0]):
                        continue
                    return w
        return segs
    hmax = max(s[3] - s[2] for s in segs)
    tall = [s for s in segs if (s[3] - s[2]) >= 0.6 * hmax]
    return tall if tall else segs

def _norm(bw, x0, x1, t, b):
    ch = bw[t:b + 1, x0:x1]
    r = cv2.resize(ch, (CHAR_W, CHAR_H), interpolation=cv2.INTER_AREA)
    return (r > 127).astype(np.float32)

class TemplateEngine:
    def __init__(self, path=None):
        self.atlas = {}
        if path:
            self.load(path)

    @property
    def trained(self):
        return bool(self.atlas)

    def train(self, bw, text, kind=None):
        seg = window_for(segment(bw), kind)
        if len(seg) != len(text):
            return False
        for s, ch in zip(seg, text):
            if ch == " ":
                continue
            if len(self.atlas.setdefault(ch, [])) < 24:
                self.atlas[ch].append(_norm(bw, *s))
        return True

    def recognize(self, bw, kind=None):
        if not self.atlas:
            return "", 0.0
        seg = window_for(segment(bw), kind)
        if not seg:
            return "", 0.0
        out, worst = [], 1.0
        for s in seg:
            a = _norm(bw, *s)
            best_ch, best_sc = "", 0.0
            for ch, tpls in self.atlas.items():
                sc = max(_iou(a, t) for t in tpls)
                if sc > best_sc:
                    best_sc, best_ch = sc, ch
            out.append(best_ch)
            worst = min(worst, best_sc)
        return "".join(out), float(worst)

    def save(self, path):
        np.savez_compressed(path, **{("c%d" % ord(k)): np.stack(v) for k, v in self.atlas.items()})

    def load(self, path):
        z = np.load(path)
        self.atlas = {chr(int(k[1:])): [z[k][i] for i in range(z[k].shape[0])] for k in z.files}

def _iou(a, b):
    inter = float((a * b).sum())
    union = float(a.sum() + b.sum() - inter)
    return inter / union if union > 0 else 0.0
