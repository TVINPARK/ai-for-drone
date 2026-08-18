"""
Генератор HTML-отчётов с интерактивными графиками Plotly.
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

# Импортируем из модуля analysis
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from analysis.laps import LapInfo
from analysis.sticks_metrics import StickMetrics


class ReportGenerator:
    """Генерирует HTML-отчёт после вылета."""

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def generate(
        self,
        laps: List[LapInfo],
        df_raw: pd.DataFrame,
        stick_metrics: Dict[int, Dict[str, StickMetrics]] = None,
        delta_curves: Dict[str, tuple] = None,
        summary_text: str = ""
    ) -> str:
        """
        Создаёт полный HTML-отчёт.
        
        Args:
            laps: Список кругов с метаданными
            df_raw: Сырые данные телеметрии
            stick_metrics: Метрики стиков по кругам {lap_num: {axis: metrics}}
            delta_curves: Дельта-кривые {lap_num: (times, deltas)}
            summary_text: Текстовый вывод аналитики
            
        Returns:
            Путь к сохранённому HTML файлу
        """
        # Создаём фигуру с подграфами
        fig = make_subplots(
            rows=5, cols=1,
            subplot_titles=(
                "Времена кругов и дельты",
                "Дельта-кривая (F1 style)",
                "Скорость и высота",
                "Стики (газ/руль)",
                "Стики (тангаж/крен)"
            ),
            vertical_spacing=0.08,
            row_heights=[0.15, 0.2, 0.2, 0.2, 0.2]
        )

        # 1. Таблица кругов (визуализация через bar chart)
        if laps:
            lap_nums = [l.lap_number for l in laps]
            durations = [l.duration for l in laps]
            deltas = [l.delta_to_best for l in laps]
            
            # Бары времён кругов
            fig.add_trace(
                go.Bar(x=lap_nums, y=durations, name='Время круга', marker_color='steelblue'),
                row=1, col=1
            )
            
            # Линия дельты
            fig.add_trace(
                go.Scatter(x=lap_nums, y=deltas, name='Дельта к лучшему', 
                          mode='lines+markers', line=dict(color='red', dash='dash')),
                row=1, col=1
            )

        # 2. Дельта-кривая
        if delta_curves:
            colors = ['blue', 'green', 'orange', 'purple']
            for i, (lap_name, (times, deltas)) in enumerate(delta_curves.items()):
                fig.add_trace(
                    go.Scatter(x=times, y=deltas, name=f'Круг {lap_name}',
                              mode='lines', line=dict(color=colors[i % len(colors)])),
                    row=2, col=1
                )
            
            # Горизонтальная линия нуля
            fig.add_hline(y=0, line_dash="dot", line_color="gray", row=2, col=1)

        # 3. Скорость и высота
        if 'hud_speed' in df_raw.columns:
            fig.add_trace(
                go.Scatter(x=df_raw['timestamp'], y=df_raw['hud_speed'], 
                          name='Скорость (км/ч)', line=dict(color='green')),
                row=3, col=1
            )
        if 'hud_alt' in df_raw.columns:
            fig.add_trace(
                go.Scatter(x=df_raw['timestamp'], y=df_raw['hud_alt'], 
                          name='Высота (м)', line=dict(color='cyan')),
                row=3, col=1
            )

        # 4. Стики: газ и руль
        stick_cols = {
            'stick_l_gas': ('Газ', 'blue'),
            'stick_l_yaw': ('Руль', 'red'),
            'stick_r_pitch': ('Тангаж', 'green'),
            'stick_r_roll': ('Крен', 'orange')
        }
        
        for col, (name, color) in stick_cols.items():
            if col in df_raw.columns:
                if col in ['stick_l_gas', 'stick_l_yaw']:
                    fig.add_trace(
                        go.Scatter(x=df_raw['timestamp'], y=df_raw[col], 
                                  name=name, line=dict(color=color)),
                        row=4, col=1
                    )
                else:
                    fig.add_trace(
                        go.Scatter(x=df_raw['timestamp'], y=df_raw[col], 
                                  name=name, line=dict(color=color)),
                        row=5, col=1
                    )

        # Настройка лейаута
        fig.update_layout(
            height=900,
            showlegend=True,
            legend=dict(x=0, y=1.05),
            title_text="Отчёт телеметрии: ТВ-телеметрия Квадросима",
            template="plotly_white"
        )
        
        fig.update_xaxes(title_text="Время (с)", row=5, col=1)
        fig.update_yaxes(title_text="Секунды", row=1, col=1)
        fig.update_yaxes(title_text="Дельта (с)", row=2, col=1)
        fig.update_yaxes(title_text="Ед.", row=3, col=1)

        # Сохранение
        html_path = self.output_dir / f"report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.html"
        pio.write_html(fig, file=str(html_path), include_plotlyjs=True, full_html=True)
        
        # Добавляем текстовый саммари в начало файла
        self._inject_summary(html_path, summary_text, laps)
        
        return str(html_path)

    def _inject_summary(self, html_path: Path, summary: str, laps: List[LapInfo]):
        """Вставляет текстовый отчёт в начало HTML."""
        if not html_path.exists():
            return
            
        content = html_path.read_text(encoding='utf-8')
        
        # Формируем таблицу кругов
        table_rows = ""
        if laps:
            best = min(l.duration for l in laps)
            for l in laps:
                table_rows += f"""
                <tr>
                    <td>{l.lap_number}</td>
                    <td>{l.duration:.3f}</td>
                    <td>{l.delta_to_best:+.3f}</td>
                    <td>{l.delta_to_prev:+.3f}</td>
                </tr>
                """
        
        summary_block = f"""
        <div style="max-width: 1200px; margin: 20px auto; padding: 20px; 
                    font-family: Arial, sans-serif; background: #f5f5f5; 
                    border-radius: 8px;">
            <h2 style="color: #333;">📊 Анализ вылета</h2>
            <div style="background: white; padding: 15px; border-radius: 5px; 
                        margin-bottom: 15px;">
                <h3>Краткие выводы:</h3>
                <p style="white-space: pre-wrap;">{summary or 'Нет данных для анализа.'}</p>
            </div>
            <div style="background: white; padding: 15px; border-radius: 5px;">
                <h3>Таблица кругов:</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #eee;">
                            <th style="padding: 8px; border: 1px solid #ddd;">№</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">Время</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">Δ к лучшему</th>
                            <th style="padding: 8px; border: 1px solid #ddd;">Δ к пред.</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>
        </div>
        <hr style="max-width: 1200px; margin: 20px auto;">
        """
        
        # Вставляем после opening body tag
        content = content.replace('<body>', f'<body>{summary_block}', 1)
        html_path.write_text(content, encoding='utf-8')

    def generate_summary_text(
        self, 
        laps: List[LapInfo], 
        stick_metrics: Dict[int, Dict[str, StickMetrics]] = None
    ) -> str:
        """Генерирует текстовые выводы на основе данных."""
        if not laps:
            return "Нет данных о кругах."
        
        lines = []
        
        # Лучший круг
        best_lap = min(laps, key=lambda x: x.duration)
        lines.append(f"✅ Лучший круг: #{best_lap.lap_number} ({best_lap.duration:.3f} сек)")
        
        # Прогресс
        if len(laps) > 1:
            first = laps[0].duration
            last = laps[-1].duration
            if last < first:
                lines.append(f"📈 Прогресс: улучшение на {first - last:.3f} сек за сессию")
            else:
                lines.append(f"📉 Время выросло на {last - first:.3f} сек относительно первого круга")
        
        # Секторы (если есть)
        if best_lap.sectors:
            slowest_sector = max(best_lap.sectors.items(), key=lambda x: x[1])
            lines.append(f"⚠️ Самый медленный сектор: #{slowest_sector[0]} ({slowest_sector[1]:.3f} сек)")
        
        # Стикс метрики
        if stick_metrics and best_lap.lap_number in stick_metrics:
            metrics = stick_metrics[best_lap.lap_number]
            throttle = metrics.get('stick_l_gas')
            if throttle and throttle.corrections_count > 10:
                lines.append(f"🎮 Высокая активность газа: {throttle.corrections_count} коррекций за круг")
                
        return "\n".join(lines)
