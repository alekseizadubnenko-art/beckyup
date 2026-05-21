import logging
import os
from pathlib import Path

def setup_logger(name="backup_tool"):
    """Настройка логгера приложения"""
    logger = logging.getLogger(name)

    # Предотвращаемduplicate обработчики
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Обработчик для файла
    log_dir = Path.home() / ".backup_tool" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(
        log_dir / "backup.log",
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

def get_logger(name=None):
    """Получить логгер для модуля"""
    if name:
        return logging.getLogger(f"backup_tool.{name}")
    return logging.getLogger("backup_tool")