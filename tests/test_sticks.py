"""
Тесты для модуля распознавания стиков (qt.sticks.detector).
"""
import pytest
import numpy as np
import cv2
from qt.sticks.detector import StickDetector


class TestStickDetector:
    """Тесты детектора положения стиков."""

    def test_detector_initialization(self):
        """Проверка инициализации детектора с конфигом по умолчанию."""
        detector = StickDetector()
        assert detector.min_area == 15
        assert detector.max_area == 800
        assert "sticks" in detector.config

    def test_detector_with_missing_config(self):
        """Проверка работы с отсутствующим конфигом (заглушка)."""
        detector = StickDetector(config_path="nonexistent.json")
        # Должна загрузиться заглушка
        assert "left" in detector.config["sticks"]
        assert "right" in detector.config["sticks"]
        # Проверяем что координаты соответствуют калиброванным
        assert detector.config["sticks"]["left"]["center"] == [570, 1000]
        assert detector.config["sticks"]["right"]["center"] == [1022, 1000]

    def test_synthetic_stick_detection(self):
        """Тест на синтетическом изображении с яркой точкой."""
        detector = StickDetector()
        
        # Создаем синтетический кадр 1920x1080
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        # Используем центры из заглушки конфига: left center=[570, 1000]
        cx, cy = 570, 1000
        
        # Рисуем яркий цветной круг радиусом 10 пикселей
        cv2.circle(frame, (cx, cy), 10, (255, 255, 255), -1)
        
        result = detector.detect(frame)
        
        # Проверка что точка найдена
        assert result.lx is not None
        assert result.ly is not None
        
        # В центре нормализованные значения должны быть близки к 0
        assert abs(result.lx) < 0.15
        assert abs(result.ly) < 0.15

    def test_stick_center_position(self):
        """Тест нейтрального положения стика (точка в центре)."""
        detector = StickDetector()
        
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cx, cy = 570, 1000
        
        # Точка ровно в центре
        cv2.circle(frame, (cx, cy), 10, (255, 255, 255), -1)
        
        result = detector.detect(frame)
        
        # В центре нормализованные значения должны быть близки к 0
        assert result.lx is not None
        assert result.ly is not None
        assert abs(result.lx) < 0.15
        assert abs(result.ly) < 0.15

    def test_stick_edge_positions(self):
        """Тест крайних положений стика."""
        detector = StickDetector()
        
        cx, cy = 570, 1000
        radius = 70
        
        # Тест правого края (x = +1)
        frame_right = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.circle(frame_right, (cx + radius - 5, cy), 10, (255, 255, 255), -1)
        result_right = detector.detect(frame_right)
        
        assert result_right.lx is not None
        assert result_right.lx > 0.7
        
        # Тест левого края (x = -1)
        frame_left = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.circle(frame_left, (cx - radius + 5, cy), 10, (255, 255, 255), -1)
        result_left = detector.detect(frame_left)
        
        assert result_left.lx is not None
        assert result_left.lx < -0.7
        
        # Тест верхнего края (y = +1, т.к. инверсия)
        frame_up = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.circle(frame_up, (cx, cy - radius + 5), 10, (255, 255, 255), -1)
        result_up = detector.detect(frame_up)
        
        assert result_up.ly is not None
        assert result_up.ly > 0.7

    def test_both_sticks_detection(self):
        """Тест одновременного обнаружения обоих стиков."""
        detector = StickDetector()
        
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        # Левый стик: центр [570, 1000]
        cv2.circle(frame, (570, 1000), 10, (255, 255, 255), -1)
        
        # Правый стик: центр [1022, 1000]
        cv2.circle(frame, (1022, 1000), 10, (255, 255, 255), -1)
        
        result = detector.detect(frame)
        
        assert result.lx is not None
        assert result.rx is not None
        
        # Оба должны быть близко к центру
        assert abs(result.lx) < 0.15
        assert abs(result.ly) < 0.15
        assert abs(result.rx) < 0.15
        assert abs(result.ry) < 0.15

    def test_no_point_detected(self):
        """Тест когда точек нет — должно вернуть None."""
        detector = StickDetector()
        
        # Пустой черный кадр
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        result = detector.detect(frame)
        
        # Точки не найдены - все значения None
        assert result.lx is None
        assert result.ly is None
        assert result.rx is None
        assert result.ry is None

    def test_color_threshold_detection(self):
        """Тест обнаружения точки с заданным цветовым порогом HSV."""
        detector = StickDetector()
        
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        # Рисуем точку в HSV пространстве
        #HSV: H=60 (желтый), S=200, V=255
        hsv_color = np.array([[[60, 200, 255]]], dtype=np.uint8)
        bgr_color = cv2.cvtColor(hsv_color, cv2.COLOR_HSV2BGR)[0][0]
        
        cv2.circle(frame, (570, 1000), 12, tuple(map(int, bgr_color)), -1)
        
        # Устанавливаем пороги для желтого цвета
        detector.set_color_range("left", [50, 150, 200], [70, 255, 255])
        
        result = detector.detect(frame)
        
        assert result.lx is not None

    def test_normalization_bounds(self):
        """Проверка что нормализованные значения всегда в [-1, 1]."""
        detector = StickDetector()
        
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        
        # Точка далеко за пределами радиуса (должна обрезаться до ±1)
        cv2.circle(frame, (570 + 100, 1000 + 100), 10, (255, 255, 255), -1)
        
        result = detector.detect(frame)
        
        if result.lx is not None:
            assert -1.0 <= result.lx <= 1.0
            assert -1.0 <= result.ly <= 1.0
