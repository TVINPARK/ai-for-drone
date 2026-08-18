"""
Модуль логгирования телеметрии.
Записывает данные в SQLite с буферизацией для производительности.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import deque
import logging

from ..core.frame import Frame, Hud, Sticks

logger = logging.getLogger(__name__)


class DataLogger:
    """
    Асинхронный логгер телеметрии с буферизацией.
    
    Архитектура:
    - Основной поток добавляет кадры в очередь через put()
    - Фоновый поток пишет батчами в SQLite каждые N мс или при заполнении буфера
    - Автоматическое создание сессий и кругов
    """
    
    def __init__(self, db_path: str = "telemetry.db", buffer_size: int = 100, flush_interval: float = 0.5):
        self.db_path = Path(db_path)
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        
        # Буфер для батчевой записи
        self._buffer: deque = deque(maxlen=buffer_size)
        self._buffer_lock = threading.Lock()
        
        # Состояние сессии
        self._session_id: Optional[int] = None
        self._current_lap: Optional[int] = None
        self._session_start: Optional[float] = None
        
        # Для детекции смены кругов
        self._last_lap_time: float = 0.0
        self._last_lap_number: int = 0
        
        # Поток и события
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._flush_event = threading.Event()
        self._db_ready_event = threading.Event()  # Сигнал о готовности БД
        
        # DB connection (в потоке)
        self._conn: Optional[sqlite3.Connection] = None
        self._cursor: Optional[sqlite3.Cursor] = None
        
    def start(self):
        """Запуск фонового потока записи."""
        if self._running:
            return
            
        self._running = True
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("DataLogger started")
        
    def stop(self):
        """Остановка и финальная запись буфера."""
        if not self._running:
            return
            
        self._running = False
        self._stop_event.set()
        self._flush_event.set()  # Принудительная запись
        
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
            
        # Финальная запись остатков
        self._flush_buffer()
        
        # Закрываем сессию
        if self._session_id is not None:
            self._close_session()
            
        logger.info("DataLogger stopped")
        
    def _init_db(self):
        """Инициализация БД и создание таблиц."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")  # Для лучшей производительности
        self._cursor = self._conn.cursor()
        
        # Читаем схему из файла
        schema_file = Path(__file__).parent / "schema.sql"
        if schema_file.exists():
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema = f.read()
            self._conn.executescript(schema)
            self._conn.commit()
        else:
            logger.warning(f"Schema file not found: {schema_file}")
            raise FileNotFoundError(f"Database schema not found at {schema_file}")
            
    def _worker_loop(self):
        """Фоновый цикл записи."""
        try:
            self._init_db()
            self._db_ready_event.set()  # Сигнал о готовности БД
        except Exception as e:
            logger.error(f"Failed to init DB: {e}")
            return
        
        last_flush = time.time()
        
        while self._running or not self._stop_event.is_set():
            # Ждем сигнала о данных или остановке
            if self._buffer:
                current_time = time.time()
                
                # Flush если прошло достаточно времени или буфер полон
                if (current_time - last_flush >= self.flush_interval) or len(self._buffer) >= self.buffer_size // 2:
                    self._flush_buffer()
                    last_flush = current_time
                    
            self._flush_event.wait(timeout=0.1)
            self._flush_event.clear()
            
        # Финальный flush
        if self._buffer:
            self._flush_buffer()
            
        # Закрываем соединение
        if self._conn:
            self._conn.close()
            self._conn = None
            self._cursor = None
            
    def _flush_buffer(self):
        """Запись буфера в БД."""
        with self._buffer_lock:
            if not self._buffer:
                return
                
            frames_data = list(self._buffer)
            self._buffer.clear()
            
        if not frames_data:
            return
            
        try:
            # Пакетная вставка
            insert_query = """
                INSERT INTO frames (
                    session_id, lap_number, timestamp,
                    hud_speed, hud_altitude, hud_current_lap_time, hud_best_lap_time,
                    hud_battery_v, hud_battery_a,
                    stick_throttle, stick_roll, stick_pitch, stick_yaw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            rows = []
            for frame in frames_data:
                row = (
                    self._session_id,
                    self._current_lap,
                    frame.t,  # Используем правильное имя поля
                    frame.hud.speed if frame.hud and frame.hud.speed is not None else None,
                    frame.hud.alt if frame.hud and frame.hud.alt is not None else None,
                    frame.hud.cur_t if frame.hud else None,
                    frame.hud.best_t if frame.hud else None,
                    frame.hud.bat_v if frame.hud else None,
                    frame.hud.bat_a if frame.hud else None,
                    frame.sticks.ly if frame.sticks else None,  # ly = throttle
                    frame.sticks.lx if frame.sticks else None,  # lx = roll
                    frame.sticks.ry if frame.sticks else None,  # ry = pitch
                    frame.sticks.rx if frame.sticks else None,  # rx = yaw/roll
                )
                rows.append(row)
                
            self._cursor.executemany(insert_query, rows)
            self._conn.commit()
            
        except Exception as e:
            logger.error(f"Error flushing buffer to DB: {e}")
            
    def put(self, frame: Frame):
        """
        Добавить кадр в буфер для записи.
        Вызывается из основного потока захвата.
        """
        # Ждем готовности БД (не более 5 секунд)
        if not self._db_ready_event.wait(timeout=5.0):
            logger.error("Database not ready after 5 seconds, skipping frame")
            return
            
        # Проверяем необходимость создания новой сессии
        if self._session_id is None:
            self._start_session(frame)
            
        # Детектируем смену круга
        if frame.hud:
            self._check_lap_change(frame.hud)
            
        # Добавляем в буфер
        with self._buffer_lock:
            self._buffer.append(frame)
            
        # Сигнал потоку о новых данных
        self._flush_event.set()
        
    def _start_session(self, first_frame: Frame):
        """Создание новой сессии."""
        self._session_start = time.time()
        
        pilot_name = None
        if first_frame.hud and first_frame.hud.pilot:
            pilot_name = first_frame.hud.pilot
            
        insert_query = """
            INSERT INTO sessions (start_time, pilot_name)
            VALUES (?, ?)
        """
        
        self._cursor.execute(insert_query, (self._session_start, pilot_name))
        self._conn.commit()
        
        self._session_id = self._cursor.lastrowid
        self._current_lap = 0
        self._last_lap_time = 0.0
        self._last_lap_number = 0
        
        logger.info(f"Session started: ID={self._session_id}, Pilot={pilot_name}")
        
    def _check_lap_change(self, hud: Hud):
        """
        Детекция старта нового круга по изменению счетчика кругов или сбросу таймера.
        """
        if hud.lap_cur is not None and hud.lap_cur > self._last_lap_number:
            # Завершение предыдущего круга
            if self._current_lap is not None and self._current_lap > 0:
                self._finish_lap(hud.cur_t)
                
            # Старт нового круга
            self._current_lap = hud.lap_cur + 1
            self._last_lap_number = hud.lap_cur
            self._start_lap()
            
        elif hud.cur_t is not None:
            # Проверка на сброс таймера (новый круг без изменения счетчика)
            if hud.cur_t < self._last_lap_time - 1000:  # Сброс более чем на 1 секунду
                if self._current_lap is not None and self._current_lap > 0:
                    self._finish_lap(self._last_lap_time)
                    
                self._current_lap = (self._current_lap or 0) + 1
                self._start_lap()
                
            self._last_lap_time = hud.cur_t
            
    def _start_lap(self):
        """Регистрация старта круга."""
        logger.info(f"Lap {self._current_lap} started")
        
    def _finish_lap(self, lap_time_ms: Optional[float]):
        """Регистрация завершения круга."""
        if self._session_id is None or self._current_lap is None:
            return
            
        current_time = time.time()
        
        # Определяем лучший круг
        is_best = False
        if lap_time_ms is not None:
            # Проверяем против текущего лучшего
            query = "SELECT best_lap_time FROM sessions WHERE id = ?"
            self._cursor.execute(query, (self._session_id,))
            row = self._cursor.fetchone()
            
            if row and row[0] is not None:
                if lap_time_ms < row[0]:
                    is_best = True
                    # Обновляем лучший круг сессии
                    update_query = "UPDATE sessions SET best_lap_time = ? WHERE id = ?"
                    self._cursor.execute(update_query, (lap_time_ms, self._session_id))
            else:
                # Первый круг автоматически лучший
                is_best = True
                update_query = "UPDATE sessions SET best_lap_time = ? WHERE id = ?"
                self._cursor.execute(update_query, (lap_time_ms, self._session_id))
                
        # Вставляем запись о круге
        insert_query = """
            INSERT INTO laps (session_id, lap_number, start_time, end_time, lap_duration, is_best)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        
        # Вычисляем время старта круга (приблизительно)
        lap_start = current_time - (lap_time_ms / 1000.0 if lap_time_ms else 0)
        
        self._cursor.execute(
            insert_query,
            (self._session_id, self._current_lap, lap_start, current_time, lap_time_ms, is_best)
        )
        
        # Обновляем счетчик кругов в сессии
        update_query = "UPDATE sessions SET total_laps = total_laps + 1 WHERE id = ?"
        self._cursor.execute(update_query, (self._session_id,))
        
        self._conn.commit()
        
        logger.info(f"Lap {self._current_lap} finished: {lap_time_ms:.1f}ms, Best: {is_best}")
        
    def _close_session(self):
        """Закрытие текущей сессии."""
        if self._session_id is None or self._cursor is None:
            return
            
        current_time = time.time()
        
        update_query = """
            UPDATE sessions SET end_time = ? WHERE id = ?
        """
        
        self._cursor.execute(update_query, (current_time, self._session_id))
        self._conn.commit()
        
        logger.info(f"Session {self._session_id} closed")
        
    def mark_crash(self):
        """Отметить краш в текущей сессии."""
        if self._session_id is None:
            return
            
        update_query = "UPDATE sessions SET crash_detected = 1 WHERE id = ?"
        self._cursor.execute(update_query, (self._session_id,))
        self._conn.commit()
        
        logger.warning(f"Crash marked in session {self._session_id}")
        
    def get_session_stats(self, session_id: Optional[int] = None) -> Dict[str, Any]:
        """Получить статистику сессии."""
        if session_id is None:
            session_id = self._session_id
            
        if session_id is None:
            return {}
            
        query = """
            SELECT 
                s.id,
                s.start_time,
                s.end_time,
                s.pilot_name,
                s.total_laps,
                s.best_lap_time,
                s.crash_detected,
                COUNT(l.id) as recorded_laps
            FROM sessions s
            LEFT JOIN laps l ON s.id = l.session_id
            WHERE s.id = ?
            GROUP BY s.id
        """
        
        self._cursor.execute(query, (session_id,))
        row = self._cursor.fetchone()
        
        if not row:
            return {}
            
        return {
            "id": row[0],
            "start_time": row[1],
            "end_time": row[2],
            "pilot_name": row[3],
            "total_laps": row[4],
            "best_lap_time": row[5],
            "crash_detected": bool(row[6]),
            "recorded_laps": row[7]
        }
        
    def get_laps(self, session_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Получить все круги сессии."""
        if session_id is None:
            session_id = self._session_id
            
        if session_id is None:
            return []
            
        query = """
            SELECT 
                lap_number,
                start_time,
                end_time,
                lap_duration,
                is_best
            FROM laps
            WHERE session_id = ?
            ORDER BY lap_number
        """
        
        self._cursor.execute(query, (session_id,))
        
        return [
            {
                "lap_number": row[0],
                "start_time": row[1],
                "end_time": row[2],
                "lap_duration": row[3],
                "is_best": bool(row[4])
            }
            for row in self._cursor.fetchall()
        ]
        
    def get_frames_for_lap(self, lap_number: int, session_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Получить все кадры для конкретного круга."""
        if session_id is None:
            session_id = self._session_id
            
        if session_id is None:
            return []
            
        query = """
            SELECT 
                timestamp,
                hud_speed,
                hud_altitude,
                hud_current_lap_time,
                hud_best_lap_time,
                hud_battery_v,
                hud_battery_a,
                stick_throttle,
                stick_roll,
                stick_pitch,
                stick_yaw
            FROM frames
            WHERE session_id = ? AND lap_number = ?
            ORDER BY timestamp
        """
        
        self._cursor.execute(query, (session_id, lap_number))
        
        return [
            {
                "timestamp": row[0],
                "speed": row[1],
                "altitude": row[2],
                "current_lap_time": row[3],
                "best_lap_time": row[4],
                "battery_v": row[5],
                "battery_a": row[6],
                "throttle": row[7],
                "roll": row[8],
                "pitch": row[9],
                "yaw": row[10]
            }
            for row in self._cursor.fetchall()
        ]
