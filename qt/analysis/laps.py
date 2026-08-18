"""
Модуль пост-анализа: нарезка на круги, расчет дельт и секторов.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# FrameData не нужен здесь, используем только DataFrame


@dataclass
class LapInfo:
    lap_number: int
    start_time: float
    end_time: float
    duration: float
    delta_to_best: float = 0.0
    delta_to_prev: float = 0.0
    sectors: Dict[int, float] = field(default_factory=dict)
    best_sector_times: Dict[int, float] = field(default_factory=dict)


class LapAnalyzer:
    """Анализирует сырой лог кадров и выделяет круги."""

    def __init__(self, num_sectors: int = 3):
        self.num_sectors = num_sectors

    def extract_laps(self, df: pd.DataFrame) -> List[LapInfo]:
        """
        Нарезает DataFrame на круги на основе событий 'lap_start' и 'lap_end'.
        Если событий нет, пытается детектировать сброс таймера.
        """
        if df.empty:
            return []

        laps = []
        
        # Попытка найти события через маркеры
        if 'event' in df.columns:
            starts = df[df['event'] == 'lap_start']
            ends = df[df['event'] == 'lap_end']
            
            # Парсинг по событиям
            for i, (_, start_row) in enumerate(starts.iterrows()):
                # Ищем соответствующий конец
                matching_ends = ends[ends['timestamp'] > start_row['timestamp']]
                if matching_ends.empty:
                    continue # Круг не завершен
                
                end_row = matching_ends.iloc[0]
                
                lap_dur = end_row['timestamp'] - start_row['timestamp']
                laps.append(LapInfo(
                    lap_number=i + 1,
                    start_time=start_row['timestamp'],
                    end_time=end_row['timestamp'],
                    duration=lap_dur
                ))
        else:
            # Fallback: Детекция по таймеру HUD (если он сбрасывается)
            # Предполагаем, что у нас есть колонка 'hud_current_time' (в секундах)
            if 'hud_current_time' in df.columns:
                laps = self._detect_laps_by_timer(df)

        # Расчет дельт
        if len(laps) > 0:
            best_lap = min(laps, key=lambda x: x.duration)
            best_duration = best_lap.duration
            
            for i, lap in enumerate(laps):
                lap.delta_to_best = lap.duration - best_duration
                if i > 0:
                    lap.delta_to_prev = lap.duration - laps[i-1].duration
                else:
                    lap.delta_to_prev = 0.0

        return laps

    def _detect_laps_by_timer(self, df: pd.DataFrame) -> List[LapInfo]:
        """Детекция кругов по сбросу таймера текущего круга."""
        laps = []
        timer_col = df['hud_current_time'].reset_index(drop=True)
        ts_col = df['timestamp'].reset_index(drop=True)
        
        # Ищем точки, где таймер резко уменьшился (сброс)
        diffs = timer_col.diff()
        # Сброс: разница меньше -1.0 (таймер ушел назад)
        reset_mask = diffs < -1.0
        reset_indices = reset_mask[reset_mask].index.tolist()
        
        # Добавляем начало и конец данных как границы
        boundaries = [0] + reset_indices + [len(df) - 1]
        
        for i in range(len(boundaries) - 1):
            start_idx = boundaries[i]
            end_idx = boundaries[i+1]
            
            if start_idx >= len(df) or end_idx >= len(df):
                continue
                
            start_ts = ts_col.iloc[start_idx]
            end_ts = ts_col.iloc[end_idx]
            duration = end_ts - start_ts
            
            # Проверка: круг должен быть разумной длины (например > 10 сек)
            if duration < 10.0:
                continue

            laps.append(LapInfo(
                lap_number=len(laps) + 1,
                start_time=start_ts,
                end_time=end_ts,
                duration=duration
            ))
            
        return laps

    def calculate_sectors(self, df: pd.DataFrame, laps: List[LapInfo]) -> List[LapInfo]:
        """
        Разбивает каждый круг на N виртуальных секторов.
        Метод: равномерная временная разбивка внутри круга.
        """
        for lap in laps:
            # Получаем данные конкретного круга
            mask = (df['timestamp'] >= lap.start_time) & (df['timestamp'] <= lap.end_time)
            lap_data = df.loc[mask]
            
            if len(lap_data) < self.num_sectors:
                continue

            total_time = lap.duration
            sector_duration = total_time / self.num_sectors
            
            lap.sectors = {}
            lap.best_sector_times = {} # Пока заглушка, для сравнения нужно несколько кругов
            
            for s in range(1, self.num_sectors + 1):
                # Время прохождения сектора (упрощенно: длительность сектора)
                # В реальной задаче нужно искать время пересечения границы
                lap.sectors[s] = sector_duration
                
        return laps

    def get_summary_table(self, laps: List[LapInfo]) -> pd.DataFrame:
        """Возвращает таблицу кругов для отчета."""
        if not laps:
            return pd.DataFrame()
            
        data = []
        for lap in laps:
            row = {
                'Круг': lap.lap_number,
                'Время': f"{lap.duration:.3f}",
                'Дельта к лучшему': f"+{lap.delta_to_best:.3f}" if lap.delta_to_best > 0 else f"{lap.delta_to_best:.3f}",
                'Дельта к пред.': f"+{lap.delta_to_prev:.3f}" if lap.delta_to_prev > 0 else f"{lap.delta_to_prev:.3f}",
            }
            # Добавляем сектора
            for s, t in lap.sectors.items():
                row[f'Сектор {s}'] = f"{t:.3f}"
            data.append(row)
            
        return pd.DataFrame(data)
