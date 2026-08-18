"""
GUI Калибратор зон HUD для ТВ-телеметрии Квадросима
Замените консольную калибровку на интуитивный графический интерфейс
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import mss
    from PIL import Image, ImageTk
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

# Зоны для калибровки
ROI_ZONES = {
    "pilot_info": {"label": "Пилот (верх-лево)", "color": "#FF6B6B"},
    "battery": {"label": "Батарея (верх-лево)", "color": "#4ECDC4"},
    "flight_mode": {"label": "Режим полёта (верх-лево)", "color": "#45B7D1"},
    "time_limit": {"label": "Лимит времени (верх-право)", "color": "#96CEB4"},
    "speed": {"label": "Скорость (центр-лево)", "color": "#FFEAA7"},
    "altitude": {"label": "Высота (центр-право)", "color": "#DFE6E9"},
    "laps": {"label": "Круги (низ-лево)", "color": "#A29BFE"},
    "current_time": {"label": "Текущее время (низ-лево)", "color": "#6C5CE7"},
    "best_time": {"label": "Лучшее время (низ-право)", "color": "#FD79A8"},
    "sticks": {"label": "Стики (низ-центр)", "color": "#FAB1A0"},
}


class ROIRectangle:
    """Класс для управления прямоугольником зоны на холсте"""
    
    def __init__(self, canvas, x1, y1, x2, y2, color, label):
        self.canvas = canvas
        self.color = color
        self.label = label
        self.rect = canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=3, tags="roi")
        self.text = canvas.create_text((x1+x2)//2, y1-10, text=label, fill=color, font=("Arial", 10, "bold"), tags="roi")
        self.coords = [x1, y1, x2, y2]
        
        # Привязка событий
        self.canvas.tag_bind(self.rect, "<ButtonPress-1>", self.on_press)
        self.canvas.tag_bind(self.rect, "<B1-Motion>", self.on_drag)
        self.canvas.tag_bind(self.rect, "<ButtonRelease-1>", self.on_release)
        self.canvas.tag_bind(self.text, "<ButtonPress-1>", self.on_press)
        self.canvas.tag_bind(self.text, "<B1-Motion>", self.on_drag)
        self.canvas.tag_bind(self.text, "<ButtonRelease-1>", self.on_release)
        
        self._drag_data = {"x": 0, "y": 0}
    
    def on_press(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
    
    def on_drag(self, event):
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        
        # Обновляем координаты
        self.coords[0] += dx
        self.coords[1] += dy
        self.coords[2] += dx
        self.coords[3] += dy
        
        # Перерисовываем
        self.canvas.coords(self.rect, *self.coords)
        self.canvas.coords(self.text, (self.coords[0]+self.coords[2])//2, self.coords[1]-10)
        
        # Обновляем данные для следующего перетаскивания
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
    
    def on_release(self, event):
        pass
    
    def get_roi(self):
        """Возвращает ROI в формате [x, y, width, height]"""
        x1, y1, x2, y2 = self.coords
        return [int(x1), int(y1), int(x2-x1), int(y2-y1)]


class CalibrationApp:
    """Основное приложение калибратора"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Калибратор ТВ-телеметрия Квадросима")
        self.root.geometry("1200x800")
        
        self.roi_rects = {}
        self.screenshot = None
        
        # Проверка зависимостей
        if not HAS_DEPS:
            messagebox.showerror("Ошибка", "Не установлены зависимости: mss, pillow\nЗапустите: pip install mss pillow")
            root.destroy()
            return
        
        self._create_ui()
        self._load_screenshot()
    
    def _create_ui(self):
        """Создание интерфейса"""
        # Верхняя панель
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(top_frame, text="📸 Сделать скриншот", command=self._load_screenshot).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="💾 Сохранить config.json", command=self._save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="📂 Загрузить config.json", command=self._load_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="❓ Помощь", command=self._show_help).pack(side=tk.RIGHT, padx=5)
        
        ttk.Label(top_frame, text="Перетаскивайте рамки для настройки зон").pack(side=tk.LEFT, padx=20)
        
        # Холст для скриншота
        self.canvas_frame = ttk.Frame(self.root)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars
        h_scroll = ttk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        v_scroll = ttk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Нижняя панель со списком зон
        bottom_frame = ttk.LabelFrame(self.root, text="Зоны ROI")
        bottom_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Создаем чекбоксы для каждой зоны
        self.zone_vars = {}
        cols = 5
        for i, (key, zone_info) in enumerate(ROI_ZONES.items()):
            row = i // cols
            col = i % cols
            
            var = tk.BooleanVar(value=True)
            self.zone_vars[key] = var
            
            cb = ttk.Checkbutton(bottom_frame, text=f"{zone_info['label']} ({zone_info['color']})", 
                                variable=var, command=lambda k=key: self._toggle_zone(k))
            cb.grid(row=row, column=col, sticky=tk.W, padx=10, pady=5)
    
    def _load_screenshot(self):
        """Загрузка скриншота экрана"""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # Все экраны
                screenshot = sct.grab(monitor)
                self.screenshot = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            # Масштабируем если нужно
            max_width = 1000
            if self.screenshot.width > max_width:
                ratio = max_width / self.screenshot.width
                new_size = (max_width, int(self.screenshot.height * ratio))
                self.screenshot = self.screenshot.resize(new_size, Image.Resampling.LANCZOS)
            
            self.photo = ImageTk.PhotoImage(self.screenshot)
            
            # Очищаем и рисуем
            self.canvas.delete("all")
            self.canvas.config(scrollregion=(0, 0, self.screenshot.width, self.screenshot.height))
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
            
            # Создаем ROI прямоугольники
            self._create_roi_rectangles()
            
            messagebox.showinfo("Успех", f"Скриншот сделан: {self.screenshot.width}x{self.screenshot.height}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сделать скриншот: {e}")
    
    def _create_roi_rectangles(self):
        """Создание прямоугольников зон по умолчанию"""
        # Очищаем старые
        self.canvas.delete("roi")
        self.roi_rects.clear()
        
        w, h = self.screenshot.width, self.screenshot.height
        
        # Дефолтные позиции (примерные)
        defaults = {
            "pilot_info": [10, 10, 250, 80],
            "battery": [10, 90, 150, 140],
            "flight_mode": [160, 90, 250, 140],
            "time_limit": [w-250, 10, w-10, 80],
            "speed": [10, h//2-100, 150, h//2+100],
            "altitude": [w-150, h//2-100, w-10, h//2+100],
            "laps": [10, h-100, 200, h-10],
            "current_time": [10, h-150, 250, h-110],
            "best_time": [w-250, h-100, w-10, h-10],
            "sticks": [w//2-200, h-150, w//2+200, h-10],
        }
        
        for key, coords in defaults.items():
            if key in ROI_ZONES:
                zone_info = ROI_ZONES[key]
                rect = ROIRectangle(self.canvas, *coords, zone_info["color"], zone_info["label"])
                self.roi_rects[key] = rect
    
    def _toggle_zone(self, key):
        """Показать/скрыть зону"""
        if self.zone_vars[key].get():
            self.canvas.itemconfig(self.roi_rects[key].rect, state=tk.NORMAL)
            self.canvas.itemconfig(self.roi_rects[key].text, state=tk.NORMAL)
        else:
            self.canvas.itemconfig(self.roi_rects[key].rect, state=tk.HIDDEN)
            self.canvas.itemconfig(self.roi_rects[key].text, state=tk.HIDDEN)
    
    def _save_config(self):
        """Сохранение конфигурации в JSON"""
        config = {"rois": {}}
        
        for key, rect in self.roi_rects.items():
            if self.zone_vars[key].get():
                config["rois"][key] = rect.get_roi()
        
        filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
        
        # Если файл существует, загружаем и обновляем
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                existing["rois"].update(config["rois"])
                config = existing
            except:
                pass
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Успех", f"Конфигурация сохранена в:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}")
    
    def _load_config(self):
        """Загрузка существующей конфигурации"""
        filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
        
        if not os.path.exists(filepath):
            messagebox.showwarning("Предупреждение", "Файл config.json не найден")
            return
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            rois = config.get("rois", {})
            
            # Применяем координаты к прямоугольникам
            for key, roi in rois.items():
                if key in self.roi_rects and len(roi) == 4:
                    x, y, w, h = roi
                    rect = self.roi_rects[key]
                    rect.coords = [x, y, x+w, y+h]
                    self.canvas.coords(rect.rect, *rect.coords)
                    self.canvas.coords(rect.text, (rect.coords[0]+rect.coords[2])//2, rect.coords[1]-10)
            
            messagebox.showinfo("Успех", "Конфигурация загружена")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить: {e}")
    
    def _show_help(self):
        """Показать справку"""
        help_text = """
        ИНСТРУКЦИЯ ПО КАЛИБРОВКЕ:
        
        1. Нажмите '📸 Сделать скриншот' для захвата текущего экрана
        2. Перетаскивайте цветные рамки мышью для точной настройки зон
        3. Используйте чекбоксы внизу для показа/скрытия зон
        4. Нажмите '💾 Сохранить config.json' для сохранения настроек
        5. Запустите main.py для начала телеметрии
        
        СОВЕТЫ:
        - Убедитесь, что симулятор запущен на полном экране
        - Размещайте рамки точно вокруг цифр/текста
        - Для стиков захватите оба крестика с точками
        """
        messagebox.showinfo("Помощь", help_text)


def main():
    root = tk.Tk()
    app = CalibrationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
