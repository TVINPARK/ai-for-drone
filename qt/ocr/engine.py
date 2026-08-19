"""EasyOCR-бэкенд: кириллица (ФИО), fallback и тренер шаблонного движка."""
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

class EasyOCREngine:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        try:
            import easyocr
        except ImportError:
            print("⚠️ EasyOCR не установлен. Будет использоваться только шаблонный движок для цифр.")
            self._reader = None
            return
        
        # Инициализируем читатель с поддержкой русского и английского языков
        # gpu=False для максимальной совместимости (работает на CPU)
        self._reader = easyocr.Reader(['ru', 'en'], gpu=False, verbose=False)

    def available(self):
        try:
            # Проверка работоспособности путем попытки инициализации
            return self._reader is not None
        except Exception:
            return False

    def process_frame(self, frame) -> Hud:
        """Обрабатывает кадр и возвращает объект Hud с распознанными полями."""
        from .fields import FIELD_SPECS, parse_value
        from ..core.frame import Hud
        
        # Если передан Frame, извлекаем изображение
        if hasattr(frame, 'img'):
            img = frame.img
        else:
            img = frame
            
        hud_dict = {}
        
        # Если EasyOCR не доступен, используем только TemplateEngine для цифр
        if self._reader is None:
            # Возвращаем пустой HUD или используем шаблонный движок
            from .digits import TemplateEngine
            template_engine = TemplateEngine(self.cfg)
            result_dict = template_engine.process_frame(img)
            return Hud(**result_dict) if isinstance(result_dict, dict) else result_dict
        
        # Извлекаем ROI из конфигурации
        rois = self.cfg.get("rois", {})
        
        for field_name, spec in FIELD_SPECS.items():
            if field_name not in rois:
                continue
                
            roi = rois[field_name]
            x, y, w, h = roi['x'], roi['y'], roi['w'], roi['h']
            
            # Вырезаем ROI из кадра
            crop = img[y:y+h, x:x+w]
            
            if crop.size == 0:
                # Устанавливаем значение по умолчанию в зависимости от типа поля
                field_target = spec.get('field')
                if isinstance(field_target, tuple):
                    for f in field_target:
                        hud_dict[f] = None
                elif field_target:
                    hud_dict[field_target] = None
                continue
            
            # Распознаём поле
            txt, conf = self.run(crop, spec)
            
            # Парсим значение согласно спецификации
            parsed = parse_value(spec['kind'], txt)
            
            # Маппинг на поля Hud
            field_target = spec.get('field')
            if isinstance(field_target, tuple):
                # Для полей типа laps и battery parsed - это кортеж
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
        # Если EasyOCR не доступен, возвращаем пустой результат
        if self._reader is None:
            return "", 0.0
        
        # Для текстовых полей (pilot) используем предварительную обработку
        if spec.get("kind") == "pilot":
            gray = crop if len(crop.shape) == 2 else cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            # Бинаризация Otsu
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            # Морфологическое открытие для удаления шума
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 1))
            bw = cv2.erode(bw, kernel, iterations=1)
            bw = cv2.dilate(bw, kernel, iterations=1)
            # Добавим рамку
            img = cv2.copyMakeBorder(bw, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)
            # Масштабирование для улучшения распознавания
            img = cv2.resize(img, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        else:
            # Для числовых полей используем стандартную предобработку
            bw = crop if binary else prepare(crop, spec)
            img = 255 - bw
            img = cv2.copyMakeBorder(img, 16, 16, 16, 16, cv2.BORDER_CONSTANT, value=255)
        
        try:
            # EasyOCR возвращает список кортежей: (bbox, text, confidence)
            results = self._reader.readtext(img, detail=1, paragraph=False)
            
            if not results:
                return "", 0.0
            
            # Объединяем результаты, если их несколько
            texts = [r[1] for r in results]
            confidences = [r[2] for r in results]
            
            txt = " ".join(texts).strip()
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
            
            return txt, float(avg_conf)
        except Exception:
            return "", 0.0
