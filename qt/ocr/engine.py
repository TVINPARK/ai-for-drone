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
        try:
            import easyocr
        except ImportError:
            raise ImportError("EasyOCR не установлен. Установите: pip install easyocr")
        
        # Инициализируем читатель с поддержкой русского и английского языков
        # gpu=False для максимальной совместимости (работает на CPU)
        self._reader = easyocr.Reader(['ru', 'en'], gpu=False, verbose=False)

    def available(self):
        try:
            # Проверка работоспособности путем попытки инициализации
            return self._reader is not None
        except Exception:
            return False

    def run(self, crop, spec: dict, binary: bool = False):
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
