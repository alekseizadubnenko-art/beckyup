import time
import threading
from pathlib import Path
from typing import List, Callable
from utils.logger import get_logger

class DeviceMonitor:
    def __init__(self, backup_engine, detector=None, check_interval: int = 5):
        self.logger = get_logger("device_monitor")
        self.backup_engine = backup_engine
        self.detector = detector
        self.check_interval = check_interval
        self.running = False
        self.monitor_thread = None
        self.known_devices: set = set()
        self.callbacks: List[Callable] = []

    def add_callback(self, callback: Callable):
        """Добавление callback функции для вызова при обнаружении нового устройства"""
        self.callbacks.append(callback)

    def _check_for_new_devices(self):
        try:
            current_devices = self.detector.get_mounted_devices()
            current_uuids = {d[2] for d in current_devices}
            known_uuids = {d[2] for d in self.known_devices}
            new_uuids = current_uuids - known_uuids

            for mount_path, label, uuid in current_devices:
                if uuid in new_uuids:
                    known_drives = self.backup_engine.config.get("backup", {}).get("known_drive_uuids", {})
                    if known_drives.get(uuid):
                        self._on_device_connected(mount_path, label, uuid)
                    else:
                        self.logger.info(f"Неизвестное устройство: {label} — игнорируем")

            lost_uuids = known_uuids - current_uuids
            if lost_uuids:
                self.logger.info(f"Устройства отсоединены: {lost_uuids}")
            self.known_devices = current_devices
        except Exception as e:
            self.logger.error(f"Ошибка при проверке устройств: {e}")

    def _on_device_connected(self, device_path: str, device_label: str = "", device_uuid: str = ""):
        """Обработчик подключения нового устройства"""
        self.logger.info(f"Устройство подключено: {device_path}")

        auth_mode = self.backup_engine.config.get("backup", {}).get("auth_mode", "none")
        auth_hash = self.backup_engine.config.get("backup", {}).get("auth_hash", "")
        auto_confirm = self.backup_engine.config.get("monitoring", {}).get("auto_confirm", False)

        should_backup = False
        if auth_mode == "none" and auto_confirm:
            should_backup = True
            self.logger.info("Автоматический бэкап запущен...")
        else:
            from utils.auth import confirm_backup
            sources = self.backup_engine.config.get("backup", {}).get("source_directories", [])
            summary = "; ".join(str(s) for s in sources[:3])
            if len(sources) > 3:
                summary += f" и ещё {len(sources) - 3}"
            confirmed = confirm_backup(device_label or device_path, summary or "—", auth_mode, auth_hash)
            if confirmed:
                should_backup = True
                self.logger.info("Бэкап подтверждён пользователем")

        if should_backup:
            self.backup_engine.run_backup()

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