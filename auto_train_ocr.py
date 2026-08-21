#!/usr/bin/env python3
"""
Скрипт автоматической калибровки OCR атласа на основе видео.
Извлекает все уникальные символы из ROI, кластеризует их и создаёт атлас.
"""
import cv2
import numpy as np
from pathlib import Path
import json
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from qt.ocr.digits import TemplateEngine, segment, window_for
from qt.ocr.preprocess import prepare
from qt.ocr.fields import FIELD_SPECS

CHAR_H, CHAR_W = 32, 20

def extract_chars_from_video(video_path: str, config_path: str, output_atlas: str = "ocr_atlas.npz", max_frames: int = 500):
    """
    Извлекает символы из видео и создаёт обученный атлас.
    
    Args:
        video_path: Путь к видеофайлу
        config_path: Путь к конфигурации с ROI
        output_atlas: Путь для сохранения атласа
        max_frames: Максимальное количество кадров для анализа
    """
    # Загружаем конфиг
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    
    rois = cfg.get('rois', {})
    
    # Открываем видео
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Не удалось открыть видео: {video_path}")
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Видео: {total_frames} кадров, {fps:.1f} FPS")
    
    # Пропускаем первые 200 кадров (меню/статистика)
    skip_frames = 200
    for _ in range(skip_frames):
        cap.read()
    
    # Коллекция всех извлечённых символов
    # Формат: {field_name: [(binary_vector, roi_name, frame_idx), ...]}
    all_chars = {}
    
    frame_idx = 0
    processed = 0
    
    print("Извлечение символов из видео...")
    
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
        
        if frame_idx >= max_frames:
            break
        
        # Пропускаем кадры для разнообразия (каждый 10-й)
        if frame_idx % 10 != 0:
            frame_idx += 1
            continue
        
        # Извлекаем символы из каждого ROI
        for field_name, roi_spec in rois.items():
            if field_name == 'pilot':
                continue
            
            if field_name not in FIELD_SPECS:
                continue
            
            x, y, w, h = roi_spec['x'], roi_spec['y'], roi_spec['w'], roi_spec['h']
            crop = frame[y:y+h, x:x+w]
            
            if crop.size == 0:
                continue
            
            spec = FIELD_SPECS[field_name]
            bw = prepare(crop, spec)
            
            kind = spec.get('kind', 'int')
            segs_raw = segment(bw)
            segs = window_for(segs_raw, kind)
            
            # Извлекаем каждый сегмент как отдельный символ
            for seg_idx, s in enumerate(segs):
                x0, x1, y0, y1 = s
                
                # Пропускаем слишком широкие сегменты (слипшиеся символы)
                if (x1 - x0) > CHAR_W * 1.5:
                    continue
                
                # Нормализуем символ
                char_crop = bw[y0:y1+1, x0:x1+1]
                if char_crop.size == 0:
                    continue
                
                try:
                    char_norm = cv2.resize(char_crop, (CHAR_W, CHAR_H), interpolation=cv2.INTER_AREA)
                    char_binary = (char_norm > 0.5).astype(np.float32).flatten()
                    
                    if field_name not in all_chars:
                        all_chars[field_name] = []
                    
                    all_chars[field_name].append((char_binary, field_name, frame_idx, seg_idx))
                except Exception as e:
                    pass
        
        frame_idx += 1
        processed += 1
        
        if processed % 50 == 0:
            print(f"  Обработано {processed} кадров...")
    
    cap.release()
    
    print(f"\nВсего извлечено символов: {sum(len(v) for v in all_chars.values())}")
    
    # Для каждого поля кластеризуем символы и пытаемся распознать
    engine = TemplateEngine()
    
    for field_name, chars in all_chars.items():
        if len(chars) < 2:
            continue
        
        print(f"\n=== {field_name} ===")
        print(f"  Символов: {len(chars)}")
        
        # Преобразуем в массив
        char_vectors = np.array([c[0] for c in chars])
        
        # Определяем количество уникальных символов через силуэт
        # Для цифр обычно 10-12 классов (0-9 + : + .)
        n_clusters = min(12, len(chars) // 3)
        n_clusters = max(2, n_clusters)
        
        # Кластеризация
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(char_vectors)
        
        # Считаем силуэт для оценки качества
        if len(set(labels)) > 1:
            score = silhouette_score(char_vectors, labels)
            print(f"  Silhouette score: {score:.3f} ({n_clusters} кластеров)")
        
        # Для каждого кластера берём центральный элемент и сохраняем в атлас
        unique_labels = sorted(set(labels))
        
        for label in unique_labels:
            cluster_indices = np.where(labels == label)[0]
            
            # Находим самый центральный элемент (ближайший к центру кластера)
            cluster_center = kmeans.cluster_centers_[label]
            cluster_vectors = char_vectors[cluster_indices]
            
            distances = np.linalg.norm(cluster_vectors - cluster_center, axis=1)
            central_idx = cluster_indices[np.argmin(distances)]
            
            # Получаем оригинальные данные
            char_binary, orig_field, frame_id, seg_id = chars[central_idx]
            
            # Восстанавливаем изображение
            char_img = char_binary.reshape(CHAR_H, CHAR_W)
            
            # Пытаемся определить символ по эвристике
            # Если не получилось - используем номер кластера как плейсхолдер
            symbol = guess_symbol(char_img, field_name)
            
            # Если символ не определён, используем временное имя
            if not symbol:
                # Для цифр можно использовать простую эвристику
                symbol = guess_digit_simple(char_img)
            
            if symbol and symbol not in engine.atlas:
                engine.atlas[symbol] = [char_img]
                print(f"  Добавлен символ '{symbol}' (кластер {label}, {len(cluster_indices)} элементов)")
            elif symbol and symbol in engine.atlas:
                # Добавляем ещё один пример в атлас
                if len(engine.atlas[symbol]) < 10:
                    engine.atlas[symbol].append(char_img)
    
    # Сохраняем атлас
    if engine.trained:
        engine.save(output_atlas)
        print(f"\n✅ Атлас сохранён: {output_atlas}")
        print(f"   Символов в атласе: {len(engine.atlas)} ({list(engine.atlas.keys())})")
        
        # Тестируем на последнем кадре
        test_frame(video_path, skip_frames + max_frames, cfg, engine)
    else:
        print("\n⚠ Не удалось создать атлас")
    
    return engine


def guess_symbol(char_img: np.ndarray, field_name: str) -> str:
    """
    Эвристическое определение символа по изображению.
    """
    # Простые эвристики на основе геометрии
    h, w = char_img.shape
    
    # Подсчитываем заполненность
    fill_ratio = char_img.sum() / (h * w)
    
    # Проверяем вертикальную симметрию
    left_half = char_img[:, :w//2]
    right_half = char_img[:, w//2:]
    symmetry = np.corrcoef(left_half.flatten(), right_half.flatten())[0, 1] if left_half.sum() > 0 and right_half.sum() > 0 else 0
    
    # Проверяем горизонтальную симметрию
    top_half = char_img[:h//2, :]
    bottom_half = char_img[h//2:, :]
    h_symmetry = np.corrcoef(top_half.flatten(), bottom_half.flatten())[0, 1] if top_half.sum() > 0 and bottom_half.sum() > 0 else 0
    
    return None


def guess_digit_simple(char_img: np.ndarray) -> str:
    """
    Простая эвристика для определения цифр 0-9 и символов :, .
    Возвращает символ или None если не удалось определить.
    """
    h, w = char_img.shape
    total_pixels = char_img.sum()
    fill_ratio = total_pixels / (h * w)
    
    # Пустой символ
    if fill_ratio < 0.05:
        return None
    
    # Очень узкий символ - вероятно '1'
    cols_with_pixels = np.any(char_img > 0, axis=0)
    width = np.sum(cols_with_pixels)
    
    if width <= 4:
        return '1'
    
    # Разделяющие символы (: или .)
    if fill_ratio < 0.15 and width < 8:
        # Проверяем есть ли два отдельных компонента (для :)
        rows_with_pixels = np.any(char_img > 0, axis=1)
        if np.sum(rows_with_pixels) < h * 0.3:
            return '.'
        return ':'
    
    # Для остальных цифр используем простую эвристику
    # В реальной системе лучше использовать обученную модель
    
    # Если заполненность высокая и есть симметрия - возможно '8' или '0'
    if fill_ratio > 0.35:
        return '8'  # Предполагаем 8 как наиболее заполненную цифру
    
    # Средняя заполненность -可能是 4, 5, 6, 9, 0
    if fill_ratio > 0.25:
        return '0'
    
    # Низкая заполненность -可能是 2, 3, 7
    if fill_ratio > 0.15:
        return '4'
    
    return '?'  # Неопознанный символ


def test_frame(video_path: str, frame_idx: int, cfg: dict, engine: TemplateEngine):
    """Тестирует распознавание на указанном кадре."""
    cap = cv2.VideoCapture(video_path)
    
    # Переходим к кадру
    for _ in range(frame_idx):
        cap.read()
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        return
    
    print("\n=== Тест распознавания ===")
    
    rois = cfg.get('rois', {})
    
    for field_name, roi_spec in rois.items():
        if field_name == 'pilot' or field_name not in FIELD_SPECS:
            continue
        
        x, y, w, h = roi_spec['x'], roi_spec['y'], roi_spec['w'], roi_spec['h']
        crop = frame[y:y+h, x:x+w]
        
        if crop.size == 0:
            continue
        
        spec = FIELD_SPECS[field_name]
        bw = prepare(crop, spec)
        kind = spec.get('kind', 'int')
        
        text, conf = engine.recognize(bw, kind)
        print(f"{field_name}: \"{text}\" (conf={conf:.2f})")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Автоматическая калибровка OCR атласа")
    parser.add_argument("video", help="Путь к видеофайлу")
    parser.add_argument("-c", "--config", default="config.json", help="Путь к конфигурации")
    parser.add_argument("-o", "--output", default="ocr_atlas.npz", help="Путь для сохранения атласа")
    parser.add_argument("-n", "--frames", type=int, default=500, help="Макс. количество кадров")
    
    args = parser.parse_args()
    
    extract_chars_from_video(
        video_path=args.video,
        config_path=args.config,
        output_atlas=args.output,
        max_frames=args.frames
    )
