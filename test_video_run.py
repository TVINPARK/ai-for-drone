#!/usr/bin/env python3
"""
Тестовый скрипт для обработки видеофайла video_01.mp4
"""
import sys
import os
sys.path.insert(0, '/workspace')

from qt.ocr import EasyOCREngine
from qt.sticks.detector import StickDetector
from qt.events import EventDetector
from qt.logger import DataLogger as TelemetryLogger
from qt.core.frame import Frame, Hud, Sticks
import cv2
import json

def test_video_processing(video_path: str):
    """Обработка видеофайла с тестированием всех компонентов"""
    
    print(f"🎬 Начало тестирования видео: {video_path}")
    print("=" * 60)
    
    # Проверка существования файла
    if not os.path.exists(video_path):
        print(f"❌ Файл не найден: {video_path}")
        return False
    
    # Загрузка конфигурации
    config_path = '/workspace/config.json'
    if not os.path.exists(config_path):
        print(f"❌ Config файл не найден: {config_path}")
        return False
        
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Инициализация компонентов
    print("🔧 Инициализация компонентов...")
    
    # OCR движок
    ocr_engine = EasyOCREngine(config)
    print("✅ OCR движок готов")
    
    # Детектор стиков (используем метод detect)
    stick_detector = StickDetector(config_path=config_path)
    print("✅ Детектор стиков готов")
    
    # Детектор событий (принимает Frame объекты)
    event_detector = EventDetector()
    print("✅ Детектор событий готов")
    
    # Логгер
    logger = TelemetryLogger(config=config, db_path='/workspace/test_telemetry.db')
    logger.start()
    print("✅ Логгер готов")
    
    # Открытие видео
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"❌ Не удалось открыть видео: {video_path}")
        return False
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"📊 Параметры видео: {total_frames} кадров, {fps:.2f} FPS")
    print("=" * 60)
    
    # Обработка кадров
    frame_count = 0
    processed_count = 0
    ocr_errors = 0
    stick_errors = 0
    event_count = 0
    
    print("🚀 Начало обработки кадров...")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        
        # Обработка каждого 100-го кадра для быстрого тестирования
        if frame_count % 100 != 0:
            continue
        
        print(f"\n📹 Кадр {frame_count}/{total_frames}")
        
        # 1. OCR обработка
        hud_data_dict = None
        try:
            hud_data_dict = ocr_engine.process_frame(frame)
            if hud_data_dict:
                print(f"   ✅ OCR: распознано полей: {len(hud_data_dict)}")
                for field, value in list(hud_data_dict.items())[:3]:
                    print(f"      - {field}: {value}")
                processed_count += 1
            else:
                print(f"   ⚠️ OCR: нет данных")
        except Exception as e:
            ocr_errors += 1
            print(f"   ❌ OCR ошибка: {e}")
        
        # 2. Детекция стиков (метод detect)
        sticks_data = None
        try:
            sticks_data = stick_detector.detect(frame)
            if sticks_data:
                print(f"   ✅ Стики: {sticks_data}")
        except Exception as e:
            stick_errors += 1
            print(f"   ❌ Ошибка детекции стиков: {e}")
        
        # 3. Создаём Frame объект для логгера и детектора событий
        frame_obj = None
        if hud_data_dict or sticks_data:
            try:
                # Преобразуем словарь HUD в объект Hud
                hud_obj = None
                if hud_data_dict:
                    hud_obj = Hud(
                        speed=hud_data_dict.get('speed'),
                        alt=hud_data_dict.get('alt'),
                        cur_t=hud_data_dict.get('cur_t'),
                        best_t=hud_data_dict.get('best_t'),
                        lap_cur=hud_data_dict.get('lap_cur'),
                        bat_v=hud_data_dict.get('bat_v'),
                        bat_a=hud_data_dict.get('bat_a'),
                        pilot=hud_data_dict.get('pilot'),
                        mode=hud_data_dict.get('mode')
                    )
                
                # Преобразуем данные стиков в объект Sticks
                sticks_obj = None
                if sticks_data:
                    sticks_obj = Sticks(
                        lx=sticks_data.get('lx'),
                        ly=sticks_data.get('ly'),
                        rx=sticks_data.get('rx'),
                        ry=sticks_data.get('ry')
                    )
                
                frame_obj = Frame(t=frame_count / fps, hud=hud_obj, sticks=sticks_obj)
            except Exception as e:
                print(f"   ⚠️ Ошибка создания Frame объекта: {e}")
        
        # 4. Детекция событий
        if frame_obj:
            try:
                events = event_detector.process_frame(frame_obj)
                if events:
                    event_count += len(events)
                    print(f"   🎯 События: {len(events)} найдено")
            except Exception as e:
                print(f"   ❌ Ошибка детекции событий: {e}")
        
        # 5. Логирование
        if frame_obj:
            try:
                logger.put(frame_obj)
            except Exception as e:
                print(f"   ❌ Ошибка логгирования: {e}")
        
        # Прерываем после 10 успешно обработанных кадров для быстрого теста
        if processed_count >= 10:
            print("\n⏹️ Прерывание после 10 успешно обработанных кадров")
            break
    
    # Завершение
    cap.release()
    logger.stop()
    
    # Статистика
    print("\n" + "=" * 60)
    print("📊 СТАТИСТИКА ТЕСТИРОВАНИЯ")
    print("=" * 60)
    print(f"Всего кадров обработано: {frame_count}")
    print(f"Успешно обработано кадров: {processed_count}")
    print(f"Ошибок OCR: {ocr_errors}")
    print(f"Ошибок детекции стиков: {stick_errors}")
    print(f"Всего событий найдено: {event_count}")
    print(f"База данных: /workspace/test_telemetry.db")
    print("=" * 60)
    
    if processed_count > 0:
        print("✅ Тестирование завершено успешно!")
        return True
    else:
        print("❌ Тестирование завершено с ошибками")
        return False

if __name__ == "__main__":
    video_path = "/workspace/tests/fixtures/video_01.mp4"
    success = test_video_processing(video_path)
    sys.exit(0 if success else 1)
