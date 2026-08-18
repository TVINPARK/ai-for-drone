#!/usr/bin/env python3
"""
Демонстрационный скрипт: генерирует синтетические данные полёта,
прогоняет их через все модули системы и создаёт HTML-отчёт.
"""
import os
import sys
import time
import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent))

from qt.core.frame import Frame, Hud, Sticks
from qt.logger import DataLogger
from qt.events import EventDetector
from qt.analysis import LapAnalyzer, StickAnalyzer, DeltaCalculator
from qt.report.html import ReportGenerator

def generate_synthetic_flight(duration_sec=30, num_laps=3):
    """Генерирует синтетические данные полёта на заданное время."""
    print(f"🎲 Генерация синтетического полёта: {duration_sec}с, {num_laps} кругов...")
    
    frames = []
    start_time = time.perf_counter()
    
    # Параметры полёта
    lap_duration = duration_sec / num_laps
    best_lap_time = lap_duration * 0.95  # Лучший круг чуть быстрее среднего
    
    for i in range(int(duration_sec * 30)):  # 30 FPS
        t = i / 30.0
        frame_t = start_time + t
        
        # Эмуляция HUD
        hud = Hud()
        hud.hud_present = True
        hud.pilot = "Иванов И.И."
        hud.mode = "ACRO"
        hud.bat_v = 16.8 - (t / duration_sec) * 0.5  # Разряд батареи
        hud.bat_a = 15.0 + np.sin(t * 2) * 5.0
        hud.speed = 60 + np.sin(t * 3) * 20 + np.random.normal(0, 2)
        hud.alt = 5 + np.sin(t * 1.5) * 3 + np.random.normal(0, 0.5)
        
        # Таймер текущего круга (сбрасывается каждый круг)
        time_in_lap = t % lap_duration
        hud.cur_t = time_in_lap
        
        # Счётчик кругов
        current_lap = int(t / lap_duration) + 1
        hud.lap_cur = min(current_lap, num_laps)
        hud.lap_tot = num_laps
        
        # Лучшее время (появляется после первого круга)
        if current_lap > 1:
            hud.best_t = best_lap_time
        
        # Лимит времени
        hud.limit_s = duration_sec
        
        # Эмуляция стиков (плавные движения с шумом)
        sticks = Sticks()
        sticks.ly = 0.5 + 0.3 * np.sin(t * 2) + np.random.normal(0, 0.05)  # Газ
        sticks.lx = 0.2 * np.sin(t * 1.5) + np.random.normal(0, 0.05)      # Руль
        sticks.ry = 0.1 * np.sin(t * 3) + np.random.normal(0, 0.05)        # Тангаж
        sticks.rx = 0.15 * np.sin(t * 2.5) + np.random.normal(0, 0.05)     # Крен
        sticks.conf_l = 0.95
        sticks.conf_r = 0.95
        
        # Ограничение значений [-1, 1]
        for attr in ['lx', 'ly', 'rx', 'ry']:
            val = getattr(sticks, attr)
            setattr(sticks, attr, max(-1.0, min(1.0, val)))
        
        # Создаём фейковый кадр (чёрный квадрат)
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        frame = Frame(t=frame_t, img=img)
        
        frames.append({
            'frame': frame,
            'hud': hud,
            'sticks': sticks
        })
    
    print(f"✅ Сгенерировано {len(frames)} кадров")
    return frames

def main():
    print("=" * 60)
    print("🚁 ДЕМО-ЗАПУСК СИСТЕМЫ «ТВ-телеметрия Квадросима»")
    print("=" * 60)
    
    # 1. Генерация данных
    frames_data = generate_synthetic_flight(duration_sec=25, num_laps=3)
    
    # 2. Инициализация логгера
    db_path = Path("demo_flight.db")
    if db_path.exists():
        db_path.unlink()
    
    logger = DataLogger(db_path=str(db_path))
    logger.start()  # Запускаем worker-поток
    print(f"📝 Логгер инициализирован: {db_path}")
    
    # 3. Инициализация детектора событий
    detector = EventDetector()
    events = []
    
    def on_event(event):
        events.append(event)
        print(f"   📍 СОБЫТИЕ: {event.event_type} @ {event.timestamp:.2f}s")
    
    # Регистрируем callback для всех типов событий
    for event_type in ['session_start', 'session_end', 'lap_start', 'lap_end', 'crash']:
        detector.register_callback(event_type, on_event)
    
    print("📡 Детектор событий активирован")
    
    # 4. Обработка кадров (эмуляция основного цикла)
    print("\n⏱️  Обработка кадров...")
    best_lap_time = None
    
    for i, data in enumerate(frames_data):
        frame = data['frame']
        hud = data['hud']
        sticks = data['sticks']
        
        # Запись в лог (создаём полный фрейм)
        full_frame = Frame(t=frame.t, img=frame.img)
        full_frame.hud = hud
        full_frame.sticks = sticks
        logger.put(full_frame)
        
        # Детекция событий (передаём полный фрейм с данными)
        detector.process_frame(full_frame)
        
        # Live-дельта вычисляется внутри детектора и логгера автоматически
        
        # Обновление лучшего времени для детектора
        if hud.best_t is not None:
            detector.set_best_lap_time(hud.best_t)
    
    # Завершение сессии (передаём пустой фрейм)
    end_frame = Frame(t=time.perf_counter(), img=np.zeros((10, 10, 3), dtype=np.uint8))
    end_frame.hud = Hud(hud_present=False)
    end_frame.sticks = Sticks()
    detector.process_frame(end_frame)
    
    # Останавливаем логгер и ждём завершения записи
    logger.stop()
    logger.close()
    
    print(f"\n✅ Обработано {len(frames_data)} кадров")
    print(f"📊 Зарегистрировано событий: {len(events)}")
    
    # 5. Анализ данных
    print("\n🔍 Анализ данных...")
    
    # Чтение данных из БД для анализа
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Извлекаем кадры
    cursor.execute("SELECT t, speed, alt, cur_t, best_t, lap_cur, stick_lx, stick_ly, stick_rx, stick_ry FROM frames ORDER BY t")
    rows = cursor.fetchall()
    
    # Формируем структуры для анализа
    telemetry = []
    for row in rows:
        hud = Hud(
            cur_t=row['cur_t'],
            best_t=row['best_t'],
            lap_cur=row['lap_cur'],
            speed=row['speed'],
            alt=row['alt']
        )
        sticks = Sticks(
            lx=row['stick_lx'] or 0,
            ly=row['stick_ly'] or 0,
            rx=row['stick_rx'] or 0,
            ry=row['stick_ry'] or 0
        )
        telemetry.append({
            't': row['t'],
            'hud': hud,
            'sticks': sticks
        })
    
    conn.close()
    
    # Анализ кругов
    lap_analyzer = LapAnalyzer()
    laps = lap_analyzer.extract_laps_from_events(events, telemetry)
    print(f"   🏁 Найдено кругов: {len(laps)}")
    
    if len(laps) > 0:
        for i, lap in enumerate(laps):
            print(f"      Круг {i+1}: {lap['duration']:.3f}s")
    
    # Анализ секторов (встроено в LapAnalyzer)
    if len(laps) > 0:
        lap_analyzer_with_sectors = LapAnalyzer(num_sectors=3)
        laps_with_sectors = lap_analyzer_with_sectors.calculate_sectors(
            pd.DataFrame(telemetry), laps
        )
        sectors = [lap.sectors for lap in laps_with_sectors]
        print(f"   📍 Секторов на круг: {len(sectors[0]) if sectors else 0}")
    else:
        sectors = []
    
    # Дельта-расчёты
    if len(laps) > 1:
        delta_calc = DeltaCalculator()
        delta_curves = delta_calc.calculate_delta_curve(laps[0], laps[-1], telemetry)
        print(f"   📈 Точек в дельта-кривой: {len(delta_curves)}")
    
    # Анализ стиков
    stick_analyzer = StickAnalyzer()
    if len(laps) > 0:
        lap_idx = 0
        metrics = stick_analyzer.analyze_lap_sticks(laps[lap_idx], telemetry)
        print(f"   🎮 Метрики стиков:")
        print(f"      Коррекций газа: {metrics.get('throttle_corrections', 0)}")
        print(f"      Плавность (RMS): {metrics.get('smoothness_rms', 0):.4f}")
    
    # 6. Генерация отчёта
    print("\n📄 Генерация HTML-отчёта...")
    
    report_gen = ReportGenerator(output_dir=".")
    
    # Подготовка данных для отчёта
    report_data = {
        'laps': laps,
        'sectors': sectors if len(laps) > 0 else [],
        'delta_curves': delta_curves if len(laps) > 1 else [],
        'stick_metrics': metrics if len(laps) > 0 else {},
        'telemetry': telemetry,
        'events': events
    }
    
    report_path = report_gen.generate_html_report(report_data, session_id="demo_flight")
    print(f"✅ Отчёт сохранён: {report_path}")
    
    # 7. Вывод сводки
    print("\n" + "=" * 60)
    print("📊 СВОДКА ПОЛЁТА")
    print("=" * 60)
    
    if len(laps) > 0:
        best_lap = min(laps, key=lambda x: x['duration'])
        worst_lap = max(laps, key=lambda x: x['duration'])
        avg_lap = sum(l['duration'] for l in laps) / len(laps)
        
        print(f"Количество кругов: {len(laps)}")
        print(f"Лучший круг: {best_lap['duration']:.3f}s")
        print(f"Худший круг: {worst_lap['duration']:.3f}s")
        print(f"Среднее время: {avg_lap:.3f}s")
        print(f"Разброс: {worst_lap['duration'] - best_lap['duration']:.3f}s")
        
        if len(laps) > 1:
            delta_to_best = worst_lap['duration'] - best_lap['duration']
            print(f"Дельта худшего к лучшему: +{delta_to_best:.3f}s")
    
    print("\n✅ ДЕМО-ЗАПУСК ЗАВЕРШЁН УСПЕШНО!")
    print(f"📁 Файл базы данных: {db_path.absolute()}")
    print(f"📁 Файл отчёта: {Path(report_path).absolute()}")
    print("=" * 60)

if __name__ == "__main__":
    main()
