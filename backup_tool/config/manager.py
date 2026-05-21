import json
import os
from pathlib import Path
from typing import Dict, Any
from utils.logger import get_logger

class ConfigManager:
    def __init__(self, app_name: str = "backup_tool"):
        self.logger = get_logger("config_manager")
        self.app_name = app_name
        self.config_dir = self._get_config_dir()
        self.config_file = self.config_dir / "config.json"
        self.default_config_file = Path(__file__).parent / "default_config.json"
        self.config: Dict[str, Any] = {}
        self._load_config()

    def _get_config_dir(self) -> Path:
        """Получить директорию конфигурации для текущей ОС"""
        if os.name == 'nt':  # Windows
            base_dir = os.getenv('APPDATA', os.path.expanduser('~'))
        elif os.name == 'posix':  # macOS and Linux
            base_dir = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        else:
            base_dir = os.path.expanduser('~')

        config_dir = Path(base_dir) / self.app_name
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    def _load_config(self):
        """Загрузка конфигурации из файла"""
        # Сначала пробуем загрузить пользовательскую конфигурацию
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                self.logger.info(f"Конфигурация загружена из {self.config_file}")
                return
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"Не удалось загрузить пользовательскую конфигурацию: {e}")

        # Если пользовательская конфигурация не найдена или повреждена, загружаем значение по умолчанию
        try:
            with open(self.default_config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.logger.info(f"Конфигурация загружена из значения по умолчанию: {self.default_config_file}")
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"Не удалось загрузить конфигурацию по умолчанию: {e}")
            self.config = self._get_hardcoded_defaults()

    def _get_hardcoded_defaults(self) -> Dict[str, Any]:
        """Жестко запрограммированные значения по умолчанию на случай если не удается загрузить файл"""
        return {
            "backup": {
                "source_directories": [],
                "destination_path": "",
                "known_drive_uuids": {},
                "auth_mode": "none",
                "auth_hash": "",
                "file_extensions": ["*"],
                "exclude_patterns": ["*.tmp", "*.temp", "~*"],
                "max_file_size_mb": 100,
                "verify_after_copy": True
            },
            "monitoring": {
                "check_interval_seconds": 5,
                "auto_confirm": False,
                "notify_on_backup": True
            },
            "logging": {
                "level": "INFO",
                "file": "backup.log",
                "max_size_mb": 10,
                "backup_count": 5
            }
        }

    def save_config(self):
        """Сохранение текущей конфигурации в файл"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Конфигурация сохранена в {self.config_file}")
        except IOError as e:
            self.logger.error(f"Не удалось сохранить конфигурацию: {e}")

    def get(self, key_path: str, default=None):
        """
        Получение значения конфигурации по пути (например, 'backup.source_directories')
        """
        keys = key_path.split('.')
        value = self.config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key_path: str, value):
        """
        Установка значения конфигурации по пути
        """
        keys = key_path.split('.')
        config = self.config
        try:
            # Переходим к предковому словарю
            for key in keys[:-1]:
                if key not in config:
                    config[key] = {}
                config = config[key]
            # Устанавливаем значение
            config[keys[-1]] = value
        except (KeyError, TypeError) as e:
            self.logger.error(f"Не удалось установить значение для {key_path}: {e}")

    def get_backup_sources(self) -> list:
        """Получить список исходных директорий для бэкапа"""
        return self.get('backup.source_directories', [])

    def set_backup_sources(self, sources: list):
        """Установить список исходных директорий для бэкапа"""
        self.set('backup.source_directories', sources)

    def get_backup_destination(self) -> str:
        """Получить директорию назначения для бэкапа"""
        return self.get('backup.destination_path', "")

    def set_backup_destination(self, destination: str):
        """Установить директорию назначения для бэкапа"""
        self.set('backup.destination_path', destination)

    def get_monitoring_interval(self) -> int:
        """Получить интервал проверки устройств в секундах"""
        return self.get('monitoring.check_interval_seconds', 5)

    def set_monitoring_interval(self, interval: int):
        """Установить интервал проверки устройств в секундах"""
        self.set('monitoring.check_interval_seconds', interval)

    def get_auto_confirm(self) -> bool:
        """Получить флаг автоматического подтверждения бэкапа"""
        return self.get('monitoring.auto_confirm', False)

    def set_auto_confirm(self, auto_confirm: bool):
        """Установить флаг автоматического подтверждения бэкапа"""
        self.set('monitoring.auto_confirm', auto_confirm)

    def get_known_uuids(self) -> dict[str, str]:
        """Get dict of {uuid: label} for known backup drives."""
        return self.get('backup.known_drive_uuids', {})

    def add_known_uuid(self, uuid: str, label: str):
        """Register a drive as known backup destination."""
        uuids = self.get_known_uuids()
        uuids[uuid] = label
        self.set('backup.known_drive_uuids', uuids)
        self.save_config()

    def remove_known_uuid(self, uuid: str):
        """Unregister a drive from known backup destinations."""
        uuids = self.get_known_uuids()
        uuids.pop(uuid, None)
        self.set('backup.known_drive_uuids', uuids)
        self.save_config()

    def get_auth_mode(self) -> str:
        """Get auth mode: none | system | custom"""
        return self.get('backup.auth_mode', 'none')

    def set_auth_mode(self, mode: str):
        self.set('backup.auth_mode', mode)
        self.save_config()

    def get_auth_hash(self) -> str:
        """Get stored bcrypt hash for custom password mode."""
        return self.get('backup.auth_hash', '')

    def set_auth_hash(self, auth_hash: str):
        self.set('backup.auth_hash', auth_hash)
        self.save_config()