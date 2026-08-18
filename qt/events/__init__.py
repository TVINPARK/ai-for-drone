"""
Модуль детекции событий полета.
Реализует машину состояний для отслеживания статуса полета.
"""

from __future__ import annotations

import time
import logging
from enum import Enum, auto
from typing import Optional, Callable, List
from dataclasses import dataclass, field

from ..core.frame import Frame, Hud, Sticks

logger = logging.getLogger(__name__)


class FlightState(Enum):
    """Состояния полета."""
    IDLE = auto()           # Ожидание начала
    READY = auto()          # Готов к взлету (HUD появился)
    FLYING = auto()         # Полет
    CRASHED = auto()        # Краш
    LANDED = auto()         # Посадка/завершение


@dataclass
class Event:
    """Событие детектированное системой."""
    timestamp: float                    # Время события
    event_type: str                     # Тип события
    data: dict = field(default_factory=dict)  # Дополнительные данные
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "type": self.event_type,
            **self.data
        }


class EventDetector:
    """
    Детектор событий полета на основе анализа HUD.
    
    Детектируемые события:
    - session_start: Начало сессии (появление HUD)
    - lap_start: Старт круга
    - lap_finish: Финиш круга
    - crash: Обнаружение краша
    - session_end: Завершение сессии (исчезновение HUD или смена режима)
    - live_delta: Обновление live-дельты
    """
    
    def __init__(self):
        self.state = FlightState.IDLE
        
        # Последнее известное состояние HUD
        self._last_hud: Optional[Hud] = None
        self._last_lap_number: int = 0
        self._last_lap_time: float = 0.0
        self._last_speed: float = 0.0
        self._last_altitude: float = 0.0
        self._last_throttle: float = 0.0
        
        # Для детекции краша
        self._speed_history: List[float] = []
        self._altitude_history: List[float] = []
        self._history_size = 10  # ~0.3 секунды при 30 FPS
        
        # Callbacks для событий
        self._callbacks: dict[str, List[Callable]] = {
            "session_start": [],
            "session_end": [],
            "lap_start": [],
            "lap_finish": [],
            "crash": [],
            "live_delta": []
        }
        
        # Лучшее время для live-дельты
        self._best_lap_time_ms: Optional[float] = None
        self._current_lap_start_time: Optional[float] = None
        
    def reset(self):
        """Сброс состояния детектора."""
        self.state = FlightState.IDLE
        self._last_hud = None
        self._last_lap_number = 0
        self._last_lap_time = 0.0
        self._last_speed = 0.0
        self._last_altitude = 0.0
        self._last_throttle = 0.0
        self._speed_history.clear()
        self._altitude_history.clear()
        self._best_lap_time_ms = None
        self._current_lap_start_time = None
        
    def register_callback(self, event_type: str, callback: Callable):
        """Регистрация callback для события."""
        if event_type in self._callbacks:
            self._callbacks[event_type].append(callback)
            
    def _emit_event(self, event: Event):
        """Отправка события всем подписчикам."""
        logger.debug(f"Event: {event.event_type} - {event.data}")
        
        callbacks = self._callbacks.get(event.event_type, [])
        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in callback for {event.event_type}: {e}")
                
    def process_frame(self, frame: Frame):
        """
        Обработка кадра и детекция событий.
        Вызывается для каждого нового кадра.
        """
        hud = frame.hud
        sticks = frame.sticks
        
        current_time = frame.t  # Используем поле 't' из Frame
        
        # Детекция появления HUD (начало сессии)
        if self.state == FlightState.IDLE and hud is not None:
            self.state = FlightState.READY
            self._emit_event(Event(
                timestamp=current_time,
                event_type="session_start",
                data={"pilot": hud.pilot if hud else None}
            ))
            
        # Детекция исчезновения HUD (конец сессии)
        if self.state in [FlightState.FLYING, FlightState.READY] and hud is None:
            if self._last_hud is not None:  # HUD был, но пропал
                self.state = FlightState.LANDED
                self._emit_event(Event(
                    timestamp=current_time,
                    event_type="session_end",
                    data={"reason": "hud_disappeared"}
                ))
                return
                
        # Проверка смены режима полёта (не ACRO)
        if self.state == FlightState.FLYING and hud and hud.mode:
            if hud.mode != "ACRO":
                self.state = FlightState.LANDED
                self._emit_event(Event(
                    timestamp=current_time,
                    event_type="session_end",
                    data={"reason": "mode_change", "mode": hud.mode}
                ))
                return
                
        if hud is None:
            self._last_hud = None
            return
            
        # Обновляем историю для детекции краша
        if hud.speed is not None:
            self._speed_history.append(hud.speed)
            if len(self._speed_history) > self._history_size:
                self._speed_history.pop(0)
                
        if hud.alt is not None:
            self._altitude_history.append(hud.alt)
            if len(self._altitude_history) > self._history_size:
                self._altitude_history.pop(0)
                
        # Детекция краша
        if self._detect_crash(sticks):
            if self.state != FlightState.CRASHED:
                self.state = FlightState.CRASHED
                self._emit_event(Event(
                    timestamp=current_time,
                    event_type="crash",
                    data={
                        "speed": hud.speed,
                        "altitude": hud.alt,
                        "throttle": sticks.ly if sticks else 0
                    }
                ))
                
        # Возврат в полет после краша (если снова летим)
        if self.state == FlightState.CRASHED and hud.speed and hud.speed > 5:
            self.state = FlightState.FLYING
            
        # Переход в состояние полета
        if self.state == FlightState.READY and hud.speed and hud.speed > 1:
            self.state = FlightState.FLYING
            
        # Детекция кругов
        if self.state == FlightState.FLYING:
            self._detect_lap_events(hud, current_time)
            
        # Live-дельта
        if self.state == FlightState.FLYING:
            self._calculate_live_delta(hud, current_time)
            
        # Сохраняем состояние
        self._last_hud = hud
        if hud.speed is not None:
            self._last_speed = hud.speed
        if hud.alt is not None:
            self._last_altitude = hud.alt
        if sticks and sticks.ly is not None:
            self._last_throttle = sticks.ly
            
    def _detect_crash(self, sticks) -> bool:
        """
        Детекция краша по эвристике:
        - Газ > 10%
        - Скорость резко упала до ~0
        - Высота быстро снижается
        """
        if sticks is None or sticks.ly is None:
            return False
            
        # Газ должен быть значительным
        if sticks.ly < 0.1:
            return False
            
        # Проверяем скорость (должна быть близка к 0)
        if len(self._speed_history) < 5:
            return False
            
        avg_speed = sum(self._speed_history[-5:]) / 5
        if avg_speed > 5:  # Скорость еще есть, не краш
            return False
            
        # Проверяем падение высоты
        if len(self._altitude_history) >= 5:
            recent_avg = sum(self._altitude_history[-3:]) / 3
            older_avg = sum(self._altitude_history[-5:-2]) / 3
            
            if older_avg - recent_avg > 2:  # Быстрое снижение
                return True
                
        # Альтернатива: скорость была и резко пропала
        if len(self._speed_history) >= 5:
            old_speed = sum(self._speed_history[:3]) / 3
            new_speed = sum(self._speed_history[-3:]) / 3
            
            if old_speed > 20 and new_speed < 2:
                return True
                
        return False
        
    def _detect_lap_events(self, hud: Hud, current_time: float):
        """Детекция старта и финиша круга."""
        
        # По счетчику кругов
        if hud.lap_cur is not None:
            if hud.lap_cur > self._last_lap_number:
                # Финиш предыдущего круга
                if self._last_lap_number > 0:
                    self._emit_event(Event(
                        timestamp=current_time,
                        event_type="lap_finish",
                        data={
                            "lap_number": self._last_lap_number,
                            "lap_time_ms": self._last_lap_time
                        }
                    ))
                    
                # Старт нового круга
                new_lap = hud.lap_cur
                self._emit_event(Event(
                    timestamp=current_time,
                    event_type="lap_start",
                    data={"lap_number": new_lap}
                ))
                
                self._last_lap_number = hud.lap_cur
                self._current_lap_start_time = current_time
                
        # По таймеру круга
        if hud.cur_t is not None:
            # Сброс таймера (новый круг)
            if hud.cur_t < self._last_lap_time - 1.0:
                # Финиш предыдущего круга
                if self._last_lap_time > 1.0:  # Круг длился больше 1 секунды
                    self._emit_event(Event(
                        timestamp=current_time,
                        event_type="lap_finish",
                        data={
                            "lap_number": self._last_lap_number or 1,
                            "lap_time_ms": self._last_lap_time * 1000
                        }
                    ))
                    
                # Старт нового круга
                new_lap = (self._last_lap_number or 0) + 1
                self._emit_event(Event(
                    timestamp=current_time,
                    event_type="lap_start",
                    data={"lap_number": new_lap}
                ))
                
                self._last_lap_number = new_lap
                self._current_lap_start_time = current_time
                
            # Обновляем лучшее время из HUD
            if hud.best_t is not None:
                if self._best_lap_time_ms is None or hud.best_t * 1000 < self._best_lap_time_ms:
                    self._best_lap_time_ms = hud.best_t * 1000
                    
            self._last_lap_time = hud.cur_t
            
    def _calculate_live_delta(self, hud: Hud, current_time: float):
        """
        Расчет live-дельты текущего круга к лучшему.
        """
        if hud.cur_t is None:
            return
            
        if self._best_lap_time_ms is None or self._best_lap_time_ms <= 0:
            return
            
        if self._current_lap_start_time is None:
            self._current_lap_start_time = current_time
            
        # Время, прошедшее с начала текущего круга
        elapsed_ms = (current_time - self._current_lap_start_time) * 1000
        
        # Прогнозируемое время лучшего круга на этот момент
        progress = elapsed_ms / self._best_lap_time_ms if self._best_lap_time_ms > 0 else 0
        projected_best = elapsed_ms  # На тот же момент времени
        
        # Дельта: насколько мы отстаем или опережаем
        # Если текущее время круга больше прогресса лучшего - отстаем
        delta_ms = elapsed_ms - (progress * self._best_lap_time_ms)
        
        self._emit_event(Event(
            timestamp=current_time,
            event_type="live_delta",
            data={
                "delta_ms": delta_ms,
                "elapsed_ms": elapsed_ms,
                "best_lap_ms": self._best_lap_time_ms,
                "progress": min(1.0, progress)
            }
        ))
        
    def get_current_state(self) -> dict:
        """Получить текущее состояние детектора."""
        return {
            "state": self.state.name,
            "last_lap_number": self._last_lap_number,
            "last_lap_time": self._last_lap_time,
            "best_lap_time": self._best_lap_time_ms,
            "speed_history_avg": sum(self._speed_history[-5:]) / len(self._speed_history) if self._speed_history else 0,
            "altitude_history_avg": sum(self._altitude_history[-5:]) / len(self._altitude_history) if self._altitude_history else 0
        }
