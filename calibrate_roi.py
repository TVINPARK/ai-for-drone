"""
Скрипт для автоматической калибровки зон HUD (ROI) на основе анализа видео.
Ищет стабильные области с цифрами/текстом и предлагает пользователю подтвердить зоны.
"""

import cv2
import numpy as np
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import matplotlib.pyplot as plt

class ROICalibrator:
    def __init__(self, video_path: str):
        self.video_path = video_path
        self.cap = cv2.VideoCapture(video_path)
        if not self.cap.isOpened():
            raise ValueError(f"Не удалось открыть видео: {video_path}")
        
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Стандартные относительные позиции HUD элементов (для FPV дронов)
        # Можно настроить под конкретный шлем/видео
        self.default_rois = {
            "throttle": {"x_rel": 0.05, "y_rel": 0.85, "w_rel": 0.15, "h_rel": 0.1},
            "pitch": {"x_rel": 0.5, "y_rel": 0.9, "w_rel": 0.15, "h_rel": 0.08},
            "roll": {"x_rel": 0.85, "y_rel": 0.85, "w_rel": 0.15, "h_rel": 0.1},
            "yaw": {"x_rel": 0.5, "y_rel": 0.05, "w_rel": 0.15, "h_rel": 0.08},
            "battery": {"x_rel": 0.9, "y_rel": 0.05, "w_rel": 0.1, "h_rel": 0.05},
            "flight_time": {"x_rel": 0.1, "y_rel": 0.05, "w_rel": 0.15, "h_rel": 0.05}
        }

    def detect_text_regions(self, frame: np.ndarray) -> List[Dict]:
        """
        Обнаруживает потенциальные текстовые регионы на кадре.
        Использует морфологические операции и поиск контуров.
        Оптимизировано для OSD с ярким текстом на темном/разноцветном фоне.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Метод 1: Порог для очень ярких элементов (OSD обычно белый/яркий)
        _, binary1 = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
        
        # Метод 2: Адаптивный порог для контрастного текста
        binary2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                        cv2.THRESH_BINARY, 15, 5)
        
        # Объединяем результаты
        binary = cv2.bitwise_or(binary1, binary2)
        
        # Инвертируем для поиска светлого текста
        binary_inv = cv2.bitwise_not(binary)
        
        # Морфологические операции для объединения символов в слова
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        dilated = cv2.dilate(binary, kernel, iterations=2)
        eroded = cv2.erode(dilated, kernel, iterations=1)
        
        # Поиск контуров
        contours, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        regions = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = cv2.contourArea(cnt)
            
            # Фильтр по размеру (адаптирован под HD видео 1920x1080)
            if 200 < area < 30000 and w > 15 and h > 8:
                # Проверка соотношения сторон (текст обычно вытянут)
                aspect_ratio = w / float(h)
                if 0.8 < aspect_ratio < 8:
                    # Дополнительная проверка: средняя яркость в регионе должна быть высокой
                    roi = gray[y:y+h, x:x+w]
                    mean_brightness = np.mean(roi)
                    if mean_brightness > 180:  # OSD обычно яркий
                        regions.append({
                            "x": x, "y": y, "w": w, "h": h,
                            "confidence": area / (w * h),
                            "brightness": mean_brightness
                        })
        
        return regions

    def analyze_stability(self, regions_per_frame: List[List[Dict]], threshold: float = 0.7) -> List[Dict]:
        """
        Анализирует стабильность регионов across кадров.
        Возвращает только те регионы, которые присутствуют в >threshold% кадров.
        """
        if not regions_per_frame:
            return []
        
        # Собираем все уникальные позиции (кластеризация простая)
        all_centers = []
        for frame_idx, regions in enumerate(regions_per_frame):
            for reg in regions:
                cx, cy = reg["x"] + reg["w"]/2, reg["y"] + reg["h"]/2
                all_centers.append((cx, cy, reg["w"], reg["h"], frame_idx))
        
        if not all_centers:
            return []
        
        # Простая кластеризация: группируем близкие центры
        clusters = []
        used = [False] * len(all_centers)
        
        for i, (cx, cy, w, h, f_idx) in enumerate(all_centers):
            if used[i]:
                continue
            
            cluster = [(cx, cy, w, h, f_idx)]
            used[i] = True
            
            for j in range(i+1, len(all_centers)):
                if used[j]:
                    continue
                cx2, cy2, w2, h2, f_idx2 = all_centers[j]
                dist = np.sqrt((cx-cx2)**2 + (cy-cy2)**2)
                
                if dist < 20:  # Порог близости в пикселях
                    cluster.append((cx2, cy2, w2, h2, f_idx2))
                    used[j] = True
            
            clusters.append(cluster)
        
        # Фильтруем кластеры по стабильности (должны быть во многих кадрах)
        stable_rois = []
        min_frames_required = int(len(regions_per_frame) * threshold)
        
        for cluster in clusters:
            if len(cluster) >= min_frames_required:
                # Усредняем координаты
                avg_cx = sum(c[0] for c in cluster) / len(cluster)
                avg_cy = sum(c[1] for c in cluster) / len(cluster)
                avg_w = sum(c[2] for c in cluster) / len(cluster)
                avg_h = sum(c[3] for c in cluster) / len(cluster)
                
                stable_rois.append({
                    "x": int(avg_cx - avg_w/2),
                    "y": int(avg_cy - avg_h/2),
                    "w": int(avg_w),
                    "h": int(avg_h),
                    "stability": len(cluster) / len(regions_per_frame)
                })
        
        return stable_rois

    def run_calibration(self, sample_frames: int = 100, output_file: str = "hud_config.json"):
        """
        Запускает процесс калибровки.
        1. Берет sample_frames кадров из середины видео (чтобы избежать меню).
        2. Ищет текстовые регионы.
        3. Находит стабильные регионы.
        4. Предлагает пользователю сопоставить их с полями HUD.
        """
        print(f"🎥 Анализ видео: {self.video_path}")
        print(f"📊 Размер: {self.width}x{self.height}, FPS: {self.fps}, Всего кадров: {self.total_frames}")
        
        # Пропускаем начало (меню) и берем кадры из середины
        start_frame = int(self.total_frames * 0.1)  # Первые 10% пропускаем
        step = max(1, (int(self.total_frames * 0.9) - start_frame) // sample_frames)
        
        regions_per_frame = []
        frames_data = []
        
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        print("🔍 Сканирование кадров на наличие текстовых регионов...")
        count = 0
        while count < sample_frames:
            ret, frame = self.cap.read()
            if not ret:
                break
            
            regions = self.detect_text_regions(frame)
            if regions:
                regions_per_frame.append(regions)
                frames_data.append(frame)
                count += 1
                
            if count % 10 == 0:
                print(f"   Обработано {count}/{sample_frames} кадров...")
        
        if not regions_per_frame:
            print("❌ Не найдено текстовых регионов. Возможно, низкое качество или нет OSD.")
            return None
        
        print("📈 Анализ стабильности регионов...")
        stable_rois = self.analyze_stability(regions_per_frame)
        
        print(f"✅ Найдено {len(stable_rois)} стабильных регионов.")
        
        # Визуализация результатов
        if len(frames_data) > 0:
            sample_frame = frames_data[0]
            vis_frame = sample_frame.copy()
            
            for i, roi in enumerate(stable_rois):
                x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
                cv2.rectangle(vis_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(vis_frame, f"#{i}", (x, y-5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            plt.figure(figsize=(15, 10))
            plt.imshow(cv2.cvtColor(vis_frame, cv2.COLOR_BGR2RGB))
            plt.title(f"Найдено стабильных регионов: {len(stable_rois)}")
            plt.axis('off')
            plt.tight_layout()
            plt.show()
        
        # Сопоставление с именами полей (интерактивно или автоматически)
        hud_mapping = {}
        field_names = ["throttle", "pitch", "roll", "yaw", "battery", "flight_time"]
        
        print("\n📝 Сопоставление регионов с полями HUD:")
        print("Введите номер региона для каждого поля (или -1, если не найдено):")
        
        for field in field_names:
            default_roi = self.default_rois[field]
            dx = default_roi["x_rel"] * self.width
            dy = default_roi["y_rel"] * self.height
            
            # Ищем ближайший регион к ожидаемой позиции
            best_idx = -1
            min_dist = float('inf')
            
            for i, roi in enumerate(stable_rois):
                cx, cy = roi["x"] + roi["w"]/2, roi["y"] + roi["h"]/2
                dist = np.sqrt((cx - dx)**2 + (cy - dy)**2)
                if dist < min_dist:
                    min_dist = dist
                    best_idx = i
            
            # Если регион близко (< 100 пикселей), предлагаем его
            if min_dist < 150 and best_idx != -1:
                user_input = input(f"  {field} (ожидался около [{dx:.0f}, {dy:.0f}]): регион #{best_idx}? [Enter для подтверждения или введите номер]: ")
                if user_input.strip() == "":
                    hud_mapping[field] = stable_rois[best_idx]
                elif user_input.strip().isdigit():
                    idx = int(user_input)
                    if 0 <= idx < len(stable_rois):
                        hud_mapping[field] = stable_rois[idx]
            else:
                user_input = input(f"  {field}: введите номер региона (0-{len(stable_rois)-1}) или -1: ")
                if user_input.strip().isdigit():
                    idx = int(user_input)
                    if 0 <= idx < len(stable_rois):
                        hud_mapping[field] = stable_rois[idx]
        
        # Сохранение конфигурации
        config = {
            "video_source": self.video_path,
            "resolution": {"width": self.width, "height": self.height},
            "rois": hud_mapping
        }
        
        output_path = Path(output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"\n💾 Конфигурация сохранена в: {output_path}")
        return config

if __name__ == "__main__":
    import sys
    
    video_file = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/video_01.mp4"
    
    calibrator = ROICalibrator(video_file)
    config = calibrator.run_calibration(sample_frames=50)
    
    if config:
        print("\n✅ Калибровка завершена успешно!")
        print(json.dumps(config, indent=2))
