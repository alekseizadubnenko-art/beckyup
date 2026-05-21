#!/usr/bin/env python3
"""
Экстренный бэкап важных данных
Главный модуль приложения
"""

import sys
import logging
import signal
import argparse
from core.backup_engine import BackupEngine
from core.device_monitor import DeviceMonitor
from config.manager import ConfigManager
from utils.logger import setup_logger

# Глобальные переменные для корректного завершения
backup_engine = None
device_monitor = None
config_manager = None

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    print("\nПолучен сигнал завершения. Останавливаем приложение...")
    shutdown()
    sys.exit(0)

def shutdown():
    """Корректное завершение работы приложения"""
    global device_monitor
    if device_monitor:
        device_monitor.stop_monitoring()
    print("Приложение остановлено.")

def main():
    """Главная функция приложения"""
    global backup_engine, device_monitor, config_manager

    # Настройка обработчика сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description="Экстренный бэкап важных данных")
    parser.add_argument("--source", help="Исходная директория для одноразового бэкапа")
    parser.add_argument("--destination", help="Директория назначения для одноразового бэкапа")
    parser.add_argument("--config", help="Путь к файлу конфигурации", default=None)
    args = parser.parse_args()

    # Настройка логирования
    logger = setup_logger()
    logger.info("Запуск экстренного бэкапа важных данных")

    try:
        # Если указаны source и destination, выполняем одноразовый бэкап
        if args.source and args.destination:
            logger.info("Запуск одноразового бэкапа")
            # Инициализация движка бэкапа
            backup_engine = BackupEngine(args.config)
            # Переопределяем источник и назначение из аргументов командной строки
            backup_engine.source_directories = [args.source]
            backup_engine.destination_path = args.destination
            # Запускаем бэкап
            stats = backup_engine.run_backup()
            print("Одноразовый бэкап завершен:")
            print(f"  Источник: {args.source}")
            print(f"  Назначение: {args.destination}")
            print(f"  Скопировано файлов: {stats.get('total_copied', 0)}")
            print(f"  Пропущено файлов: {stats.get('total_skipped', 0)}")
            print(f"  Ошибок: {stats.get('total_errors', 0)}")
            logger.info(f"Одноразовый бэкап завершен: {stats}")
            return

        # Иначе запускаем в режиме мониторинга устройств
        # Инициализация менеджера конфигурации
        config_manager = ConfigManager()
        logger.info("Менеджер конфигурации инициализирован")

        # Инициализация компонентов
        backup_engine = BackupEngine(args.config)
        device_monitor = DeviceMonitor(backup_engine)

        # Добавляем callback для оповещения о подключении устройств
        def on_device_connected(device_path):
            logger.info(f"Обнаружено новое устройство: {device_path}")
            # Можно добавить дополнительную логику здесь, например, уведомление пользователя

        device_monitor.add_callback(on_device_connected)

        # Запуск мониторинга устройств
        device_monitor.start_monitoring()

        logger.info("Приложение запущено и готово к работе")
        print("Экстренный бэкап запущен. Нажмите Ctrl+C для выхода.")
        print(f"Конфигурация загружена из: {config_manager.config_file if config_manager else 'default'}")

        # Основной цикл приложения
        try:
            while True:
                # Можно добавить периодические проверки или просто ждать сигнала
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки от пользователя")
        finally:
            shutdown()

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
