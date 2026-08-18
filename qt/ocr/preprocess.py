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
    
    # Собираем информацию о всех компонентах
    components = []
    for i in range(1, n):
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        comp = ((labels == i).astype(np.uint8)) * 255
        components.append({'idx': i, 'x': x, 'y': y, 'w': w, 'h': h, 'comp': comp})
    
    # Сортируем по x-координате
    components.sort(key=lambda c: c['x'])
    
    # Находим основные символы (широкие и высокие)
    # Цифры: ширина >= 8, высота >= 20
    # Двоеточие: ширина 4-8, высота < 20 (состоит из двух частей)
    main_symbols = [c for c in components if c['w'] >= 8 or c['h'] >= 20]
    
    if len(main_symbols) < 3:
        # Если мало основных символов, используем все компоненты шириной > 4
        main_symbols = [c for c in components if c['w'] > 4]
    
    if not main_symbols:
        return bw
    
    # Вычисляем медианную высоту основных символов
    heights = [c['h'] for c in main_symbols]
    hmed = sorted(heights)[len(heights) // 2]
    
    # Вычисляем диапазон X основных символов
    x_min = min(c['x'] for c in main_symbols)
    x_max = max(c['x'] + c['w'] for c in main_symbols)
    
    out = np.zeros_like(bw)
    kern = np.ones((3, 3), np.uint8)
    
    for c in components:
        x, y, w, h = c['x'], c['y'], c['w'], c['h']
        comp = c['comp']
        
        # Проверяем не является ли компонент слипшимся символом
        merged = w > 1.25 * max(1, h) or w > 2.2 * (w if not main_symbols else main_symbols[0]['w'])
        if merged:
            comp = cv2.morphologyEx(comp, cv2.MORPH_OPEN, kern)
            comp = _cut_tail(comp)
            # Обновляем параметры после морфологии
            ys, xs = np.where(comp > 0)
            if ys.size == 0:
                continue
            x = int(xs.min())
            y = int(ys.min())
            w = int(xs.max()) - x + 1
            h = int(ys.max()) - y + 1
        
        # Фильтр 1: Узкие вертикальные линии далеко от основных символов
        if w <= 4 and h > 15:
            # Проверяем расстояние до ближайшего основного символа
            dist_to_nearest = min(abs(x - mc['x']) + abs(y - mc['y']) for mc in main_symbols)
            if dist_to_nearest > 10:
                continue
        
        # Фильтр 2: Компоненты далеко слева/справа от основного диапазона
        if w <= 8:
            if x < x_min - 12 or x > x_max:
                continue
        
        # Фильтр 3: Узкие высокие линии между основными символами (артефакты разделителей)
        if w <= 4 and h > 0.6 * hmed:
            # Проверяем есть ли соседи слева и справа
            left_exists = any(mc['x'] + mc['w'] < x - 5 for mc in main_symbols)
            right_exists = any(mc['x'] > x + w + 5 for mc in main_symbols)
            if left_exists and right_exists:
                # Это может быть артефакт разделителя - проверяем расстояние
                dist_left = min(x - (mc['x'] + mc['w']) for mc in main_symbols if mc['x'] + mc['w'] < x)
                dist_right = min(mc['x'] - (x + w) for mc in main_symbols if mc['x'] > x + w)
                if dist_left < 20 and dist_right < 20:
                    continue
        
        # Фильтр 4: Очень маленькие компоненты (< 20 пикселей总面积)
        area = (comp > 0).sum()
        if area < 20 and w <= 4 and h <= 8:
            continue
        
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
