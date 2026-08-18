"""
Модуль расчета дельта-кривых (F1-style telemetry).
Сравнивает текущий круг с лучшим, выравнивая их по времени.
"""
import pandas as pd
import numpy as np
from typing import Tuple, List


class DeltaCalculator:
    """Расчет накопительной дельты времени между двумя кругами."""

    def calculate_delta_curve(
        self, 
        df_best: pd.DataFrame, 
        df_current: pd.DataFrame, 
        num_points: int = 100
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Вычисляет кривую дельты: разница во времени в каждой точке круга.
        
        Args:
            df_best: Данные лучшего круга (колонки: timestamp, distance или progress)
            df_current: Данные текущего круга
            num_points: Количество точек для ресемплинга
            
        Returns:
            times: Массив времени (0..T)
            deltas: Массив дельт (положительное = отставание, отрицательное = опережение)
        """
        # Нормализация времени обоих кругов к [0, 1]
        def normalize_time(df):
            t0 = df['timestamp'].min()
            t1 = df['timestamp'].max()
            duration = t1 - t0
            if duration == 0:
                return np.zeros(len(df))
            return (df['timestamp'] - t0) / duration

        best_norm = normalize_time(df_best)
        current_norm = normalize_time(df_current)
        
        # Ресемплинг к единой сетке
        grid = np.linspace(0, 1, num_points)
        
        # Интерполяция прогресса (или скорости) для построения дельты
        # Упрощенный подход: сравниваем накопленное время достижения одной и той же % дистанции
        
        # Если есть колонка 'distance' или 'speed', можно интегрировать скорость
        # Здесь используем упрощение: считаем, что время равномерного прохождения сегмента
        # Дельта = T_current(p) - T_best(p), где p - процент круга
        
        best_times = np.interp(grid, best_norm, df_best['timestamp'].values)
        current_times = np.interp(grid, current_norm, df_current['timestamp'].values)
        
        # Длительности
        best_dur = df_best['timestamp'].max() - df_best['timestamp'].min()
        current_dur = df_current['timestamp'].max() - df_current['timestamp'].min()
        
        # Восстанавливаем абсолютное время от начала круга
        best_abs = best_times - best_times[0]
        current_abs = current_times - current_times[0]
        
        # Дельта: насколько текущий круг отстаёт (+) или опережает (-) лучший
        # Delta = T_current - T_best
        deltas = current_abs - best_abs
        
        # Временная ось (в секундах от начала круга)
        time_axis = np.linspace(0, max(best_dur, current_dur), num_points)[:len(deltas)]
        
        return time_axis, deltas

    def find_gain_loss_zones(self, times: np.ndarray, deltas: np.ndarray) -> List[dict]:
        """
        Находит зоны, где пилот выигрывает или проигрывает время.
        Возвращает список зон: {start, end, type: 'gain'|'loss', value}
        """
        zones = []
        if len(deltas) < 2:
            return zones
            
        current_zone = None
        
        for i in range(1, len(deltas)):
            d_prev = deltas[i-1]
            d_curr = deltas[i]
            t_curr = times[i]
            
            # Определение знака: delta > 0 (проигрыш), delta < 0 (выигрыш)
            is_loss = d_curr > 0.05 # Порог значимости 50мс
            is_gain = d_curr < -0.05
            
            if is_loss:
                zone_type = 'loss'
                val = d_curr
            elif is_gain:
                zone_type = 'gain'
                val = d_curr
            else:
                zone_type = 'neutral'
                
            if zone_type != 'neutral':
                if current_zone is None:
                    current_zone = {
                        'start': times[i-1],
                        'end': t_curr,
                        'type': zone_type,
                        'max_val': val,
                        'min_val': val
                    }
                elif current_zone['type'] == zone_type:
                    current_zone['end'] = t_curr
                    current_zone['max_val'] = max(current_zone['max_val'], val)
                    current_zone['min_val'] = min(current_zone['min_val'], val)
                else:
                    # Смена типа зоны
                    zones.append(current_zone)
                    current_zone = {
                        'start': times[i-1],
                        'end': t_curr,
                        'type': zone_type,
                        'max_val': val,
                        'min_val': val
                    }
            else:
                if current_zone is not None:
                    zones.append(current_zone)
                    current_zone = None
                    
        if current_zone is not None:
            zones.append(current_zone)
            
        return zones
