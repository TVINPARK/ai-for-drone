"""
Модуль анализа стиков: метрики, плавность, коррекции.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class StickMetrics:
    """Метрики одного стика за круг."""
    axis_name: str
    avg_value: float
    max_value: float
    min_value: float
    corrections_count: int  # Смены знака производной
    smoothness_rms: float   # RMS второй производной (дрожание)
    activity_percent: float # Процент времени, когда стик отклонен > 5%


class StickAnalyzer:
    """Анализирует поведение стиков."""

    def analyze_lap(self, df: pd.DataFrame, lap_start: float, lap_end: float) -> Dict[str, StickMetrics]:
        """
        Вычисляет метрики для всех осей стиков за период круга.
        Оси: throttle, yaw, pitch, roll
        """
        mask = (df['timestamp'] >= lap_start) & (df['timestamp'] <= lap_end)
        lap_data = df.loc[mask].copy()
        
        if lap_data.empty:
            return {}

        axes = ['stick_throttle', 'stick_yaw', 'stick_pitch', 'stick_roll']
        # Переименование для удобства, если в базе другие имена
        # В реальной БД могут быть stick_l_x, stick_l_y и т.д.
        # Здесь предполагаем нормализованные названия
        
        # Проверка наличия колонок (fallback на стандартные имена из детектора)
        available_axes = [ax for ax in axes if ax in lap_data.columns]
        
        # Если нет наших имен, пробуем стандартные из detector.py
        if not available_axes:
            standard_axes = ['stick_l_gas', 'stick_l_yaw', 'stick_r_pitch', 'stick_r_roll']
            available_axes = [ax for ax in standard_axes if ax in lap_data.columns]
            axes = available_axes # Обновляем список

        results = {}
        for axis in available_axes:
            series = lap_data[axis].dropna()
            if len(series) < 2:
                continue
                
            metrics = self._calculate_axis_metrics(series, axis)
            results[axis] = metrics
            
        return results

    def _calculate_axis_metrics(self, series: pd.Series, name: str) -> StickMetrics:
        """Расчет метрик для одной оси."""
        values = series.values
        
        # Базовые статистики
        avg_val = float(np.mean(values))
        max_val = float(np.max(values))
        min_val = float(np.min(values))
        
        # Производная (скорость изменения)
        derivative = np.diff(values)
        
        # Коррекции: смены знака производной
        # Знак производной: + (растет), - (падает), 0 (стоит)
        signs = np.sign(derivative)
        # Игнорируем нули (мертвая зона)
        signs[signs == 0] = 0 
        # Считаем переходы + -> - или - -> +
        changes = np.diff(signs)
        corrections = int(np.sum(np.abs(changes) > 1)) # Резкая смена направления
        
        # Плавность (RMS второй производной - ускорение/дрожание)
        if len(derivative) > 1:
            second_deriv = np.diff(derivative)
            rms_smoothness = float(np.sqrt(np.mean(second_deriv**2)))
        else:
            rms_smoothness = 0.0
            
        # Активность: процент времени, когда отклонение > 0.05 (5%)
        active_points = np.sum(np.abs(values) > 0.05)
        activity_pct = float((active_points / len(values)) * 100)
        
        return StickMetrics(
            axis_name=name,
            avg_value=avg_val,
            max_value=max_val,
            min_value=min_val,
            corrections_count=corrections,
            smoothness_rms=rms_smoothness,
            activity_percent=activity_pct
        )

    def compare_laps(self, metrics_1: Dict[str, StickMetrics], metrics_2: Dict[str, StickMetrics]) -> str:
        """Генерирует текстовое сравнение двух кругов по стикам."""
        text = []
        common_axes = set(metrics_1.keys()) & set(metrics_2.keys())
        
        for axis in common_axes:
            m1 = metrics_1[axis]
            m2 = metrics_2[axis]
            
            diff_corr = m2.corrections_count - m1.corrections_count
            diff_smooth = m2.smoothness_rms - m1.smoothness_rms
            
            if diff_corr > 2:
                text.append(f"{axis}: Во втором круге на {diff_corr} коррекций больше (менее плавно).")
            elif diff_corr < -2:
                text.append(f"{axis}: Во втором круге управление стало плавнее ({abs(diff_corr)} меньше коррекций).")
                
            if diff_smooth > 0.1:
                text.append(f"{axis}: Увеличилось дрожание стика во втором круге.")
                
        if not text:
            return "Стиль управления стиками стабилен между кругами."
            
        return " ".join(text)
