#!/usr/bin/env python3
"""
Launcher для ТВ-телеметрия Квадросима.
Автоматически проверяет и устанавливает зависимости, затем запускает основную систему.
"""

import subprocess
import sys
import os
import json
from pathlib import Path

# Цвета для вывода
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(60)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")

def check_python_version():
    """Проверка версии Python"""
    print_header("ПРОВЕРКА PYTHON")
    
    required_version = (3, 10)
    current_version = sys.version_info[:2]
    
    if current_version >= required_version:
        print_success(f"Python {current_version[0]}.{current_version[1]} установлен")
        return True
    else:
        print_error(f"Требуется Python {'.'.join(map(str, required_version))} или выше")
        print_warning(f"У вас установлен Python {'.'.join(map(str, current_version))}")
        return False

def check_tesseract():
    """Проверка установки Tesseract OCR"""
    print_header("ПРОВЕРКА TESSERACT OCR")
    
    try:
        result = subprocess.run(
            ['tesseract', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print_success(f"Tesseract OCR установлен: {version_line}")
            return True
        else:
            raise subprocess.CalledProcessError(result.returncode, 'tesseract')
    except FileNotFoundError:
        print_error("Tesseract OCR не найден в системе")
        print_info("Инструкция по установке:")
        print("  1. Скачайте установщик: https://github.com/UB-Mannheim/tesseract/wiki")
        print("  2. Установите, отметив галочку 'Add to PATH'")
        print("  3. Перезапустите терминал")
        return False
    except subprocess.TimeoutExpired:
        print_error("Превышено время ожидания ответа от tesseract")
        return False

def install_requirements():
    """Установка Python-зависимостей из requirements.txt"""
    print_header("УСТАНОВКА ЗАВИСИМОСТЕЙ")
    
    req_file = Path(__file__).parent / 'requirements.txt'
    
    if not req_file.exists():
        print_error("Файл requirements.txt не найден")
        return False
    
    print_info("Обновление pip...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pip'], 
                   check=False, capture_output=True)
    
    print_info("Установка пакетов из requirements.txt...")
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-r', str(req_file)],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print_success("Все зависимости установлены")
        # Проверка установленных версий
        print_info("Проверка установленных версий...")
        subprocess.run([sys.executable, '-m', 'pip', 'list'], check=False)
        return True
    else:
        print_error("Ошибка при установке зависимостей")
        print(result.stderr)
        return False

def verify_installations():
    """Проверка критических импортов"""
    print_header("ПРОВЕРКА ИМПОРТОВ")
    
    critical_modules = [
        'numpy',
        'cv2',
        'pandas',
        'plotly',
        'dxcam',
        'mss'
    ]
    
    all_ok = True
    for module in critical_modules:
        try:
            __import__(module)
            print_success(f"{module} - OK")
        except ImportError as e:
            print_error(f"{module} - НЕ НАЙДЕН: {e}")
            all_ok = False
    
    # Проверка pytesseract отдельно
    try:
        import pytesseract
        print_success("pytesseract - OK")
    except ImportError:
        print_error("pytesseract - НЕ НАЙДЕН")
        all_ok = False
    
    return all_ok

def load_config():
    """Загрузка конфигурации"""
    print_header("ЗАГРУЗКА КОНФИГУРАЦИИ")
    
    config_path = Path(__file__).parent / 'config.json'
    
    if not config_path.exists():
        print_warning("config.json не найден. Будет создана конфигурация по умолчанию.")
        return None
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        print_success("Конфигурация загружена успешно")
        
        # Проверка наличия ROI
        if 'rois' in config and len(config['rois']) > 0:
            print_success(f"Найдено {len(config['rois'])} зон интереса (ROI)")
        else:
            print_warning("Зоны интереса (ROI) не настроены. Потребуется калибровка.")
        
        return config
    except json.JSONDecodeError as e:
        print_error(f"Ошибка чтения config.json: {e}")
        return None

def run_calibration():
    """Предложение запустить калибровку"""
    print_header("КАЛИБРОВКА")
    
    print_info("Рекомендуется выполнить калибровку перед первым запуском.")
    print("Хотите запустить калибровку сейчас?")
    print("  y - Да, запустить калибровку")
    print("  n - Нет, пропустить (можно запустить позже)")
    print("  a - Автоматическая калибровка (если поддерживается)")
    
    choice = input("\nВаш выбор [y/n/a]: ").strip().lower()
    
    if choice == 'y':
        print_info("Запуск ручной калибровки...")
        subprocess.run([sys.executable, '-m', 'qt.capture.calibrate'])
        return True
    elif choice == 'a':
        print_info("Запуск автоматической калибровки...")
        try:
            from qt.capture.auto_rois import auto_calibrate
            if auto_calibrate():
                print_success("Автоматическая калибровка завершена")
                return True
            else:
                print_warning("Автоматическая калибровка не удалась")
        except Exception as e:
            print_error(f"Ошибка автоматической калибровки: {e}")
        return False
    else:
        print_info("Калибровка пропущена")
        return False

def run_main_app():
    """Запуск основного приложения"""
    print_header("ЗАПУСК ПРИЛОЖЕНИЯ")
    
    print_success("Все проверки пройдены!")
    print_info("Запуск main.py...")
    print("-" * 60)
    
    # Запуск main.py с передачей аргументов
    main_script = Path(__file__).parent / 'main.py'
    
    if not main_script.exists():
        print_error("main.py не найден")
        return False
    
    try:
        subprocess.run([sys.executable, str(main_script)], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Приложение завершилось с ошибкой: {e}")
        return False
    except KeyboardInterrupt:
        print_info("\nПриложение остановлено пользователем")
        return True

def main():
    """Основная функция лаунчера"""
    print_header("🚀 ТВ-ТЕЛЕМЕТРИЯ КВАДРОСИМА - ЛАУНЧЕР")
    print_info("Система автоматической проверки и запуска")
    
    # Проверка аргументов командной строки
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("\nИспользование:")
        print("  python launcher.py           - Интерактивный режим с проверками")
        print("  python launcher.py --help    - Показать эту справку")
        print("  python launcher.py --skip-deps - Пропустить проверку зависимостей")
        print("  python launcher.py --auto    - Автоматический режим без вопросов")
        sys.exit(0)
    
    auto_mode = '--auto' in sys.argv
    skip_deps = '--skip-deps' in sys.argv
    
    # Шаг 1: Проверка Python
    if not check_python_version():
        print_error("Необходимо обновить Python до версии 3.10+")
        sys.exit(1)
    
    # Шаг 2: Проверка Tesseract
    tesseract_ok = check_tesseract()
    if not tesseract_ok:
        print_warning("Без Tesseract OCR распознавание текста не будет работать")
        if not auto_mode:
            cont = input("Продолжить без Tesseract? [y/n]: ").strip().lower()
            if cont != 'y':
                sys.exit(1)
    
    # Шаг 3: Установка зависимостей
    if not skip_deps and not auto_mode:
        print("\nХотите проверить и установить зависимости?")
        print("  y - Да, проверить и установить при необходимости")
        print("  n - Нет, пропустить (если уверены, что всё установлено)")
        
        choice = input("\nВаш выбор [y/n]: ").strip().lower()
        
        if choice == 'y':
            if not install_requirements():
                print_error("Не удалось установить зависимости")
                sys.exit(1)
            
            if not verify_installations():
                print_warning("Некоторые модули не найдены. Попробуйте переустановить зависимости.")
                cont = input("Продолжить? [y/n]: ").strip().lower()
                if cont != 'y':
                    sys.exit(1)
    elif skip_deps or auto_mode:
        print_info("Проверка зависимостей пропущена")
        if not verify_installations():
            if auto_mode:
                print_warning("Некоторые модули не найдены, но продолжаем в автоматическом режиме")
            else:
                print_warning("Некоторые модули не найдены.")
                cont = input("Продолжить? [y/n]: ").strip().lower()
                if cont != 'y':
                    sys.exit(1)
    
    # Шаг 4: Загрузка конфигурации
    config = load_config()
    
    # Шаг 5: Калибровка (если нет конфига или ROI)
    needs_calibration = (config is None or 
                         'rois' not in config or 
                         len(config.get('rois', {})) == 0)
    
    if needs_calibration:
        print_warning("Конфигурация ROI отсутствует")
        if auto_mode:
            print_info("Автоматический режим: попытка авто-калибровки...")
            run_calibration()
        else:
            run_calibration()
    
    # Шаг 6: Запуск приложения
    if run_main_app():
        print_header("✅ РАБОТА ЗАВЕРШЕНА")
        print_info("Отчёт сохранён в папке reports/")
    else:
        print_header("❌ ПРОИЗОШЛА ОШИБКА")
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nℹ Лаунчер остановлен пользователем")
        sys.exit(0)
    except Exception as e:
        print_error(f"Неожиданная ошибка: {e}")
        sys.exit(1)
