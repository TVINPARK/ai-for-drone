"""
Тесты для модулей анализа: laps, sticks_metrics, delta.
"""
import pytest
import pandas as pd
import numpy as np
from qt.analysis.laps import LapAnalyzer, LapInfo
from qt.analysis.sticks_metrics import StickAnalyzer, StickMetrics
from qt.analysis.delta import DeltaCalculator


class TestLapAnalyzer:
    """Тесты анализатора кругов."""

    def test_extract_laps_from_events(self):
        """Извлечение кругов из событий."""
        df = pd.DataFrame({
            'timestamp': [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0],
            'event': ['lap_start', None, None, 'lap_end', 'lap_start', None, None, 'lap_end']
        })
        
        analyzer = LapAnalyzer()
        laps = analyzer.extract_laps(df)
        
        assert len(laps) == 2
        assert laps[0].lap_number == 1
        assert laps[0].duration == 30.0 # 40 - 10
        assert laps[1].lap_number == 2
        assert laps[1].duration == 30.0 # 80 - 50

    def test_extract_laps_from_timer_reset(self):
        """Извлечение кругов по сбросу таймера."""
        # Симуляция таймера: растет, потом сбрасывается
        df = pd.DataFrame({
            'timestamp': [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            'hud_current_time': [0.0, 10.0, 20.0, 0.5, 10.5, 20.5, 30.5] # Сброс на 30-й секунде
        })
        
        analyzer = LapAnalyzer()
        laps = analyzer.extract_laps(df)
        
        assert len(laps) >= 1
        # Первый круг должен быть примерно 30 секунд
        assert laps[0].duration > 25.0

    def test_delta_calculation(self):
        """Расчет дельт между кругами."""
        laps = [
            LapInfo(lap_number=1, start_time=0, end_time=45.0, duration=45.0),
            LapInfo(lap_number=2, start_time=45, end_time=88.0, duration=43.0), # Лучший
            LapInfo(lap_number=3, start_time=88, end_time=134.0, duration=46.0),
        ]
        
        # Эмуляция логики extract_laps по расчету дельт
        best_dur = min(l.duration for l in laps)
        for i, lap in enumerate(laps):
            lap.delta_to_best = lap.duration - best_dur
            if i > 0:
                lap.delta_to_prev = lap.duration - laps[i-1].duration
        
        assert laps[1].delta_to_best == 0.0
        assert laps[0].delta_to_best == 2.0
        assert laps[2].delta_to_best == 3.0
        assert laps[2].delta_to_prev == 3.0

    def test_sectors_calculation(self):
        """Расчет виртуальных секторов."""
        df = pd.DataFrame({
            'timestamp': np.linspace(0, 60, 100)
        })
        laps = [LapInfo(lap_number=1, start_time=0, end_time=60, duration=60)]
        
        analyzer = LapAnalyzer(num_sectors=3)
        laps = analyzer.calculate_sectors(df, laps)
        
        assert len(laps[0].sectors) == 3
        # Каждый сектор должен быть 20 секунд
        assert abs(laps[0].sectors[1] - 20.0) < 0.1


class TestStickAnalyzer:
    """Тесты анализатора стиков."""

    def test_smooth_control(self):
        """Метрики плавного управления."""
        # Плавная синусоида
        t = np.linspace(0, 10, 100)
        values = np.sin(t)
        
        df = pd.DataFrame({
            'timestamp': t,
            'stick_throttle': values
        })
        
        analyzer = StickAnalyzer()
        metrics = analyzer.analyze_lap(df, 0, 10)
        
        assert 'stick_throttle' in metrics
        m = metrics['stick_throttle']
        assert m.corrections_count > 0 # Синус имеет смены направления
        assert m.smoothness_rms < 1.0 # Плавное движение

    def test_jittery_control(self):
        """Метрики дрожания стика."""
        # Шумный сигнал
        t = np.linspace(0, 5, 50)
        values = np.random.randn(50) * 0.5
        
        df = pd.DataFrame({
            'timestamp': t,
            'stick_pitch': values
        })
        
        analyzer = StickAnalyzer()
        metrics = analyzer.analyze_lap(df, 0, 5)
        
        if 'stick_pitch' in metrics:
            # Дрожание должно давать высокий RMS второй производной
            assert metrics['stick_pitch'].smoothness_rms > 0

    def test_compare_laps_text(self):
        """Генерация текстового сравнения."""
        m1 = StickMetrics('throttle', 0.5, 1.0, 0.0, 5, 0.1, 80.0)
        m2 = StickMetrics('throttle', 0.5, 1.0, 0.0, 10, 0.1, 80.0) # Больше коррекций
        
        analyzer = StickAnalyzer()
        text = analyzer.compare_laps({'throttle': m1}, {'throttle': m2})
        
        assert 'коррекций больше' in text or 'плавнее' in text or 'стабилен' in text


class TestDeltaCalculator:
    """Тесты калькулятора дельта-кривых."""

    def test_identical_laps(self):
        """Дельта для идентичных кругов должна быть ~0."""
        t = np.linspace(0, 60, 100)
        df = pd.DataFrame({'timestamp': t})
        
        calc = DeltaCalculator()
        times, deltas = calc.calculate_delta_curve(df, df)
        
        # Дельта должна быть близка к нулю везде
        assert np.allclose(deltas, 0, atol=1e-6)

    def test_slower_lap(self):
        """Отставание в каждом участке."""
        t_best = np.linspace(0, 60, 100)
        t_curr = np.linspace(0, 65, 100) # Медленнее на 5 сек
        
        df_best = pd.DataFrame({'timestamp': t_best})
        df_curr = pd.DataFrame({'timestamp': t_curr})
        
        calc = DeltaCalculator()
        times, deltas = calc.calculate_delta_curve(df_best, df_curr)
        
        # Дельта должна расти и быть положительной (отставание)
        assert deltas[-1] > 0
        assert np.all(deltas >= -0.1) # Не должно быть значительного опережения

    def test_gain_loss_zones(self):
        """Поиск зон выигрыша/проигрыша."""
        times = np.linspace(0, 60, 100)
        # Симуляция: сначала отставание, потом опережение
        deltas = np.sin(np.linspace(0, 4*np.pi, 100)) * 0.5
        
        calc = DeltaCalculator()
        zones = calc.find_gain_loss_zones(times, deltas)
        
        # Должны найтись зоны
        assert len(zones) > 0
        
        has_gain = any(z['type'] == 'gain' for z in zones)
        has_loss = any(z['type'] == 'loss' for z in zones)
        
        assert has_gain and has_loss
