"""
Тесты модуля логгирования телеметрии.
"""

import pytest
import sqlite3
import time
import tempfile
import numpy as np
from pathlib import Path

from qt.core.frame import Frame, Hud, Sticks
from qt.logger import DataLogger


class TestDataLogger:
    """Тесты для DataLogger."""
    
    @pytest.fixture
    def temp_db(self):
        """Создание временной БД для тестов."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        yield db_path
        # Очистка после теста
        if Path(db_path).exists():
            Path(db_path).unlink()
            
    @pytest.fixture
    def logger(self, temp_db):
        """Создание логгера для тестов."""
        log = DataLogger(db_path=temp_db, buffer_size=10, flush_interval=0.1)
        log.start()
        yield log
        log.stop()
        
    def test_logger_creation(self, temp_db):
        """Тест создания логгера."""
        log = DataLogger(db_path=temp_db)
        assert log.db_path == Path(temp_db)
        assert log.buffer_size == 100
        assert not log._running
        
    def test_session_creation(self, logger):
        """Тест создания сессии при первом кадре."""
        # Создаем тестовый кадр
        hud = Hud(
            speed=50.0,
            alt=10.0,
            cur_t=0.0,
            best_t=None,
            lap_cur=0,
            pilot="Test Pilot"
        )
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        # Отправляем кадр
        logger.put(frame)
        
        # Ждем записи
        time.sleep(0.3)
        
        # Проверяем создание сессии
        stats = logger.get_session_stats()
        assert stats is not None
        assert stats["pilot_name"] == "Test Pilot"
        assert stats["total_laps"] == 0
        
    def test_lap_detection(self, logger):
        """Тест детекции кругов."""
        base_time = time.time()
        
        # Круг 1: от 0 до 5000 мс
        for i in range(20):
            hud = Hud(
                speed=50.0 + i,
                alt=10.0,
                cur_t=i * 250,  # 0, 250, 500, ... 4750
                best_t=None,
                lap_cur=0,
                pilot="Test"
            )
            sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
            frame = Frame(t=base_time + i * 0.1, img=np.zeros((100, 100, 3), dtype=np.uint8))
            frame.hud = hud
            frame.sticks = sticks
            logger.put(frame)
            
        time.sleep(0.2)
        
        # Круг 2: сброс таймера
        for i in range(20):
            hud = Hud(
                speed=60.0 + i,
                alt=12.0,
                cur_t=i * 250,
                best_t=5000.0,  # Лучший круг предыдущий
                lap_cur=1,
                pilot="Test"
            )
            sticks = Sticks(lx=0.1, ly=0.6, rx=0.0, ry=0.0)
            frame = Frame(t=base_time + 2.0 + i * 0.1, img=np.zeros((100, 100, 3), dtype=np.uint8))
            frame.hud = hud
            frame.sticks = sticks
            logger.put(frame)
            
        # Ждем записи
        time.sleep(0.5)
        
        # Проверяем круги
        laps = logger.get_laps()
        assert len(laps) >= 1  # Хотя бы один круг записан
        
        # Первый записанный круг должен быть №1 или №2 (в зависимости от логики)
        first_lap = laps[0]
        assert first_lap["lap_number"] in [1, 2]
        assert first_lap["lap_duration"] is not None
            
    def test_frame_recording(self, logger):
        """Тест записи кадров."""
        base_time = time.time()
        
        # Отправляем несколько кадров
        for i in range(15):
            hud = Hud(
                speed=50.0 + i,
                alt=10.0 + i * 0.1,
                cur_t=i * 100,
                best_t=None,
                lap_cur=0,
                bat_v=14.8,
                bat_a=5.2
            )
            sticks = Sticks(
                lx=0.1 * (i % 3 - 1),
                ly=0.5 + i * 0.01,
                rx=0.0,
                ry=0.05 * (i % 2)
            )
            frame = Frame(t=base_time + i * 0.1, img=np.zeros((100, 100, 3), dtype=np.uint8))
            frame.hud = hud
            frame.sticks = sticks
            logger.put(frame)
            
        # Ждем записи
        time.sleep(0.3)
        
        # Получаем кадры первого круга
        frames = logger.get_frames_for_lap(lap_number=0)
        
        assert len(frames) > 0
        assert len(frames) <= 15  # Может быть меньше из-за буферизации
        
        # Проверяем данные первого кадра (может быть не первый из-за буферизации)
        first_frame = frames[0]
        assert 50.0 <= first_frame["speed"] <= 64.0  # В диапазоне отправленных значений
        assert 10.0 <= first_frame["altitude"] <= 11.4
        assert first_frame["battery_v"] == 14.8
        assert first_frame["battery_a"] == 5.2
        assert 0.5 <= first_frame["throttle"] <= 0.64
        
    def test_crash_marking(self, logger):
        """Тест отметки краша."""
        # Создаем сессию
        hud = Hud(speed=50.0, alt=10.0, cur_t=0.0)
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        logger.put(frame)
        
        time.sleep(0.2)
        
        # Отмечаем краш
        logger.mark_crash()
        
        time.sleep(0.2)
        
        # Проверяем
        stats = logger.get_session_stats()
        assert stats["crash_detected"] is True
        
    def test_best_lap_tracking(self, logger):
        """Тест отслеживания лучшего круга."""
        base_time = time.time()
        
        # Круг 1: 5000 мс
        for i in range(50):
            hud = Hud(
                speed=50.0,
                alt=10.0,
                cur_t=i * 100,
                best_t=None,
                lap_cur=0
            )
            sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
            frame = Frame(t=base_time + i * 0.1, img=np.zeros((100, 100, 3), dtype=np.uint8))
            frame.hud = hud
            frame.sticks = sticks
            logger.put(frame)
            
        time.sleep(0.3)
        
        # Круг 2: 4500 мс (лучше)
        for i in range(45):
            hud = Hud(
                speed=55.0,
                alt=10.0,
                cur_t=i * 100,
                best_t=5000.0,
                lap_cur=1
            )
            sticks = Sticks(lx=0.0, ly=0.55, rx=0.0, ry=0.0)
            frame = Frame(t=base_time + 5.0 + i * 0.1, img=np.zeros((100, 100, 3), dtype=np.uint8))
            frame.hud = hud
            frame.sticks = sticks
            logger.put(frame)
            
        # Ждем записи
        time.sleep(0.5)
        
        # Проверяем лучший круг
        stats = logger.get_session_stats()
        assert stats["best_lap_time"] is not None
        assert stats["best_lap_time"] <= 5000.0
        
    def test_multiple_sessions(self, temp_db):
        """Тест нескольких сессий в одной БД."""
        # Сессия 1
        log1 = DataLogger(db_path=temp_db, buffer_size=10, flush_interval=0.1)
        log1.start()
        
        hud1 = Hud(speed=50.0, alt=10.0, cur_t=0.0, pilot="Pilot 1")
        sticks1 = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
        frame1 = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame1.hud = hud1
        frame1.sticks = sticks1
        log1.put(frame1)
        
        time.sleep(0.3)
        log1.stop()
        
        # Сессия 2
        log2 = DataLogger(db_path=temp_db, buffer_size=10, flush_interval=0.1)
        log2.start()
        
        hud2 = Hud(speed=60.0, alt=15.0, cur_t=0.0, pilot="Pilot 2")
        sticks2 = Sticks(lx=0.0, ly=0.6, rx=0.0, ry=0.0)
        frame2 = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame2.hud = hud2
        frame2.sticks = sticks2
        log2.put(frame2)
        
        time.sleep(0.3)
        log2.stop()
        
        # Проверяем что сессии разные
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions")
        count = cursor.fetchone()[0]
        conn.close()
        
        assert count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
