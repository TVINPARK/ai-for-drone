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
    
    # Удаляем тонкие одиночные вертикальные линии (артефакты масштабирования)
    cols = (out > 0).sum(axis=0)
    
    # Находим основные сегменты (ширина > 3)
    main_segments = []
    start = None
    for x in range(cols.shape[0]):
        if cols[x] > 0 and start is None:
            start = x
        elif cols[x] == 0 and start is not None:
            if x - start > 3:
                main_segments.append((start, x))
            start = None
    if start is not None and cols.shape[0] - start > 3:
        main_segments.append((start, cols.shape[0]))
    
    # Вычисляем диапазон основных символов
    if main_segments:
        x_min_main = min(s[0] for s in main_segments)
        x_max_main = max(s[1] for s in main_segments)
        
        # Удаляем узкие изолированные сегменты далеко от основных символов
        for x in range(cols.shape[0]):
            if cols[x] > 0 and cols[x] < out.shape[0] * 0.3:
                # Проверяем является ли этот столбец частью узкого изолированного сегмента
                left = x
                while left > 0 and cols[left-1] > 0:
                    left -= 1
                right = x
                while right < cols.shape[0]-1 and cols[right+1] > 0:
                    right += 1
                seg_width = right - left + 1
                
                # Если сегмент узкий (<=4 пикселя) и высокий (>50% высоты изображения)
                # и находится далеко от основных символов - удаляем
                if seg_width <= 4 and cols[x] > out.shape[0] * 0.5:
                    dist_to_main = max(x_min_main - right, left - x_max_main, 0)
                    if dist_to_main > 8:
                        out[:, left:right+1] = 0
    
    # Дополнительная очистка: удаляем очень узкие сегменты (1-2 пикселя) 
    # которые находятся далеко от основных символов
    segs = []
    start = None
    for x in range(cols.shape[0]):
        if cols[x] > 0 and start is None:
            start = x
        elif cols[x] == 0 and start is not None:
            segs.append((start, x))
            start = None
    if start is not None:
        segs.append((start, cols.shape[0]))
    
    # Если есть очень узкие сегменты (ширина <= 2) перед основными символами,
    # и они отделены большим промежутком, удаляем их как артефакты
    if len(segs) >= 2:
        main_segs = [(s0, s1) for s0, s1 in segs if (s1 - s0) > 2]
        if main_segs:
            first_main_x = main_segs[0][0]
            for s0, s1 in segs:
                if s1 - s0 <= 2 and s1 < first_main_x - 5:
                    out[:, s0:s1] = 0
    
    return out

def segment(bw, min_h_ratio=MIN_H_RATIO, merge_gap=2):
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
        # Разделяем аномально широкие сегменты (вероятно слипшиеся символы)
        final_seg = []
        for s in seg:
            x0, x1, t, b = s
            w = x1 - x0
            # Если сегмент шире 2.5 медиан, пытаемся разделить его по разрывам
            if w > 2.5 * wmed:
                bw_slice = bw[t:b+1, x0:x1]
                sub_cols = (bw_slice > 0).sum(axis=0)
                sub_segments = _find_sub_segments(sub_cols, x0, bw_slice)
                if sub_segments:
                    # Корректируем Y координаты относительно оригинального t
                    corrected = [(sx, ex, t + sy, t + ey) for (sx, ex, sy, ey) in sub_segments]
                    final_seg.extend(corrected)
                else:
                    final_seg.append(s)
            else:
                final_seg.append(s)
        seg = final_seg
    return seg

def _find_sub_segments(cols, x_offset, bw_slice, gap_threshold=2):
    """Находит подсегменты внутри широкого сегмента по разрывам."""
    result = []
    in_seg = False
    start = None
    for x, count in enumerate(cols):
        if count > 0 and not in_seg:
            start = x
            in_seg = True
        elif count == 0 and in_seg:
            end = x
            # Проверяем есть ли следующий символ nearby
            next_start = None
            for nx in range(end, len(cols)):
                if cols[nx] > 0:
                    next_start = nx
                    break
            if next_start is not None and next_start - end <= gap_threshold:
                continue
            # Добавляем найденный подсегмент с правильными Y координатами
            ys_in_slice = np.where(bw_slice[:, start:end] > 0)[0]
            if ys_in_slice.size:
                y_min = int(ys_in_slice.min())
                y_max = int(ys_in_slice.max())
                result.append((x_offset + start, x_offset + end, y_min, y_max))
            in_seg = False
            start = None
    if in_seg and start is not None:
        end = len(cols)
        ys_in_slice = np.where(bw_slice[:, start:end] > 0)[0]
        if ys_in_slice.size:
            y_min = int(ys_in_slice.min())
            y_max = int(ys_in_slice.max())
            result.append((x_offset + start, x_offset + end, y_min, y_max))
    
    # Если нашли только один подсегмент но он всё ещё аномально широкий,
    # пробуем разделить его по локальному минимуму профиля
    if len(result) == 1:
        x0, x1, y0, y1 = result[0]
        w = x1 - x0
        if w > 20:  # Слишком широко для одного символа
            sub_cols = (bw_slice[:, :] > 0).sum(axis=0)
            # Ищем локальный минимум в средней трети
            mid_start = w // 3
            mid_end = 2 * w // 3
            min_val = float('inf')
            min_x = -1
            for x in range(mid_start, mid_end):
                if sub_cols[x] < min_val:
                    min_val = sub_cols[x]
                    min_x = x
            # Разделяем если минимум достаточно глубокий
            if min_x > 0 and min_val < sub_cols[mid_start] * 0.5:
                result = [
                    (x_offset, x_offset + min_x, y0, y1),
                    (x_offset + min_x, x_offset + len(cols), y0, y1)
                ]
    
    return result

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
