import time
import threading
from pathlib import Path
from typing import List, Callable
from utils.logger import get_logger

class DeviceMonitor:
    def __init__(self, backup_engine, check_interval: int = 5):
        self.logger = get_logger("device_monitor")
        self.backup_engine = backup_engine
        self.check_interval = check_interval
        self.running = False
        self.monitor_thread = None
        self.known_devices: set = set()
        self.callbacks: List[Callable] = []

    def add_callback(self, callback: Callable):
        """Добавление callback функции для вызова при обнаружении нового устройства"""
        self.callbacks.append(callback)

    def _get_connected_devices(self) -> set:
        """
        Получение списка подключенных внешних устройств
        Это упрощенная реализация - в реальном приложении потребуется
        platform-specific код для мониторинга USB устройств
        """
        # В реальном приложении здесь должен быть код для:
        # - Windows: использование WMI или pywin32
        # - Linux: мониторинг /dev через udev или udisks2
        # - macOS: использование IOKit или FSEvents

        # Для демонстрации возвращаем пустое множество
        # В будущих версиях нужно будет реализовать реальное определение устройств
        return set()

    def _check_for_new_devices(self):
        """Проверка на наличие новых подключенных устройств"""
        try:
            current_devices = self._get_connected_devices()
            new_devices = current_devices - self.known_devices

            if new_devices:
                self.logger.info(f"Обнаружены новые устройства: {new_devices}")
                for device in new_devices:
                    self._on_device_connected(device)

            # Проверяем отсоединенные устройства (опционально)
            disconnected_devices = self.known_devices - current_devices
            if disconnected_devices:
                self.logger.info(f"Устройства отсоединены: {disconnected_devices}")
                for device in disconnected_devices:
                    self._on_device_disconnected(device)

            self.known_devices = current_devices

        except Exception as e:
            self.logger.error(f"Ошибка при проверке устройств: {e}")

    def _on_device_connected(self, device_path: str):
        """Обработчик подключения нового устройства"""
        self.logger.info(f"Устройство подключено: {device_path}")

        # Выполняем бэкап если настроено автоподтверждение
        if self.backup_engine.config.get("monitoring", {}).get("auto_confirm", False):
            self.logger.info("Автоматический бэкап запущен...")
            self.backup_engine.run_backup()
        else:
            self.logger.info("Для запуска бэкапа требуется подтверждение пользователя")

        # Вызываем зарегистрированные callbacks
        for callback in self.callbacks:
            try:
                callback(device_path)
            except Exception as e:
                self.logger.error(f"Ошибка в callback: {e}")

    def _on_device_disconnected(self, device_path: str):
        """Обработчик отсоединения устройства"""
        self.logger.info(f"Устройство отсоединено: {device_path}")

    def start_monitoring(self):
        """Запуск мониторинга устройств в отдельном потоке"""
        if self.running:
            self.logger.warning("Мониторинг уже запущен")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.logger.info(f"Мониторинг устройств запущен (интервал: {self.check_interval}s)")

    def stop_monitoring(self):
        """Остановка мониторинга устройств"""
        if not self.running:
            self.logger.warning("Мониторинг не запущен")
            return

        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        self.logger.info("Мониторинг устройств остановлен")

    def _monitor_loop(self):
        """Основной цикл мониторинга"""
        while self.running:
            self._check_for_new_devices()
            time.sleep(self.check_interval)