"""
Модуль распознавания положения стиков управления (CV).
Использует OpenCV для поиска цветных маркеров положения стиков относительно центров крестов.
Возвращает нормализованные значения осей в диапазоне [-1.0, 1.0].

Конфигурация ожидает формат из config.json:
{
  "sticks": {
    "left": {
      "center": [x, y],       # центр крестика на полном экране
      "radius_px": 65,        # радиус зоны вокруг центра
      "dot_hsv_lo": [...],    # нижний порог HSV для точки
      "dot_hsv_hi": [...]     # верхний порог HSV для точки
    },
    "right": {...}
  }
}
"""
import cv2
import numpy as np
from typing import Optional, Tuple, Dict, Any, List
import json

from ..core.frame import Sticks


class StickDetector:
    """
    Детектор положения стиков управления по цветным маркерам.
    
    Атрибуты:
        config: Словарь конфигурации из config.json
        min_area: Минимальная площадь пятна (пиксели)
        max_area: Максимальная площадь пятна
    """
    
    def __init__(self, config_path: str = "config.json"):
        # Если передан словарь, используем его напрямую
        if isinstance(config_path, dict):
            self.config = config_path
        else:
            self.config = self._load_config(config_path)
        
        # Параметры детекции
        self.min_area = 15       # Минимальная площадь пятна
        self.max_area = 800      # Максимальная площадь
        
        # Кэш для оптимизации
        self._kernel = np.ones((3, 3), np.uint8)

    def _load_config(self, path: str) -> dict:
        """Загружает конфигурацию из JSON файла."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw_config = json.load(f)
        except FileNotFoundError:
            # Заглушка для тестов
            return {
                "sticks": {
                    "left": {
                        "center": [570, 1000],
                        "radius_px": 70,
                        "dot_hsv_lo": [4, 19, 84],
                        "dot_hsv_hi": [64, 119, 255]
                    },
                    "right": {
                        "center": [1022, 1000],
                        "radius_px": 70,
                        "dot_hsv_lo": [5, 15, 104],
                        "dot_hsv_hi": [65, 115, 255]
                    }
                }
            }
        
        # Нормализация формата конфига: поддержка как "center": [x,y], 
        # так и раздельных "center_x", "center_y"
        normalized = {"sticks": {}}
        sticks_raw = raw_config.get("sticks", {})
        
        for side in ["left", "right"]:
            if side not in sticks_raw:
                continue
                
            cfg = sticks_raw[side].copy()
            
            # Если есть center_x и center_y, преобразуем в center
            if "center_x" in cfg and "center_y" in cfg:
                cfg["center"] = [cfg["center_x"], cfg["center_y"]]
                del cfg["center_x"]
                del cfg["center_y"]
            
            # Если есть radius, переименуем в radius_px
            if "radius" in cfg and "radius_px" not in cfg:
                cfg["radius_px"] = cfg["radius"]
                del cfg["radius"]
                
            # Если есть color_lo/color_hi, переименуем в dot_hsv_lo/dot_hsv_hi
            if "color_lo" in cfg and "dot_hsv_lo" not in cfg:
                cfg["dot_hsv_lo"] = cfg["color_lo"]
                del cfg["color_lo"]
            if "color_hi" in cfg and "dot_hsv_hi" not in cfg:
                cfg["dot_hsv_hi"] = cfg["color_hi"]
                del cfg["color_hi"]
            
            normalized["sticks"][side] = cfg
        
        return normalized

    def _get_roi_bounds(self, stick_cfg: dict, frame_shape: tuple) -> Optional[Tuple[int, int, int, int]]:
        """
        Вычисляет границы ROI для стика на основе центра и радиуса.
        
        Args:
            stick_cfg: Конфигурация стика из config.json
            frame_shape: (height, width) кадра
            
        Returns:
            (x, y, w, h) или None если за границами кадра
        """
        cx, cy = stick_cfg["center"]
        radius = stick_cfg.get("radius_px", 65)
        
        # Размер зоны = 2 * радиус + небольшой запас
        size = int(radius * 2.2)
        half = size // 2
        
        x = max(0, cx - half)
        y = max(0, cy - half)
        w = size
        h = size
        
        # Проверка границ
        if x >= frame_shape[1] or y >= frame_shape[0]:
            return None
            
        # Обрезка по правому/нижнему краю с сохранением размера ROI
        # Если центр слишком близко к краю, смещаем ROI влево/вверх
        if x + w > frame_shape[1]:
            x = max(0, frame_shape[1] - w)
        if y + h > frame_shape[0]:
            y = max(0, frame_shape[0] - h)
            
        # Финальная проверка после смещения
        if x + w > frame_shape[1]:
            w = frame_shape[1] - x
        if y + h > frame_shape[0]:
            h = frame_shape[0] - y
            
        return (x, y, w, h)

    def detect(self, frame: np.ndarray) -> Sticks:
        """
        Основной метод детекции положения стиков.
        
        Args:
            frame: Кадр изображения (BGR, numpy array)
            
        Returns:
            Объект Sticks с нормализованными значениями осей [-1.0, 1.0]
        """
        left_x, left_y = 0.0, 0.0
        right_x, right_y = 0.0, 0.0
        left_detected = False
        right_detected = False

        sticks_config = self.config.get("sticks", {})
        frame_shape = frame.shape[:2]  # (height, width)
        
        for side in ["left", "right"]:
            if side not in sticks_config:
                continue
                
            stick_cfg = sticks_config[side]
            roi_bounds = self._get_roi_bounds(stick_cfg, frame_shape)
            
            if roi_bounds is None:
                continue
                
            x_roi, y_roi, w, h = roi_bounds
            roi = frame[y_roi:y_roi+h, x_roi:x_roi+w]
            
            # Извлекаем пороги HSV из конфига
            hsv_lo = np.array(stick_cfg.get("dot_hsv_lo", [0, 0, 180]))
            hsv_hi = np.array(stick_cfg.get("dot_hsv_hi", [180, 80, 255]))
            
            # Поиск точки
            point_pos = self._find_stick_point(roi, hsv_lo, hsv_hi)
            
            if point_pos is not None:
                px_roi, py_roi = point_pos  # Координаты внутри ROI
                
                # Абсолютные координаты точки на полном кадре
                px_abs = x_roi + px_roi
                py_abs = y_roi + py_roi
                
                # Центр крестика из конфига (абсолютные координаты)
                cx, cy = stick_cfg["center"]
                
                # Нормализация относительно центра крестика и радиуса
                radius = stick_cfg.get("radius_px", 65)
                
                # X: вправо = положительно
                norm_x = (px_abs - cx) / radius
                # Y: вверх = положительно (инверсия т.к. в изображении Y растет вниз)
                norm_y = -(py_abs - cy) / radius
                
                # Ограничение диапазона [-1, 1]
                norm_x = max(-1.0, min(1.0, norm_x))
                norm_y = max(-1.0, min(1.0, norm_y))
                
                if side == "left":
                    left_x = float(norm_x)
                    left_y = float(norm_y)
                    left_detected = True
                else:
                    right_x = float(norm_x)
                    right_y = float(norm_y)
                    right_detected = True
        
        # Возвращаем объект Sticks
        # lx=roll, ly=throttle (left stick), rx=yaw/roll, ry=pitch (right stick)
        return Sticks(
            lx=left_x if left_detected else None,
            ly=left_y if left_detected else None,
            rx=right_x if right_detected else None,
            ry=right_y if right_detected else None
        )

    def _find_stick_point(self, roi: np.ndarray, 
                          hsv_lo: np.ndarray, 
                          hsv_hi: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        Ищет маркер положения стика в ROI.
        
        Стратегия:
        1. Маска по цвету в HSV
        2. Морфологическая фильтрация шума
        3. Поиск наибольшего контура подходящего размера
        4. Возврат центра масс контура (без морфологии для точности)
        5. Fallback на яркостную маску если цвет не найден
        
        Args:
            roi: Область интереса (BGR)
            hsv_lo: Нижний порог HSV
            hsv_hi: Верхний порог HSV
            
        Returns:
            (x, y) центра точки относительно ROI или None
        """
        if roi.size == 0:
            return None

        # Конвертация в HSV
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        # Маска по цвету
        mask = cv2.inRange(hsv, hsv_lo, hsv_hi)
        
        # Легкая морфология только для удаления одиночных пикселей шума
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(mask, kernel, iterations=1)
        eroded = cv2.erode(dilated, kernel, iterations=1)
        
        # Поиск контуров на очищенной маске
        contours, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, 
                                        cv2.CHAIN_APPROX_SIMPLE)
        
        best_contour = None
        max_area = 0
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self.min_area < area < self.max_area:
                if area > max_area:
                    max_area = area
                    best_contour = cnt
        
        if best_contour is not None:
            M = cv2.moments(best_contour)
            if M["m00"] != 0:
                cX = int(M["m10"] / M["m00"])
                cY = int(M["m01"] / M["m00"])
                return (cX, cY)
        
        # Fallback: поиск по яркости (для белых/серых маркеров)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        contours, _ = cv2.findContours(bright_mask, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if self.min_area < area < self.max_area:
                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cX = int(M["m10"] / M["m00"])
                    cY = int(M["m01"] / M["m00"])
                    return (cX, cY)

        return None
    
    def set_color_range(self, side: str, lo: List[int], hi: List[int]) -> None:
        """
        Динамическое изменение цветового диапазона для калибровки.
        
        Args:
            side: "left" или "right"
            lo: Нижний порог HSV [h, s, v]
            hi: Верхний порог HSV [h, s, v]
        """
        if side in self.config.get("sticks", {}):
            self.config["sticks"][side]["dot_hsv_lo"] = lo
            self.config["sticks"][side]["dot_hsv_hi"] = hi
