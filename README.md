# 🚀 ТВ-телеметрия Квадросима

Система автоматической телеметрии для симуляторов гоночных дронов. Снимает показатели HUD, распознает стики, пишет логи и строит аналитические отчёты.

## 📋 Требования к системе
- **ОС:** Windows 10/11
- **Python:** 3.10 или выше
- **Экран:** Разрешение 1920x1080 (рекомендуется)
- **Tesseract OCR:** Обязателен для распознавания цифр

---

## 🛠️ Установка зависимостей

### 1. Установка Tesseract OCR (КРИТИЧНО)
Без этого компонента система не сможет читать цифры с экрана.

1.  Скачайте установщик последней версии:
    *   [Скачать Tesseract для Windows (GitHub)](https://github.com/UB-Mannheim/tesseract/wiki)
    *   Рекомендую версию `tesseract-ocr-w64-setup-v5.x.x.exe`.
2.  Запустите установщик.
3.  **ВАЖНО:** При установке запомните путь. По умолчанию это:
    `C:\Program Files\Tesseract-OCR`
4.  **Добавление в PATH (Автоматически или вручную):**
    *   *Вариант А (Простой):* При установке поставьте галочку **"Add application directory to your PATH"**.
    *   *Вариант Б (Вручную):*
        1.  Нажмите `Win + R`, введите `sysdm.cpl`, нажмите Enter.
        2.  Вкладка "Дополнительно" -> кнопка "Переменные среды".
        3.  В блоке "Системные переменные" найдите строку `Path`, выберите её и нажмите "Изменить".
        4.  Нажмите "Создать" и добавьте путь: `C:\Program Files\Tesseract-OCR`.
        5.  Нажмите ОК во всех окнах.
5.  **Проверка установки:**
    Откройте командную строку (`cmd`) и введите:
    ```bash
    tesseract --version
    ```
    Если вы увидели номер версии — установка успешна. Если ошибка "не является внутренней командой" — повторите шаг 4.

### 2. Установка Python-библиотек
После установки Tesseract откройте терминал в папке проекта и выполните:

```bash
pip install -r requirements.txt
```

---

## ⚙️ Настройка и Калибровка

### Автоматическая калибровка
Система пытается автоматически определить зоны HUD, если разрешение вашего экрана совпадает с эталонным (1920x1080) и симулятор запущен в полноэкранном режиме.
Просто запустите программу. Если зоны определены верно — можно летать.

### Ручная калибровка через GUI (Рекомендуется)
Для удобной настройки зон используйте графический интерфейс:

```bash
python -m qt.capture.gui_calibrator
```

Откроется окно со скриншотом вашего экрана:
- Перетаскивайте цветные рамки мышью для точной настройки
- Включайте/выключайте зоны чекбоксами
- Нажмите "Сохранить config.json" когда закончите

### Консольная калибровка (альтернатива)
Если GUI не работает, используйте консольный режим:

```bash
python -m qt.capture.calibrate
```
Следуйте инструкциям на экране: выделите мышью области приборов. Конфигурация сохранится в `config.json`.

---

## 🏁 Запуск

### Вариант 1: Через лаунчер (рекомендуется)
Лаунчер автоматически проверит зависимости и предложит калибровку:

```bash
python launcher.py
```

**Ключи лаунчера:**
- `--help` - показать справку
- `--auto` - автоматический режим без вопросов
- `--skip-deps` - пропустить проверку зависимостей

### Вариант 2: Прямой запуск (для разработчиков)
```bash
python main.py
```

### Вариант 3: EXE-файл (для пользователей)
Создайте standalone EXE-файл:
```bash
python build_exe.py
```
Готовый файл появится в папке `dist/QuadrosimTelemetry.exe`.

---

После запуска:
1. Запустите симулятор.
2. Система начнет запись в фоне.
3. После завершения полёта (посадка/краш) в папке `reports` появится HTML-отчёт, который автоматически откроется в браузере.

## Возможности

- **Захват экрана**: 
  - DirectX Desktop Duplication (Windows, GPU-ускорение) через `dxcam`
  - Кроссплатформенный fallback через `mss`
  - Поддержка нескольких мониторов
  
- **OCR движок**:
  - Шаблонный движок (template matching) — быстрое распознавание цифр
  - Tesseract как бэкенд для кириллицы (имена пилотов) и fallback
  
- **Распознаваемые поля**:
  - Имя пилота (кириллица)
  - Дата/время
  - Заряд батареи (V, A)
  - Режим полёта (ACRO, HORIZON, ANGLE и др.)
  - Лимит времени
  - Скорость, высота
  - Круги (laps)
  - Текущее и лучшее время круга

- **Фильтрация данных**:
  - Медианный фильтр для стабильности показаний
  - RepeatFilter для игнорирования одиночных ошибок OCR

- **Хранение и отчёты**:
  - SQLite база данных с пакетной записью
  - Экспорт отчётов через Pandas/Plotly

## Установка

```bash
pip install -r requirements.txt
```

### Зависимости

- `numpy >= 1.24`
- `opencv-python >= 4.8`
- `mss >= 9.0`
- `dxcam >= 0.0.5` (только Windows)
- `pandas >= 2.0`
- `plotly >= 5.18`
- `pytesseract >= 0.3.10` (опционально, для Tesseract)

**Опционально**: Tesseract OCR для распознавания кириллицы:
- Установите Tesseract: https://github.com/tesseract-ocr/tesseract
- Добавьте в PATH или укажите путь в конфиге

## Конфигурация

Конфигурационный файл `config.json` (или путь через переменную окружения `QT_CONFIG`):

```json
{
  "capture": {
    "backend": "auto",      // "auto", "dxcam", "mss"
    "monitor": 0,           // индекс монитора
    "fps_target": 0         // целевой FPS захвата (0 = макс)
  },
  "screen": {
    "width": 1920,
    "height": 1080
  },
  "rois": {
    "pilot": [x, y, w, h],
    "battery": [x, y, w, h],
    ...
  },
  "sticks": {
    "left": {
      "center": [x, y],
      "radius_px": 65,
      "dot_rgb": [255, 255, 255],
      "dot_hsv_lo": [0, 0, 180],
      "dot_hsv_hi": [180, 80, 255]
    },
    "right": {...}
  },
  "ocr": {
    "engine": "template",   // "template" или "tesseract"
    "tess_cmd": "tesseract", // команда/путь к tesseract
    "hz_fast": 10.0,        // частота OCR при движении
    "hz_slow": 1.0,         // частота OCR в покое
    "median_window": 5,     // окно медианного фильтра
    "hold_last_valid_s": 1.0 // удержание последнего валидного значения
  },
  "events": {
    "crash_speed_drop_s": 0.3,
    "hud_lost_s": 2.0,
    "timer_stuck_s": 3.0
  },
  "report": {
    "sectors_n": 3,
    "out_dir": "reports"
  },
  "db": {
    "path": "telemetry.db",
    "batch_ms": 500
  }
}
```

### ROI (Region of Interest)

Области интереса можно задать вручную в конфиге или использовать авто-калибровку. Пример для разрешения 1920x1080:

```json
"rois": {
  "pilot": [0, 0, 471, 33],
  "datetime": [40, 39, 152, 21],
  "battery": [126, 66, 104, 32],
  "mode": [40, 107, 92, 30],
  "limit": [1816, 70, 38, 11],
  "speed": [107, 528, 81, 75],
  "alt": [1597, 556, 16, 23],
  "laps": [99, 1026, 36, 24],
  "cur_time": [263, 1027, 95, 21],
  "best_time": [1786, 1027, 95, 21]
}
```

## Использование

### Захват кадра

```python
from qt.capture.source import create_source
from qt.core.config import load_config

cfg = load_config()
source = create_source(cfg)
timestamp, frame = source.grab()
```

### Распознавание текста

**Шаблонный движок** (быстрый, для цифр):
```python
from qt.ocr.digits import TemplateEngine
from qt.ocr.preprocess import prepare
from qt.ocr.fields import FIELD_SPECS

engine = TemplateEngine()
# Обучение на эталоне
engine.train(preprocessed_crop, expected_text, kind="int")
# Распознавание
text, confidence = engine.recognize(preprocessed_crop, kind="int")
```

**Tesseract** (для кириллицы):
```python
from qt.ocr.engine import TesseractEngine

tess = TesseractEngine(cfg)
if tess.available():
    text, conf = tess.run(crop, spec={"kind": "pilot"})
```

### Парсинг значений

```python
from qt.ocr.fields import parse_value

# Время в секундах
parse_value("hms", "01:02:03.500")  # → 3723.5
parse_value("mmss", "02:49")        # → 169

# Батарея
parse_value("battery", "25,2V1,1A")  # → (25.2, 1.1)

# Круги
parse_value("laps", "1/3")  # → (1, 3)
```

### Фильтры

```python
from qt.ocr.filters import MedianFilter, RepeatFilter

# Медианный фильтр
mf = MedianFilter(window=5)
stable_value = mf.push(noisy_value, timestamp)

# Защита от одиночных ошибок OCR
rf = RepeatFilter()
value = rf.push(new_reading, timestamp)
```

## Тесты

```bash
pytest
```

Тесты используют эталонный скриншот `tests/fixtures/screen_01.png` и проверяют:
- 100% совпадение шаблонного OCR с эталоном
- Корректность парсинга значений
- Работу фильтров
- Интеграцию с Tesseract (если установлен)

## Структура проекта

```
qt/
├── __init__.py
├── capture/          # Захват экрана
│   ├── source.py     # DxCamSource, MssSource
│   ├── auto_rois.py  # Авто-определение ROI
│   └── roi.py        # Работа с областями
├── core/             # Базовые компоненты
│   ├── config.py     # Конфигурация
│   ├── frame.py      # Класс кадра
│   ├── io.py         # Ввод/вывод
│   └── queue.py      # Очереди
└── ocr/              # OCR и постобработка
    ├── engine.py     # Tesseract бэкенд
    ├── digits.py     # Шаблонный движок
    ├── preprocess.py # Предобработка изображений
    ├── fields.py     # Спецификации полей, парсинг
    └── filters.py    # Медианный и Repeat фильтры

tests/
├── fixtures/
│   └── screen_01.png  # Эталонный скриншот
└── test_fields.py     # Тесты OCR и парсинга
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `QT_CONFIG` | Путь к файлу конфигурации (по умолчанию `config.json`) |

## Лицензия

Проект использует следующие open-source библиотеки:
- numpy, opencv-python, pandas, plotly
- mss, dxcam (Windows)
- pytesseract + Tesseract OCR

## Примечания

- Для работы DxCam требуется Windows 8+ и поддержка Desktop Duplication API
- При exclusive fullscreen игра может выдавать чёрные кадры — используйте оконный режим или borderless window
- Точность OCR зависит от качества шрифта в HUD и контраста изображения
