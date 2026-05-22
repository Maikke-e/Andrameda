"""
Модуль для работы с текстовыми документами на рабочем столе.
Поддерживает Windows, macOS и Linux.
"""

import os
import platform
import subprocess
from pathlib import Path
from typing import Optional
from enum import Enum


class FileAction(Enum):
    """Действия с файлом."""
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"


class FileManagerError(Exception):
    """Базовое исключение для ошибок менеджера файлов."""
    pass


class FileNotFoundError(FileManagerError):
    """Файл не найден."""
    pass


class InvalidFileNameError(FileManagerError):
    """Некорректное имя файла."""
    pass


class PermissionError(FileManagerError):
    """Ошибка прав доступа."""
    pass


def get_desktop_path() -> Path:
    """
    Определяет путь к рабочему столу в зависимости от ОС.
    
    Returns:
        Path: Путь к рабочему столу
    """
    system = platform.system()
    
    if system == "Windows":
        # На Windows используем переменную окружения USERPROFILE
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            return Path(user_profile) / "Desktop"
        # Альтернативный способ через HOMEDRIVE и HOMEPATH
        homedrive = os.environ.get("HOMEDRIVE", "C:")
        homepath = os.environ.get("HOMEPATH", "\\Users\\Public")
        return Path(homedrive) / homepath / "Desktop"
    
    elif system == "Darwin":
        # На macOS используем переменную окружения HOME
        home = os.environ.get("HOME")
        if home:
            return Path(home) / "Desktop"
        return Path.home() / "Desktop"
    
    else:
        # На Linux и других Unix-подобных системах
        home = os.environ.get("HOME")
        if home:
            desktop = Path(home) / "Desktop"
            if desktop.exists():
                return desktop
        # Альтернативные варианты для Linux
        xdg_desktop = os.environ.get("XDG_DESKTOP_DIR")
        if xdg_desktop:
            return Path(xdg_desktop)
        return Path.home() / "Desktop"


def validate_filename(filename: str) -> str:
    """
    Проверяет корректность имени файла.
    
    Args:
        filename: Имя файла для проверки
        
    Returns:
        str: Очищенное имя файла
        
    Raises:
        InvalidFileNameError: Если имя файла некорректно
    """
    if not filename or not filename.strip():
        raise InvalidFileNameError("Имя файла не может быть пустым")
    
    # Удаляем лишние пробелы
    filename = filename.strip()
    
    # Проверяем на недопустимые символы
    invalid_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
    for char in invalid_chars:
        if char in filename:
            raise InvalidFileNameError(
                f"Имя файла содержит недопустимый символ: '{char}'"
            )
    
    # Проверяем на зарезервированные имена Windows
    reserved_names = [
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    ]
    name_without_ext = Path(filename).stem.upper()
    if name_without_ext in reserved_names:
        raise InvalidFileNameError(
            f"Имя файла '{filename}' является зарезервированным"
        )
    
    # Проверяем длину имени
    if len(filename) > 255:
        raise InvalidFileNameError("Имя файла слишком длинное (максимум 255 символов)")
    
    return filename


def open_in_editor(filepath: Path) -> bool:
    """
    Открывает файл в текстовом редакторе по умолчанию.
    
    Args:
        filepath: Путь к файлу
        
    Returns:
        bool: True если файл успешно открыт
    """
    system = platform.system()
    
    try:
        if system == "Windows":
            # Используем notepad по умолчанию
            os.startfile(str(filepath))
            return True
        
        elif system == "Darwin":
            # На macOS открываем в TextEdit
            subprocess.run(["open", "-t", str(filepath)], check=True)
            return True
        
        else:
            # На Linux пытаемся открыть в gedit, nano или vim
            editors = ["gedit", "kate", "mousepad", "nano", "vim"]
            for editor in editors:
                try:
                    subprocess.Popen([editor, str(filepath)])
                    return True
                except FileNotFoundError:
                    continue
            
            # Если не нашли редактор, используем xdg-open
            subprocess.run(["xdg-open", str(filepath)], check=True)
            return True
    
    except Exception as e:
        print(f"Не удалось открыть файл в редакторе: {e}")
        return False


def manage_desktop_file(
    filename: str,
    content: Optional[str] = None,
    action: FileAction = FileAction.CREATE
) -> dict:
    """
    Управляет текстовыми документами на рабочем столе.
    
    Args:
        filename: Имя файла (строка)
        content: Содержимое файла (строка, опционально)
        action: Действие (создание, редактирование, удаление)
        
    Returns:
        dict: Результат операции с ключами:
            - success: bool - успешность операции
            - message: str - сообщение о результате
            - filepath: str - путь к файлу (если применимо)
            
    Raises:
        FileNotFoundError: Файл не найден (при редактировании или удалении)
        InvalidFileNameError: Некорректное имя файла
        PermissionError: Ошибка прав доступа
    """
    result = {
        "success": False,
        "message": "",
        "filepath": None
    }
    
    try:
        # Получаем путь к рабочему столу
        desktop_path = get_desktop_path()
        
        # Проверяем, существует ли рабочий стол
        if not desktop_path.exists():
            raise PermissionError(
                f"Не удалось определить путь к рабочему столу: {desktop_path}"
            )
        
        # Валидируем имя файла
        safe_filename = validate_filename(filename)
        
        # Добавляем расширение .txt если его нет
        if not safe_filename.lower().endswith('.txt'):
            safe_filename += '.txt'
        
        filepath = desktop_path / safe_filename
        result["filepath"] = str(filepath)
        
        if action == FileAction.CREATE:
            # Создаём/обновляем файл
            # Проверяем права на запись
            if not os.access(desktop_path, os.W_OK):
                raise PermissionError(
                    f"Нет прав на запись в директорию: {desktop_path}"
                )
            
            # Создаём или обновляем файл с содержимым
            with open(filepath, 'w', encoding='utf-8') as f:
                if content:
                    f.write(content)
            
            if filepath.exists() and not content:
                # Файл уже существовал и не передавалось содержимое
                result["message"] = f"Файл уже существует: {safe_filename}"
            else:
                result["message"] = f"Файл успешно создан: {safe_filename}"
            
            result["success"] = True
            
            # Автоматически открываем в редакторе только если нет содержимого
            # (чтобы не мешать при записи через бота)
            if not content:
                if open_in_editor(filepath):
                    result["message"] += " и открыт в редакторе"
                else:
                    result["message"] += ", но не удалось открыть в редакторе"
        
        elif action == FileAction.EDIT:
            # Редактирование файла
            if not filepath.exists():
                raise FileNotFoundError(f"Файл не найден: {safe_filename}")
            
            # Если передано новое содержимое, просто обновляем файл
            if content is not None:
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                    result["message"] = f"Файл успешно обновлён: {safe_filename}"
                    result["success"] = True
                except Exception as e:
                    raise PermissionError(f"Нет прав на редактирование файла: {safe_filename}")
            else:
                # Открываем для ручного редактирования
                if open_in_editor(filepath):
                    result["message"] = f"Файл открыт для редактирования: {safe_filename}"
                else:
                    result["message"] = f"Файл готов к редактированию: {safe_filename}"
                result["success"] = True
        
        elif action == FileAction.DELETE:
            # Удаление файла
            if not filepath.exists():
                raise FileNotFoundError(f"Файл не найден: {safe_filename}")
            
            # Проверяем права на удаление
            if not os.access(filepath, os.W_OK):
                raise PermissionError(f"Нет прав на удаление файла: {safe_filename}")
            
            filepath.unlink()
            result["message"] = f"Файл успешно удалён: {safe_filename}"
            result["success"] = True
        
        else:
            raise ValueError(f"Неизвестное действие: {action}")
    
    except FileManagerError as e:
        result["message"] = str(e)
        result["success"] = False
    except Exception as e:
        result["message"] = f"Произошла ошибка: {e}"
        result["success"] = False
    
    return result


# Удобные функции-обёртки
def create_desktop_file(filename: str, content: Optional[str] = None) -> dict:
    """Создаёт текстовый файл на рабочем столе."""
    return manage_desktop_file(filename, content, FileAction.CREATE)


def edit_desktop_file(filename: str, content: Optional[str] = None) -> dict:
    """Редактирует текстовый файл на рабочем столе."""
    return manage_desktop_file(filename, content, FileAction.EDIT)


def delete_desktop_file(filename: str) -> dict:
    """Удаляет текстовый файл с рабочего стола."""
    return manage_desktop_file(filename, None, FileAction.DELETE)


if __name__ == "__main__":
    # Примеры использования
    print("=== Тестирование файлового менеджера ===\n")
    
    # Создание файла
    result = create_desktop_file("test_document", "Привет, мир!")
    print(f"Создание: {result}\n")
    
    # Редактирование файла
    result = edit_desktop_file("test_document", "Обновлённое содержимое")
    print(f"Редактирование: {result}\n")
    
    # Удаление файла
    result = delete_desktop_file("test_document")
    print(f"Удаление: {result}\n")