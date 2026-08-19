"""
Тестовый скрипт для проверки работы всей системы телеметрии на видеофайле.
Загружает видео, эмулирует захват, распознаёт HUD и стики, пишет лог, детектирует события,
строит аналитику и генерирует HTML-отчёт.
"""

import cv2
import time
import argparse
from pathlib import Path
import sys

# Добавляем корень проекта в путь импортов
sys.path.insert(0, str(Path(__file__).parent))

from qt.core.config import load_config
from qt.core.frame import Frame, Hud, Sticks
from qt.ocr.fields import HudParser
from qt.sticks.detector import StickDetector
from qt.logger import DataLogger
from qt.events import EventDetector
from qt.analysis.laps import LapAnalyzer
from qt.analysis.delta import DeltaCalculator
from qt.analysis.sticks_metrics import StickAnalyzer
from qt.report.html import ReportGenerator

def main():
    parser = argparse.ArgumentParser(description="Тест телеметрии на видеофайле")
    parser.add_argument("--video", type=str, default="tests/fixtures/video_01.mp4", 
                        help="Путь к видеофайлу относительно корня проекта")
    parser.add_argument("--config", type=str, default="config.json", help="Путь к конфигурации")
    parser.add_argument("--output", type=str, default="test_video_report.html", help="Имя выходного HTML отчёта")
    args = parser.parse_args()

    # Определяем пути
    base_dir = Path(__file__).parent
    video_path = base_dir / args.video
    config_path = base_dir / args.config
    output_path = base_dir / args.output

    if not video_path.exists():
        print(f"❌ Видеофайл не найден: {video_path}")
        return
    
    if not config_path.exists():
        print(f"⚠️ Конфигурация не найдена: {config_path}, используем дефолтную")
        config = load_config(None)
    else:
        config = load_config(str(config_path))

    print(f"🎬 Загрузка видео: {video_path}")
    print(f"⚙️ Конфигурация: {config_path}")
    
    # Инициализация компонентов системы
    print("🔧 Инициализация модулей...")
    hud_parser = HudParser(config)
    stick_detector = StickDetector(config_path if config_path.exists() else str(config_path.parent / "config.json"))
    
    # Простой список для хранения данных (вместо сложного логгера с БД)
    frame_data = []
    
    def simple_logger(frame, hud_data, sticks):
        """Простая функция логгирования без БД."""
        frame_data.append({
            't': frame.t,
            'hud': hud_data,
            'sticks': sticks
        })
    
    class SimpleLogger:
        def put(self, frame):
            simple_logger(frame, frame.hud, frame.sticks)
        def _finish_lap(self, time_ms):
            pass
        def get_session_data(self):
            return frame_data
    
    logger = SimpleLogger()
    event_detector = EventDetector()
    event_detector._logger = logger  # Добавляем логгер как атрибут
    
    # Открываем видео через OpenCV
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print("❌ Не удалось открыть видеофайл")
        return

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    
    print(f"▶️ Параметры видео: {total_frames} кадров, {fps:.2f} FPS, длительность {duration:.2f} сек.")
    print("🚀 Начало обработки...")

    start_time = time.time()
    frame_count = 0
    ocr_success_count = 0
    sticks_success_count = 0
    
    # Основной цикл обработки кадров
    while True:
        ret, frame_img = cap.read()
        if not ret:
            break
        
        frame_count += 1
        
        # Прогресс каждые 10%
        if frame_count % max(1, total_frames // 10) == 0:
            progress = (frame_count / total_frames) * 100
            print(f"🔄 Обработано: {frame_count}/{total_frames} ({progress:.1f}%)")

        # Создаем объект кадра
        current_time = time.time()
        frame = Frame(t=current_time, img=frame_img)
        
        # 1. Распознавание HUD (OCR)
        hud_data = None
        try:
            hud_data = hud_parser.parse(frame_img)
            if hud_data and (hud_data.speed is not None or hud_data.cur_t is not None):
                ocr_success_count += 1
        except Exception as e:
            # Тихий игнор ошибок OCR для отдельных кадров
            pass

        # 2. Распознавание стиков
        sticks = None
        try:
            sticks = stick_detector.detect(frame_img)
            if sticks and (sticks.lx is not None or sticks.ly is not None):
                sticks_success_count += 1
        except Exception as e:
            # Тихий игнор ошибок детекции стиков
            pass

        # 3. Логгирование и обработка событий (только если есть данные)
        if hud_data or sticks:
            frame.hud = hud_data
            frame.sticks = sticks
            logger.put(frame)
            event_detector.process_frame(frame)

    cap.release()
    
    elapsed = time.time() - start_time
    real_fps = frame_count / elapsed if elapsed > 0 else 0
    
    print("\n" + "="*60)
    print("📊 СТАТИСТИКА ОБРАБОТКИ")
    print("="*60)
    print(f"✅ Всего кадров: {frame_count}")
    print(f"✅ Успешных OCR: {ocr_success_count} ({ocr_success_count/frame_count*100:.1f}%)")
    print(f"✅ Успешных детекций стиков: {sticks_success_count} ({sticks_success_count/frame_count*100:.1f}%)")
    print(f"⏱️ Время обработки: {elapsed:.2f} сек.")
    print(f"🚀 Скорость: {real_fps:.2f} FPS (в {real_fps/fps:.2f}x быстрее реального времени)" if fps > 0 else "")
    
    # Получение данных из логгера
    session_data = logger.get_session_data()
    
    if not session_data or len(session_data) == 0:
        print("⚠️ Нет данных для анализа. Возможно, видео не содержит распознанного HUD.")
        return

    print(f"💾 Записано записей в лог: {len(session_data)}")
    
    # 4. Пост-анализ
    print("\n📈 Выполнение пост-анализа...")
    
    try:
        # Анализ кругов
        lap_analyzer = LapAnalyzer(session_data)
        laps_results = lap_analyzer.analyze()
        
        if laps_results and 'laps' in laps_results and len(laps_results['laps']) > 0:
            print(f"🏁 Найдено кругов: {len(laps_results['laps'])}")
            for i, lap in enumerate(laps_results['laps']):
                print(f"   Круг {i+1}: {lap['time']:.3f} сек.")
                if 'sectors' in lap and lap['sectors']:
                    sectors_str = ", ".join([f"S{s}: {t:.2f}" for s, t in lap['sectors'].items()])
                    print(f"      Секторы: {sectors_str}")
        else:
            print("⚠️ Круги не обнаружены (возможно, тестовое видео слишком короткое)")
        
        # Дельта-калькулятор
        delta_calc = DeltaCalculator()
        delta_results = None
        if laps_results and 'laps' in laps_results and len(laps_results['laps']) >= 2:
            delta_results = delta_calc.calculate(laps_results['laps'])
            print("📊 Дельта-анализ выполнен")
        
        # Метрики стиков
        stick_analyzer = StickAnalyzer()
        stick_results = stick_analyzer.analyze(session_data)
        print("🎮 Метрики стиков рассчитаны")
        
        # Сбор сводных результатов (секторы уже внутри laps_results)
        analysis_results = {
            'laps': laps_results,
            'delta': delta_results,
            'sticks': stick_results
        }
        
        # 5. Генерация отчёта
        print("\n📄 Генерация HTML-отчёта...")
        report_gen = ReportGenerator(analysis_results)
        report_path = report_gen.generate(str(output_path))
        
        print(f"✅ Отчёт успешно сохранён: {report_path}")
        print(f"🌐 Откройте файл в браузере для просмотра результатов.")
        
        # Авто-открытие в браузере (опционально)
        try:
            import webbrowser
            webbrowser.open(f"file:///{report_path}")
            print("🌍 Отчёт открыт в браузере.")
        except Exception:
            pass
            
    except Exception as e:
        print(f"❌ Ошибка при анализе или генерации отчёта: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
