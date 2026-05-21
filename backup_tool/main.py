#!/usr/bin/env python3
"""
Экстренный бэкап важных данных
Главный модуль приложения
"""

import sys
import signal
import argparse
from pathlib import Path
from core.backup_engine import BackupEngine
from core.device_monitor import DeviceMonitor
from config.manager import ConfigManager
from utils.logger import setup_logger
from utils.ui import show_banner, show_startup, show_backup_result, print_error, console

# Глобальные переменные для корректного завершения
backup_engine = None
device_monitor = None
config_manager = None

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    print_error("\nПолучен сигнал завершения.")
    shutdown()
    sys.exit(0)

def shutdown():
    """Корректное завершение работы приложения"""
    global device_monitor
    if device_monitor:
        device_monitor.stop_monitoring()
    console.print("[dim]Приложение остановлено.[/dim]")

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
    parser.add_argument("--wizard", action="store_true", help="Запустить настройку заново")
    args = parser.parse_args()

    # Настройка логирования
    logger = setup_logger()
    logger.info("Запуск экстренного бэкапа важных данных")

    try:
        # Если указаны source и destination, выполняем одноразовый бэкап
        if args.source and args.destination:
            logger.info("Запуск одноразового бэкапа")
            show_banner()
            backup_engine = BackupEngine(args.config)
            dest = Path(args.destination)
            dest.mkdir(parents=True, exist_ok=True)
            backup_engine.source_directories = [Path(args.source)]
            backup_engine.destination_path = dest
            stats = backup_engine.run_backup()
            console.print(f"[bold]Источник:[/bold] {args.source}")
            console.print(f"[bold]Назначение:[/bold] {args.destination}")
            show_backup_result(stats)
            logger.info(f"Одноразовый бэкап завершен: {stats}")
            return

        # Инициализация конфигурации для режима мониторинга
        config_manager = ConfigManager()

        # Запуск визарда при первом запуске или по флагу --wizard
        if args.wizard or not config_manager.config_file.exists():
            try:
                from cli.wizard import run_wizard
                backup_engine = BackupEngine(args.config)
                run_wizard(config_manager, backup_engine)
            except ImportError:
                logger.error("questionary не установлен. Выполни: pip install -r requirements.txt")
                sys.exit(1)
            if args.wizard:
                return

        # Режим мониторинга устройств
        logger.info("Запуск в режиме мониторинга")
        backup_engine = BackupEngine(args.config)
        from core.device_detector import DeviceDetector
        detector = DeviceDetector()
        device_monitor = DeviceMonitor(backup_engine, detector=detector)

        def on_device_connected(device_path):
            logger.info(f"Обнаружено новое устройство: {device_path}")

        device_monitor.add_callback(on_device_connected)
        device_monitor.start_monitoring()

        logger.info("Приложение запущено и готово к работе")
        show_startup(str(config_manager.config_file) if config_manager else None)

        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки от пользователя")
        finally:
            shutdown()

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        print_error(f"Критическая ошибка: {e}")
        shutdown()
        sys.exit(1)

if __name__ == "__main__":
    main()
