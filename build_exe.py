#!/usr/bin/env python3
"""
Скрипт для создания standalone EXE-файла приложения.
Использует PyInstaller для упаковки всех зависимостей в один исполняемый файл.
"""

import subprocess
import sys
import os
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

def check_pyinstaller():
    """Проверка установки PyInstaller"""
    print_header("ПРОВЕРКА PYINSTALLER")
    
    try:
        import PyInstaller
        print_success(f"PyInstaller {PyInstaller.__version__} установлен")
        return True
    except ImportError:
        print_warning("PyInstaller не найден. Устанавливаю...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'pyinstaller'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            import PyInstaller
            print_success(f"PyInstaller {PyInstaller.__version__} установлен")
            return True
        else:
            print_error("Не удалось установить PyInstaller")
            print(result.stderr)
            return False

def create_exe():
    """Создание EXE файла"""
    print_header("СОЗДАНИЕ EXE ФАЙЛА")
    
    project_root = Path(__file__).parent
    launcher_script = project_root / 'launcher.py'
    
    if not launcher_script.exists():
        print_error("launcher.py не найден")
        return False
    
    # Параметры для PyInstaller
    pyinstaller_args = [
        str(launcher_script),
        '--onefile',              # Один файл
        '--windowed',             # Без консоли (для GUI)
        '--name', 'QuadrosimTelemetry',
        '--icon', str(project_root / 'assets' / 'app_icon.png') if (project_root / 'assets' / 'app_icon.png').exists() else 'NONE',         # Можно указать путь к .ico файлу
        '--add-data', 'config.json;.',
        '--add-data', 'schema.sql;.',
        '--hidden-import', 'PIL.ImageTk',
        '--hidden-import', 'qt',
        '--hidden-import', 'qt.capture',
        '--hidden-import', 'qt.ocr',
        '--hidden-import', 'qt.sticks',
        '--hidden-import', 'qt.logger',
        '--hidden-import', 'qt.events',
        '--hidden-import', 'qt.analysis',
        '--hidden-import', 'qt.report',
        '--hidden-import', 'numpy',
        '--hidden-import', 'cv2',
        '--hidden-import', 'pandas',
        '--hidden-import', 'plotly',
        '--hidden-import', 'dxcam',
        '--hidden-import', 'mss',
        '--hidden-import', 'pytesseract',
        '--collect-all', 'plotly',
        '--collect-all', 'pandas',
        '--noconfirm',
    ]
    
    # Добавляем данные из папки qt если она существует
    qt_dir = project_root / 'qt'
    if qt_dir.exists():
        pyinstaller_args.extend(['--add-data', f'{qt_dir};qt'])
    
    print_info("Запуск PyInstaller...")
    print(f"Команда: pyinstaller {' '.join(pyinstaller_args)}")
    
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller'] + pyinstaller_args,
        cwd=str(project_root)
    )
    
    if result.returncode == 0:
        dist_folder = project_root / 'dist'
        exe_path = dist_folder / 'QuadrosimTelemetry.exe'
        
        if exe_path.exists():
            print_success(f"EXE файл создан: {exe_path}")
            print_info(f"Размер файла: {exe_path.stat().st_size / (1024*1024):.1f} MB")
            print("\n" + "="*60)
            print("ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ:")
            print("="*60)
            print(f"1. Скопируйте '{exe_path.name}' в удобную папку")
            print("2. При первом запуске программа автоматически:")
            print("   - Проверит наличие Tesseract OCR")
            print("   - Проверит и установит зависимости")
            print("   - Предложит выполнить калибровку")
            print("3. Запустите симулятор и используйте телеметрию")
            print("="*60)
            return True
        else:
            print_error("EXE файл не найден в папке dist/")
            return False
    else:
        print_error("Ошибка при создании EXE файла")
        return False

def cleanup_build_files():
    """Удаление временных файлов сборки"""
    print_header("ОЧИСТКА ВРЕМЕННЫХ ФАЙЛОВ")
    
    project_root = Path(__file__).parent
    dirs_to_remove = ['build', 'dist', '__pycache__']
    
    for dir_name in dirs_to_remove:
        dir_path = project_root / dir_name
        if dir_path.exists():
            try:
                import shutil
                shutil.rmtree(dir_path)
                print_success(f"Удалена папка: {dir_name}")
            except Exception as e:
                print_warning(f"Не удалось удалить {dir_name}: {e}")
    
    # Удаление spec файла
    spec_file = project_root / 'QuadrosimTelemetry.spec'
    if spec_file.exists():
        try:
            spec_file.unlink()
            print_success("Удален spec файл")
        except Exception as e:
            print_warning(f"Не удалось удалить spec файл: {e}")

def main():
    """Основная функция"""
    print_header("📦 ГЕНЕРАТОР EXE - ТВ-ТЕЛЕМЕТРИЯ КВАДРОСИМА")
    
    # Шаг 1: Проверка PyInstaller
    if not check_pyinstaller():
        print_error("Требуется PyInstaller для создания EXE")
        sys.exit(1)
    
    # Шаг 2: Создание EXE
    if not create_exe():
        print_error("Не удалось создать EXE файл")
        sys.exit(1)
    
    # Шаг 3: Очистка (опционально)
    print("\nХотите удалить временные файлы сборки?")
    print("  y - Да, удалить")
    print("  n - Нет, оставить (полезно для отладки)")
    
    choice = input("\nВаш выбор [y/n]: ").strip().lower()
    if choice == 'y':
        cleanup_build_files()
    
    print_header("✅ ГОТОВО")
    print_info("EXE файл готов к использованию!")
    print("Он находится в папке 'dist/' в корне проекта.")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nℹ Процесс остановлен пользователем")
        sys.exit(0)
    except Exception as e:
        print_error(f"Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
