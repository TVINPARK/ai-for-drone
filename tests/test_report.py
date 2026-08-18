"""
Тесты для генератора отчётов.
"""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import tempfile
import shutil

from qt.analysis.laps import LapInfo, LapAnalyzer
from qt.analysis.sticks_metrics import StickMetrics, StickAnalyzer
from qt.report.html import ReportGenerator


class TestReportGenerator:
    """Тесты генератора HTML-отчётов."""

    @pytest.fixture
    def temp_dir(self):
        """Создаёт временную директорию для отчётов."""
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d)

    @pytest.fixture
    def sample_laps(self):
        """Пример данных кругов."""
        return [
            LapInfo(lap_number=1, start_time=0, end_time=45.5, duration=45.5, 
                    delta_to_best=2.5, delta_to_prev=0, sectors={1: 15.0, 2: 15.0, 3: 15.5}),
            LapInfo(lap_number=2, start_time=45.5, end_time=88.0, duration=42.5,
                    delta_to_best=0, delta_to_prev=-3.0, sectors={1: 14.0, 2: 14.0, 3: 14.5}),
            LapInfo(lap_number=3, start_time=88, end_time=132.0, duration=44.0,
                    delta_to_best=1.5, delta_to_prev=1.5, sectors={1: 14.5, 2: 14.5, 3: 15.0}),
        ]

    @pytest.fixture
    def sample_dataframe(self):
        """Пример сырых данных телеметрии."""
        n = 200
        return pd.DataFrame({
            'timestamp': np.linspace(0, 132, n),
            'hud_speed': np.sin(np.linspace(0, 4*np.pi, n)) * 50 + 80,
            'hud_alt': np.cos(np.linspace(0, 2*np.pi, n)) * 10 + 20,
            'stick_l_gas': np.random.rand(n) * 0.5 + 0.3,
            'stick_l_yaw': np.sin(np.linspace(0, 8*np.pi, n)) * 0.3,
            'stick_r_pitch': np.cos(np.linspace(0, 6*np.pi, n)) * 0.4,
            'stick_r_roll': np.sin(np.linspace(0, 10*np.pi, n)) * 0.2,
        })

    def test_report_generation(self, temp_dir, sample_laps, sample_dataframe):
        """Генерация полного отчёта."""
        gen = ReportGenerator(output_dir=temp_dir)
        
        # Генерируем summary
        summary = gen.generate_summary_text(sample_laps)
        
        # Создаём отчёт
        html_path = gen.generate(
            laps=sample_laps,
            df_raw=sample_dataframe,
            summary_text=summary
        )
        
        # Проверяем существование файла
        assert Path(html_path).exists()
        assert html_path.endswith('.html')
        
        # Проверяем размер файла (должен быть > 0)
        assert Path(html_path).stat().st_size > 1000

    def test_summary_text_generation(self, sample_laps):
        """Генерация текстового саммари."""
        gen = ReportGenerator()
        summary = gen.generate_summary_text(sample_laps)
        
        assert "Лучший круг" in summary
        assert "#2" in summary  # Второй круг лучший
        assert "Прогресс" in summary or "улучшение" in summary.lower()

    def test_empty_laps_summary(self):
        """Саммари для пустых данных."""
        gen = ReportGenerator()
        summary = gen.generate_summary_text([])
        
        assert "Нет данных" in summary

    def test_delta_curves_visualization(self, temp_dir, sample_laps, sample_dataframe):
        """Визуализация дельта-кривых."""
        from qt.analysis.delta import DeltaCalculator
        
        calc = DeltaCalculator()
        
        # Берём данные первого и второго круга
        lap1_mask = (sample_dataframe['timestamp'] >= 0) & (sample_dataframe['timestamp'] <= 45.5)
        lap2_mask = (sample_dataframe['timestamp'] >= 45.5) & (sample_dataframe['timestamp'] <= 88.0)
        
        df_lap1 = sample_dataframe[lap1_mask]
        df_lap2 = sample_dataframe[lap2_mask]
        
        if len(df_lap1) > 10 and len(df_lap2) > 10:
            times, deltas = calc.calculate_delta_curve(df_lap2, df_lap1)
            
            delta_curves = {'1': (times, deltas)}
            
            gen = ReportGenerator(output_dir=temp_dir)
            html_path = gen.generate(
                laps=sample_laps,
                df_raw=sample_dataframe,
                delta_curves=delta_curves
            )
            
            assert Path(html_path).exists()

    def test_stick_metrics_in_report(self, temp_dir, sample_laps, sample_dataframe):
        """Включение метрик стиков в отчёт."""
        analyzer = StickAnalyzer()
        
        # Считаем метрики для первого круга
        metrics_lap1 = analyzer.analyze_lap(sample_dataframe, 0, 45.5)
        
        stick_metrics = {1: metrics_lap1}
        
        gen = ReportGenerator(output_dir=temp_dir)
        summary = gen.generate_summary_text(sample_laps, stick_metrics)
        
        html_path = gen.generate(
            laps=sample_laps,
            df_raw=sample_dataframe,
            stick_metrics=stick_metrics,
            summary_text=summary
        )
        
        assert Path(html_path).exists()
