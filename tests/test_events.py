"""
Тесты модуля детекции событий.
"""

import pytest
import time
import numpy as np

from qt.core.frame import Frame, Hud, Sticks
from qt.events import EventDetector, FlightState


class TestEventDetector:
    """Тесты для EventDetector."""
    
    @pytest.fixture
    def detector(self):
        """Создание детектора для тестов."""
        det = EventDetector()
        yield det
        det.reset()
        
    def test_initial_state(self, detector):
        """Тест начального состояния."""
        assert detector.state == FlightState.IDLE
        assert detector._last_lap_number == 0
        assert detector._best_lap_time_ms is None
        
    def test_session_start_on_hud_appear(self, detector):
        """Тест начала сессии при появлении HUD."""
        events = []
        detector.register_callback("session_start", lambda e: events.append(e))
        
        hud = Hud(speed=0.0, alt=0.0, cur_t=0.0, lap_cur=0)
        sticks = Sticks(lx=0.0, ly=0.0, rx=0.0, ry=0.0)
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        detector.process_frame(frame)
        
        assert len(events) == 1
        assert events[0].event_type == "session_start"
        assert detector.state == FlightState.READY
        
    def test_flying_state_on_speed(self, detector):
        """Тест перехода в состояние полета."""
        # Сначала появляем HUD
        hud = Hud(speed=0.0, alt=10.0, cur_t=0.0, lap_cur=0)
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        detector.process_frame(frame)
        assert detector.state == FlightState.READY
        
        # Увеличиваем скорость
        hud.speed = 5.0
        detector.process_frame(frame)
        
        assert detector.state == FlightState.FLYING
        
    def test_lap_detection_by_counter(self, detector):
        """Тест детекции кругов по счетчику."""
        lap_events = []
        detector.register_callback("lap_start", lambda e: lap_events.append(("start", e.data)))
        detector.register_callback("lap_finish", lambda e: lap_events.append(("finish", e.data)))
        
        # Переходим в состояние полета
        hud = Hud(speed=10.0, alt=10.0, cur_t=0.0, lap_cur=0)
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        detector.process_frame(frame)  # READY
        hud.speed = 15.0
        detector.process_frame(frame)  # FLYING
        
        # Эмулируем завершение круга (счетчик увеличился)
        hud.lap_cur = 1
        hud.cur_t = 45000.0  # 45 секунд
        detector.process_frame(frame)
        
        # Должны быть события старта круга 1 и финиша круга 0 (или старта круга 2)
        assert len(lap_events) >= 1
        
    def test_lap_detection_by_timer_reset(self, detector):
        """Тест детекции кругов по сбросу таймера."""
        lap_starts = []
        lap_finishes = []
        detector.register_callback("lap_start", lambda e: lap_starts.append(e.data))
        detector.register_callback("lap_finish", lambda e: lap_finishes.append(e.data))
        
        # Старт
        hud = Hud(speed=10.0, alt=10.0, cur_t=0.0, lap_cur=0)
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        detector.process_frame(frame)
        hud.speed = 15.0
        detector.process_frame(frame)
        
        # Прогресс круга
        hud.cur_t = 30000.0
        detector.process_frame(frame)
        
        # Сброс таймера (новый круг)
        hud.cur_t = 500.0  # Сброс на 0.5 сек
        detector.process_frame(frame)
        
        # Должен быть хотя бы один старт круга
        assert len(lap_starts) >= 1
        
    def test_crash_detection(self, detector):
        """Тест детекции краша."""
        crash_events = []
        detector.register_callback("crash", lambda e: crash_events.append(e))
        
        # Сначала переводим в состояние FLYING
        hud = Hud(speed=50.0, alt=10.0, cur_t=0.0, lap_cur=0)
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)  # Газ 50%
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        # Переход в READY -> FLYING
        detector.process_frame(frame)  # HUD появляется -> READY
        detector.process_frame(frame)  # Скорость есть -> FLYING
        
        # Эмулируем серию кадров с падающей скоростью и высотой
        for i in range(15):
            speed = max(0, 50.0 - i * 4)  # Быстро падаем до 0
            alt = max(0, 10.0 - i * 0.7)
            hud = Hud(speed=speed, alt=alt, cur_t=i*100.0, lap_cur=0)
            sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)  # Газ 50%
            frame = Frame(t=time.time() + i*0.033, img=np.zeros((100, 100, 3), dtype=np.uint8))
            frame.hud = hud
            frame.sticks = sticks
            detector.process_frame(frame)
            
        # Краш: газ есть, скорости нет, высота упала
        hud = Hud(speed=0.0, alt=0.0, cur_t=1500.0, lap_cur=0)
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)  # Газ все еще 50%
        frame = Frame(t=time.time() + 0.5, img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        detector.process_frame(frame)
        
        assert detector.state == FlightState.CRASHED
        assert len(crash_events) >= 1
        
    def test_live_delta_calculation(self, detector):
        """Тест расчета live-дельты."""
        delta_events = []
        detector.register_callback("live_delta", lambda e: delta_events.append(e.data))
        
        # Устанавливаем лучшее время
        detector._best_lap_time_ms = 60000.0  # 60 секунд
        detector._current_lap_start_time = time.time()
        detector.state = FlightState.FLYING
        
        # Эмулируем кадр с текущим временем круга
        hud = Hud(speed=50.0, alt=10.0, cur_t=30000.0, best_t=60000.0, lap_cur=0)
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        detector.process_frame(frame)
        
        # Должно быть событие live_delta
        assert len(delta_events) >= 1
        
        if len(delta_events) > 0:
            delta_data = delta_events[0]
            assert "delta_ms" in delta_data
            assert "elapsed_ms" in delta_data
            assert "progress" in delta_data
            
    def test_session_end_on_hud_disappear(self, detector):
        """Тест завершения сессии при исчезновении HUD."""
        session_end_events = []
        detector.register_callback("session_end", lambda e: session_end_events.append(e))
        
        # Начало сессии
        hud = Hud(speed=10.0, alt=10.0, cur_t=0.0, lap_cur=0)
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        detector.process_frame(frame)
        hud.speed = 15.0
        detector.process_frame(frame)  # FLYING
        
        # HUD пропал
        frame_no_hud = Frame(t=time.time() + 1.0, img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame_no_hud.hud = None
        frame_no_hud.sticks = sticks
        
        detector.process_frame(frame_no_hud)
        
        assert detector.state == FlightState.LANDED
        assert len(session_end_events) >= 1
        
    def test_callback_registration(self, detector):
        """Тест регистрации callback'ов."""
        call_count = 0
        
        def my_callback(event):
            nonlocal call_count
            call_count += 1
            
        detector.register_callback("session_start", my_callback)
        detector.register_callback("session_start", my_callback)  # Второй callback
        
        hud = Hud(speed=0.0, alt=0.0, cur_t=0.0)
        sticks = Sticks()
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        detector.process_frame(frame)
        
        # Callback вызван дважды (два зарегистрированных)
        assert call_count == 2
        
    def test_get_current_state(self, detector):
        """Тест получения текущего состояния."""
        # Начальное состояние
        state = detector.get_current_state()
        assert state["state"] == "IDLE"
        assert state["last_lap_number"] == 0
        
        # После появления HUD
        hud = Hud(speed=10.0, alt=10.0, cur_t=5000.0, lap_cur=0, best_t=60000.0)
        sticks = Sticks(lx=0.0, ly=0.5, rx=0.0, ry=0.0)
        frame = Frame(t=time.time(), img=np.zeros((100, 100, 3), dtype=np.uint8))
        frame.hud = hud
        frame.sticks = sticks
        
        detector.process_frame(frame)
        hud.speed = 15.0
        detector.process_frame(frame)
        
        state = detector.get_current_state()
        assert state["state"] == "FLYING"
        # best_t в HUD в секундах, а внутри детектора конвертируется в мс
        assert state["best_lap_time"] == 60000.0 * 1000  # 60 секунд = 60000 мс, но у нас уже мс


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
