"""TemplateEngine-бэкенд: быстрый шаблонный OCR для цифровой телеметрии."""
from __future__ import annotations
import shutil
from pathlib import Path
import cv2
import numpy as np

from .preprocess import prepare

WHITELISTS = {
    "int": "0123456789",
    "hms": "0123456789:.",
    "mmss": "0123456789:",
    "laps": "0123456789/",
    "battery": "0123456789,.VA",
    "dt": "0123456789.:",
    "mode": "ACROHZNILEGSTMB",
}

class TemplateOCREngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        # TemplateEngine всегда доступен, используется для всех полей
        self._engine = None

    def available(self):
        return True

    def process_frame(self, frame) -> Hud:
        """Обрабатывает кадр и возвращает объект Hud с распознанными полями."""
        from .fields import FIELD_SPECS, parse_value
        from ..core.frame import Hud
        from .digits import TemplateEngine
        
        # Если передан Frame, извлекаем изображение
        if hasattr(frame, 'img'):
            img = frame.img
        else:
            img = frame
            
        hud_dict = {}
        
        # Используем TemplateEngine для распознавания
        engine = TemplateEngine()
        
        # Извлекаем ROI из конфигурации или используем дефолтные
        rois = self.cfg.get("rois", {})
        
        # Если ROI не заданы в конфиге, пробуем загрузить из файла
        if not rois:
            config_path = Path(__file__).parent.parent.parent / "config" / "hud_config.json"
            if config_path.exists():
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    rois = config.get("rois", {})
        
        for field_name, spec in FIELD_SPECS.items():
            if field_name not in rois:
                continue
                
            roi = rois[field_name]
            x, y, w, h = roi['x'], roi['y'], roi['w'], roi['h']
            
            # Вырезаем ROI из кадра
            crop = img[y:y+h, x:x+w]
            
            if crop.size == 0:
                field_target = spec.get('field')
                if isinstance(field_target, tuple):
                    for f in field_target:
                        hud_dict[f] = None
                elif field_target:
                    hud_dict[field_target] = None
                continue
            
            # Распознаём поле через TemplateEngine
            if field_name == "pilot":
                # Для пилота TemplateEngine не подходит, оставляем None
                field_target = spec.get('field')
                if field_target:
                    hud_dict[field_target] = None
                continue
            
            bw = prepare(crop, spec)
            text, conf = engine.recognize(bw, spec["kind"])
            
            # Парсим значение согласно спецификации
            parsed = parse_value(spec['kind'], text)
            
            # Маппинг на поля Hud
            field_target = spec.get('field')
            if isinstance(field_target, tuple):
                if isinstance(parsed, tuple) and len(parsed) == len(field_target):
                    for f, v in zip(field_target, parsed):
                        hud_dict[f] = v
                else:
                    for f in field_target:
                        hud_dict[f] = None
            elif field_target:
                hud_dict[field_target] = parsed
        
        return Hud(**hud_dict)

    def run(self, crop, spec: dict, binary: bool = False):
        # Вспомогательный метод для совместимости
        from .digits import TemplateEngine
        from .preprocess import prepare
        
        engine = TemplateEngine()
        bw = crop if binary else prepare(crop, spec)
        return engine.recognize(bw, spec.get("kind", "int"))
