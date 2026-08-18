"""
Генератор синтетических данных для тестирования без симулятора.
Создает последовательность кадров с изменяющимися показателями HUD и стиками.
"""

import cv2
import numpy as np
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from qt.core.frame import Frame, Hud, Sticks


@dataclass
class MockFlightConfig:
    """Конфигурация тестового полета."""
    resolution: tuple = (1920, 1080)
    fps: int = 60
    lap_duration_sec: float = 45.0  # Длительность круга в секундах
    total_laps: int = 2
    gate_detection_enabled: bool = False


class MockHudGenerator:
    """
    Генерирует синтетические кадры HUD для тестирования пайплайна.
    Эмулирует изменение всех полей HUD и движение стиков.
    """

    def __init__(self, config: Optional[MockFlightConfig] = None):
        self.config = config or MockFlightConfig()
        self.width, self.height = self.config.resolution
        self.fps = self.config.fps
        self.frame_interval = 1.0 / self.fps
        
        # Состояние полета
        self.current_lap = 0
        self.total_laps = self.config.total_laps
        self.lap_start_time = 0.0
        self.current_time_in_lap = 0.0
        self.best_lap_time = None  # Заполнится после первого круга
        
        # Физика эмуляции
        self.speed = 0.0
        self.altitude = 2.0
        self.battery_voltage = 22.2
        self.battery_current = 5.0
        
        # Стики (нормализованные -1..1)
        self.stick_throttle = 0.0
        self.stick_yaw = 0.0
        self.stick_pitch = 0.0
        self.stick_roll = 0.0
        
        # Внутренние таймеры
        self.start_time = time.time()
        self.is_flying = False
        self.frame_count = 0
        
        # ROI для генерации (должны совпадать с config.json для 1920x1080)
        self.rois = self._define_rois()

    def _define_rois(self) -> Dict[str, tuple]:
        """Определяет регионы интереса для рендеринга."""
        return {
            'pilot_info': (50, 30, 300, 80),
            'battery': (50, 100, 150, 60),
            'flight_mode': (50, 170, 100, 40),
            'time_limit': (1700, 30, 200, 60),
            'speed': (700, 400, 150, 200),
            'altitude': (1100, 400, 150, 200),
            'laps': (50, 900, 250, 80),
            'current_time': (50, 990, 200, 50),
            'best_time': (1600, 900, 250, 80),
            'stick_left': (700, 850, 200, 200),
            'stick_right': (1050, 850, 200, 200),
        }

    def reset(self):
        """Сброс состояния для нового полета."""
        self.current_lap = 0
        self.current_time_in_lap = 0.0
        self.best_lap_time = None
        self.speed = 0.0
        self.altitude = 2.0
        self.is_flying = False
        self.frame_count = 0
        self.start_time = time.time()
        self.stick_throttle = 0.0
        self.stick_yaw = 0.0
        self.stick_pitch = 0.0
        self.stick_roll = 0.0

    def _simulate_physics(self, dt: float):
        """Эмулирует простую физику полета."""
        if not self.is_flying:
            # На земле
            self.speed = max(0, self.speed - 10 * dt)
            self.altitude = max(0.5, self.altitude - 1 * dt)
            self.stick_throttle = max(0, self.stick_throttle - 0.5 * dt)
            return

        # Эмуляция управления
        target_speed = self.stick_throttle * 120  # Макс 120 км/ч
        self.speed += (target_speed - self.speed) * 0.5 * dt
        
        target_alt = self.stick_pitch * 10 + 5  # Базовая высота 5м
        self.altitude += (target_alt - self.altitude) * 0.3 * dt
        self.altitude = max(0.5, min(self.altitude, 50))
        
        # Трата батареи
        self.battery_current = 5.0 + abs(self.stick_throttle) * 30
        self.battery_voltage = max(18.0, self.battery_voltage - 0.0001 * self.battery_current * dt)

    def _update_sticks(self, t: float):
        """Эмулирует движение стиков пилотом (синусоиды + шум)."""
        if not self.is_flying:
            self.stick_throttle = 0.0
            self.stick_yaw = 0.0
            self.stick_pitch = 0.0
            self.stick_roll = 0.0
            return

        # Газ: плавный набор и удержание
        self.stick_throttle = 0.6 + 0.1 * np.sin(t * 0.5)
        
        # Рыскание: редкие коррекции
        self.stick_yaw = 0.1 * np.sin(t * 0.2)
        
        # Тангаж: управление высотой
        self.stick_pitch = 0.2 * np.sin(t * 0.3)
        
        # Крен: виражи на поворотах
        self.stick_roll = 0.4 * np.sin(t * 0.15)
        
        # Добавляем небольшой шум
        noise = 0.02
        self.stick_throttle += np.random.uniform(-noise, noise)
        self.stick_yaw += np.random.uniform(-noise, noise)
        self.stick_pitch += np.random.uniform(-noise, noise)
        self.stick_roll += np.random.uniform(-noise, noise)

    def _draw_text(self, img: np.ndarray, text: str, pos: tuple, 
                   color: tuple = (255, 255, 255), scale: float = 1.0):
        """Рисует текст на изображении."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        thickness = 2
        cv2.putText(img, text, pos, font, scale, color, thickness, cv2.LINE_AA)

    def _render_frame(self) -> np.ndarray:
        """Рендерит полный кадр HUD."""
        # Черный фон
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # 1. Пилот и дата (Верх-лево)
        x, y, w, h = self.rois['pilot_info']
        self._draw_text(img, "Region 1", (x, y + 20), (200, 200, 200), 0.7)
        self._draw_text(img, "Ivanov I.I.", (x, y + 50), (255, 255, 255), 0.8)
        
        # Дата/время
        current_real_time = time.strftime("%d.%m.%y %H:%M:%S")
        self._draw_text(img, current_real_time, (x, y + 75), (200, 200, 200), 0.5)

        # 2. Батарея (Верх-лево ниже)
        x, y, w, h = self.rois['battery']
        self._draw_text(img, f"{self.battery_voltage:.1f}V", (x, y + 20), (100, 255, 100), 0.8)
        self._draw_text(img, f"{self.battery_current:.1f}A", (x, y + 50), (200, 200, 200), 0.6)
        
        # Иконка батареи (простой прямоугольник)
        cv2.rectangle(img, (x + 100, y + 10), (x + 130, y + 40), (100, 255, 100), 2)
        fill_h = int(30 * (self.battery_voltage - 18.0) / (22.2 - 18.0))
        fill_h = max(0, min(30, fill_h))
        cv2.rectangle(img, (x + 102, y + 38 - fill_h), (x + 128, y + 38), (100, 255, 100), -1)

        # 3. Режим полета
        x, y, w, h = self.rois['flight_mode']
        self._draw_text(img, "ACRO", (x, y + 25), (255, 255, 0), 0.8)

        # 4. Лимит времени (Верх-право)
        x, y, w, h = self.rois['time_limit']
        limit_sec = 600  # 10 минут
        elapsed_total = self.current_lap * self.config.lap_duration_sec + self.current_time_in_lap
        remaining = max(0, limit_sec - elapsed_total)
        mm = int(remaining) // 60
        ss = int(remaining) % 60
        self._draw_text(img, f"ЛИМИТ {mm:02d}:{ss:02d}", (x, y + 30), (255, 200, 100), 0.8)

        # 5. Скорость (Центр-лево)
        x, y, w, h = self.rois['speed']
        speed_val = int(abs(self.speed))
        self._draw_text(img, f"{speed_val}", (x + 20, y + 50), (255, 255, 255), 2.0)
        self._draw_text(img, "КМ/Ч", (x + 20, y + 90), (200, 200, 200), 0.6)
        # Вертикальная шкала
        cv2.line(img, (x + 120, y + 20), (x + 120, y + 180), (255, 255, 255), 2)
        bar_h = int(160 * (speed_val / 150.0))
        bar_h = min(160, max(0, bar_h))
        cv2.rectangle(img, (x + 110, y + 180 - bar_h), (x + 130, y + 180), (0, 255, 255), -1)

        # 6. Высота (Центр-право)
        x, y, w, h = self.rois['altitude']
        alt_val = int(abs(self.altitude))
        self._draw_text(img, f"{alt_val}", (x + 20, y + 50), (255, 255, 255), 2.0)
        self._draw_text(img, "М", (x + 60, y + 55), (200, 200, 200), 0.8)
        # Вертикальная шкала
        cv2.line(img, (x + 120, y + 20), (x + 120, y + 180), (255, 255, 255), 2)
        bar_h = int(160 * (alt_val / 50.0))
        bar_h = min(160, max(0, bar_h))
        cv2.rectangle(img, (x + 110, y + 180 - bar_h), (x + 130, y + 180), (0, 255, 0), -1)

        # 7. Круги (Низ-лево)
        x, y, w, h = self.rois['laps']
        laps_display = min(self.current_lap, self.total_laps)
        self._draw_text(img, f"Круги: {laps_display} / {self.total_laps}", (x, y + 30), (255, 255, 255), 0.8)

        # 8. Текущее время (Низ-лево ниже)
        x, y, w, h = self.rois['current_time']
        if self.is_flying:
            m = int(self.current_time_in_lap) // 60
            s = self.current_time_in_lap % 60
            ms = int((s % 1) * 1000)
            self._draw_text(img, f"Текущее: {m:02d}:{s:05.2f}.{ms:03d}", (x, y + 30), (255, 255, 255), 0.7)
        else:
            self._draw_text(img, "Текущее: --:--.---", (x, y + 30), (150, 150, 150), 0.7)

        # 9. Лучшее время (Низ-право)
        x, y, w, h = self.rois['best_time']
        if self.best_lap_time is not None:
            m = int(self.best_lap_time) // 60
            s = self.best_lap_time % 60
            ms = int((s % 1) * 1000)
            self._draw_text(img, f"Лучшее: {m:02d}:{s:05.2f}.{ms:03d}", (x, y + 30), (0, 255, 255), 0.7)
        else:
            self._draw_text(img, "Лучшее: --:--.---", (x, y + 30), (150, 150, 150), 0.7)

        # 10. Стики (Низ-центр)
        self._render_stick(img, self.rois['stick_left'], self.stick_throttle, self.stick_yaw, "L")
        self._render_stick(img, self.rois['stick_right'], self.stick_pitch, self.stick_roll, "R")

        return img

    def _render_stick(self, img: np.ndarray, roi: tuple, val_y: float, val_x: float, label: str):
        """Рисует индикатор стика с крестом и точкой."""
        x, y, w, h = roi
        cx, cy = x + w // 2, y + h // 2
        radius = w // 2 - 10
        
        # Крест
        cv2.line(img, (cx - radius, cy), (cx + radius, cy), (100, 100, 100), 2)
        cv2.line(img, (cx, cy - radius), (cx, cy + radius), (100, 100, 100), 2)
        
        # Окружность
        cv2.circle(img, (cx, cy), radius, (100, 100, 100), 2)
        
        # Точка позиции (нормализация -1..1 в пиксели)
        px = cx + int(val_x * radius)
        py = cy - int(val_y * radius)  # Y инвертирован в изображениях
        
        # Цвет точки зависит от стика
        color = (0, 255, 255) if label == "L" else (255, 100, 255)
        cv2.circle(img, (px, py), 8, color, -1)
        
        # Подпись
        cv2.putText(img, label, (x + 10, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

    def step(self) -> Frame:
        """
        Выполняет один шаг симуляции и возвращает объект Frame.
        Автоматически управляет состоянием полета (старт/финиш кругов).
        """
        dt = self.frame_interval
        total_time = time.time() - self.start_time
        
        # Логика старта/финиша
        if not self.is_flying:
            # Авто-старт через 2 секунды после начала
            if total_time > 2.0 and self.current_lap < self.total_laps:
                self.is_flying = True
                self.current_lap += 1
                self.lap_start_time = total_time
                self.current_time_in_lap = 0.0
        else:
            self.current_time_in_lap = total_time - self.lap_start_time
            
            # Финиш круга
            if self.current_time_in_lap >= self.config.lap_duration_sec:
                lap_time = self.current_time_in_lap
                
                # Обновляем лучшее время
                if self.best_lap_time is None or lap_time < self.best_lap_time:
                    self.best_lap_time = lap_time
                
                self.is_flying = False
                self.current_time_in_lap = 0.0
                
                # Проверка окончания заезда
                if self.current_lap >= self.total_laps:
                    # Заезд окончен, больше не стартуем
                    pass
                else:
                    # Пауза между кругами 3 секунды
                    self.start_time = time.time() - 2.0  # Хак для быстрого рестарта

        # Обновление физики и стиков
        self._simulate_physics(dt)
        self._update_sticks(total_time)
        
        # Рендеринг
        image = self._render_frame()
        
        # Создание объекта Frame (эмуляция работы OCR и StickDetector)
        # В реальном приложении здесь были бы результаты OCR, но для мока мы знаем истинные значения
        hud = Hud(
            pilot="Ivanov I.I.",
            region="Region 1",
            dt_wall=time.strftime("%d.%m.%y %H:%M:%S"),
            bat_v=float(f"{self.battery_voltage:.1f}"),
            bat_a=float(f"{self.battery_current:.1f}"),
            mode="ACRO",
            limit_s=max(0, 600 - (self.current_lap * self.config.lap_duration_sec + self.current_time_in_lap)),
            speed=int(abs(self.speed)),
            alt=int(abs(self.altitude)),
            lap_cur=min(self.current_lap, self.total_laps),
            lap_tot=self.total_laps,
            cur_t=self.current_time_in_lap if self.is_flying else None,
            best_t=self.best_lap_time,
            hud_present=True
        )
        
        sticks = Sticks(
            ly=max(-1.0, min(1.0, self.stick_throttle)),  # газ
            lx=max(-1.0, min(1.0, self.stick_yaw)),       # руль
            ry=max(-1.0, min(1.0, self.stick_pitch)),     # тангаж
            rx=max(-1.0, min(1.0, self.stick_roll))       # крен
        )
        
        # Frame содержит только t и img. Hud и Sticks обрабатываются отдельно в пайплайне.
        # Для мока возвращаем Frame с img, а hud/sticks эмулируются через отдельные атрибуты
        frame = Frame(
            t=time.time(),
            img=image
        )
        # Сохраняем эталонные данные для последующей проверки (в реальном приложении их даст OCR/CV)
        frame.hud_ref = hud  # type: ignore
        frame.sticks_ref = sticks  # type: ignore
        
        self.frame_count += 1
        return frame

    def generate_flight_sequence(self, output_path: Optional[str] = None):
        """
        Генерирует полную последовательность кадров для одного заезда.
        Если output_path указан, сохраняет видеофайл.
        Возвращает список объектов Frame.
        """
        self.reset()
        frames = []
        
        # Длительность заезда: (круги * длительность) + паузы + буфер
        total_duration = (self.total_laps * self.config.lap_duration_sec) + 10.0
        total_frames = int(total_duration * self.fps)
        
        print(f"Генерация {total_frames} кадров ({total_duration:.1f} сек)...")
        
        out_video = None
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out_video = cv2.VideoWriter(output_path, fourcc, self.fps, (self.width, self.height))
        
        for i in range(total_frames):
            frame = self.step()
            frames.append(frame)
            
            if out_video:
                out_video.write(frame.img)  # Используем .img вместо .image
            
            if i % 60 == 0:
                print(f"  Кадр {i}/{total_frames}, Круг {self.current_lap}, Время: {self.current_time_in_lap:.2f}")
        
        if out_video:
            out_video.release()
            print(f"Видео сохранено: {output_path}")
            
        return frames


if __name__ == "__main__":
    # Демо-режим: быстрая проверка без сохранения видео (экономия памяти)
    gen = MockHudGenerator(MockFlightConfig(total_laps=2, lap_duration_sec=3.0, fps=30))
    print("Генерация тестовой последовательности (без видео)...")
    frames = gen.generate_flight_sequence(output_path=None)
    print(f"✓ Сгенерировано {len(frames)} кадров.")
    print(f"✓ Первый кадр: t={frames[0].t:.3f}, img shape={frames[0].img.shape}")
    if hasattr(frames[0], 'hud_ref'):
        print(f"✓ HUD эталон: speed={frames[0].hud_ref.speed}, alt={frames[0].hud_ref.alt}")
    if hasattr(frames[0], 'sticks_ref'):
        print(f"✓ Sticks эталон: ly={frames[0].sticks_ref.ly:.2f}, rx={frames[0].sticks_ref.rx:.2f}")
    print("\nMock generator готов к работе!")
