#!/usr/bin/env python3
"""
Главный скрипт запуска системы «ТВ-телеметрия Квадросима».

Интегрирует все модули:
1. Захват экрана (dxcam/mss)
2. OCR и парсинг HUD
3. Детекция стиков
4. Логгирование в SQLite
5. Детекция событий (круги, краши)
6. Пост-анализ и генерация отчёта
"""
import sys
import time
import signal
import argparse
from pathlib import Path
from typing import Optional

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent))

from qt.core.config import load_config
from qt.capture.source import MssSource, DxCamSource
from qt.ocr.engine import EasyOCREngine
from qt.ocr.digits import TemplateEngine
from qt.sticks.detector import StickDetector
from qt.logger import DataLogger
from qt.events import EventDetector
from qt.analysis.laps import LapAnalyzer
from qt.analysis.sticks_metrics import StickAnalyzer
from qt.analysis.delta import DeltaCalculator
from qt.report.html import ReportGenerator


class ScreenCapture:
    """Обёртка над источниками захвата."""
    def __init__(self, config):
        self.config = config
        # Выбираем источник в зависимости от платформы
        try:
            self.source = DxCamSource(config)
        except Exception:
            self.source = MssSource(config)
    
    def get_frame(self):
        return self.source.get_frame()


class OcrEngine:
    """Обёртка над OCR движками."""
    def __init__(self, config):
        self.config = config
        self.easyocr = EasyOCREngine(config)
        self.template_engine = TemplateEngine(config)
    
    def process_frame(self, frame):
        # Упрощённая логика - нужно адаптировать под реальный API
        from qt.core.frame import Hud
        return Hud()


class TelemetrySystem:
    """Основной класс системы телеметрии."""

    def __init__(self, config_path: str = "config.json"):
        self.config = load_config(config_path)
        self.running = False
        
        # Инициализация компонентов
        print("🚀 Инициализация модулей...")
        
        self.capture = ScreenCapture(self.config)
        self.ocr = OcrEngine(self.config)
        self.stick_detector = StickDetector(self.config)
        self.logger = DataLogger(self.config)
        self.event_detector = EventDetector()
        
        # Анализаторы (для пост-обработки)
        self.lap_analyzer = LapAnalyzer(num_sectors=3)
        self.stick_analyzer = StickAnalyzer()
        self.delta_calculator = DeltaCalculator()
        self.report_generator = ReportGenerator(output_dir="reports")
        
        # Обработчик прерывания
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        print("✅ Система готова к работе")

    def _signal_handler(self, signum, frame):
        """Обработка Ctrl+C."""
        print("\n🛑 Получен сигнал остановки...")
        self.running = False

    def run(self, duration: Optional[float] = None):
        """
        Запуск основного цикла захвата и обработки.
        
        Args:
            duration: Длительность записи в секундах (None = бесконечно)
        """
        print("🎬 Запуск захвата телеметрии...")
        print("💡 Нажмите Ctrl+C для завершения вылета и генерации отчёта")
        
        self.running = True
        start_time = time.time()
        frame_count = 0
        
        try:
            self.logger.start_session()
            
            while self.running:
                # Проверка длительности
                if duration and (time.time() - start_time) > duration:
                    print(f"⏱ Достигнут лимит времени {duration} сек")
                    break
                
                # 1. Захват кадра
                frame = self.capture.get_frame()
                if frame is None:
                    time.sleep(0.01)
                    continue
                
                # 2. Распознавание HUD
                hud = self.cr.process_frame(frame)
                
                # 3. Детекция стиков
                sticks = self.stick_detector.detect(frame)
                
                # 4. Логгирование
                self.logger.log_frame(frame.t, hud, sticks)
                
                # 5. Детекция событий
                events = self.event_detector.process(hud, sticks, frame.t)
                for event in events:
                    self.logger.log_event(event)
                    print(f"📌 Событие: {event.type}")
                
                frame_count += 1
                
                # Ограничение FPS для снижения нагрузки
                elapsed = time.time() - start_time
                target_fps = 30
                if frame_count / max(elapsed, 0.001) > target_fps:
                    time.sleep(0.01)
                    
        except Exception as e:
            print(f"❌ Ошибка в цикле: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            self.logger.end_session()
            
        # Пост-обработка и отчёт
        self._generate_report()

    def _generate_report(self):
        """Генерация отчёта после вылета."""
        print("📊 Генерация отчёта...")
        
        # Получаем данные из логов
        df = self.logger.get_session_data()
        
        if df.empty:
            print("⚠ Нет данных для анализа")
            return
        
        # 1. Нарезка на круги
        laps = self.lap_analyzer.extract_laps(df)
        laps = self.lap_analyzer.calculate_sectors(df, laps)
        
        if not laps:
            print("⚠ Круги не обнаружены")
            return
        
        # 2. Метрики стиков для каждого круга
        all_stick_metrics = {}
        for lap in laps:
            metrics = self.stick_analyzer.analyze_lap(df, lap.start_time, lap.end_time)
            all_stick_metrics[lap.lap_number] = metrics
        
        # 3. Дельта-кривые (сравнение с лучшим кругом)
        best_lap = min(laps, key=lambda x: x.duration)
        delta_curves = {}
        
        for lap in laps:
            if lap.lap_number == best_lap.lap_number:
                continue
                
            mask_best = (df['timestamp'] >= best_lap.start_time) & (df['timestamp'] <= best_lap.end_time)
            mask_curr = (df['timestamp'] >= lap.start_time) & (df['timestamp'] <= lap.end_time)
            
            df_best = df.loc[mask_best].copy()
            df_curr = df.loc[mask_curr].copy()
            
            if len(df_best) > 10 and len(df_curr) > 10:
                times, deltas = self.delta_calculator.calculate_delta_curve(df_best, df_curr)
                delta_curves[str(lap.lap_number)] = (times, deltas)
        
        # 4. Текстовый саммари
        summary = self.report_generator.generate_summary_text(laps, all_stick_metrics)
        
        # 5. Генерация HTML
        html_path = self.report_generator.generate(
            laps=laps,
            df_raw=df,
            stick_metrics=all_stick_metrics,
            delta_curves=delta_curves,
            summary_text=summary
        )
        
        print(f"✅ Отчёт сохранён: {html_path}")
        print("\n" + "="*50)
        print(summary)
        print("="*50)


def main():
    parser = argparse.ArgumentParser(
        description="ТВ-телеметрия Квадросима — система анализа полётов дрона"
    )
    parser.add_argument(
        "-c", "--config",
        default="config.json",
        help="Путь к файлу конфигурации (по умолчанию: config.json)"
    )
    parser.add_argument(
        "-t", "--time",
        type=float,
        default=None,
        help="Максимальная длительность записи в секундах"
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Запустить режим калибровки ROI"
    )
    
    args = parser.parse_args()
    
    if args.calibrate:
        from qt.capture.calibrate import run_calibrator
        run_calibrator()
        return
    
    # Проверка конфига
    if not Path(args.config).exists():
        print(f"❌ Файл конфигурации не найден: {args.config}")
        print("💡 Запустите сначала калибровку: python main.py --calibrate")
        sys.exit(1)
    
    # Запуск системы
    system = TelemetrySystem(config_path=args.config)
    system.run(duration=args.time)


if __name__ == "__main__":
    main()
