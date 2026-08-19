#!/usr/bin/env python3
"""Тестирование обработки видеофайла"""

import sys
import os
import json

# Добавляем workspace в путь для корректных импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Импортируем как модули из qt
from qt.ocr import EasyOCREngine
from qt.core.frame import Frame
from qt.sticks.detector import StickDetector
from qt.events import EventDetector
from qt.logger import DataLogger
import cv2
import time

def test_video_processing(video_path):
    """Обработка видеофайла с выводом результатов"""
    
    print(f"🎬 Начинаем обработку видео: {video_path}")
    print("=" * 60)
    
    # Проверка существования файла
    if not os.path.exists(video_path):
        print(f"❌ Файл не найден: {video_path}")
        return False
    
    # Загрузка конфигурации
    config_file = "config.json"
    if os.path.exists(config_file):
        print(f"📍 Загрузка конфигурации из {config_file}")
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        print("⚠️  Файл конфигурации не найден, используем значения по умолчанию")
        config = {}
    
    # Инициализация компонентов
    print("🔧 Инициализация компонентов...")
    ocr_engine = EasyOCREngine(config)
    stick_detector = StickDetector()
    event_detector = EventDetector()
    logger = DataLogger()
    
    # Открытие видео
    print("📹 Открытие видеофайла...")
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"❌ Не удалось открыть видеофайл: {video_path}")
        return False
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps if fps > 0 else 0
    
    print(f"📊 Информация о видео:")
    print(f"   - Всего кадров: {total_frames}")
    print(f"   - FPS: {fps:.2f}")
    print(f"   - Длительность: {duration:.2f} сек")
    print("=" * 60)
    
    # Обработка кадров
    processed_frames = 0
    ocr_success = 0
    sticks_detected = 0
    events_detected = 0
    
    start_time = time.time()
    
    print("🔄 Обработка кадров (первые 50 кадров для теста)...")
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            break
        
        processed_frames += 1
        
        # Ограничим обработку первыми 50 кадрами для быстрого теста
        if processed_frames > 50:
            break
        
        # Создание объекта Frame
        frame_obj = Frame(frame, processed_frames)
        
        # OCR обработка
        try:
            ocr_result = ocr_engine.process_frame(frame_obj)
            if ocr_result and any(ocr_result.values()):
                ocr_success += 1
        except Exception as e:
            print(f"⚠️  OCR ошибка в кадре {processed_frames}: {e}")
        
        # Детекция стиков
        try:
            sticks = stick_detector.detect(frame)
            if sticks:
                sticks_detected += 1
        except Exception as e:
            print(f"⚠️  Stick detector ошибка в кадре {processed_frames}: {e}")
        
        # Детекция событий
        try:
            events = event_detector.process_frame(frame_obj)
            if events:
                events_detected += len(events)
        except Exception as e:
            print(f"⚠️  Event detector ошибка в кадре {processed_frames}: {e}")
        
        # Прогресс
        if processed_frames % 10 == 0:
            print(f"   Обработано кадров: {processed_frames}/50")
    
    cap.release()
    
    elapsed_time = time.time() - start_time
    
    # Вывод результатов
    print("=" * 60)
    print("✅ Результаты тестирования:")
    print(f"   - Обработано кадров: {processed_frames}")
    print(f"   - Успешных OCR распознаваний: {ocr_success}")
    print(f"   - Кадров с обнаруженными стиками: {sticks_detected}")
    print(f"   - Обнаружено событий: {events_detected}")
    print(f"   - Время обработки: {elapsed_time:.2f} сек")
    print(f"   - Скорость обработки: {processed_frames/elapsed_time:.2f} кадров/сек")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    video_path = "tests/fixtures/video_01.mp4"
    success = test_video_processing(video_path)
    
    if success:
        print("\n🎉 Тестирование завершено успешно!")
        sys.exit(0)
    else:
        print("\n❌ Тестирование завершено с ошибками!")
        sys.exit(1)
