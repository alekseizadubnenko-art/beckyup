import os
import shutil
import json
from pathlib import Path
from typing import List, Dict, Any
from utils.logger import get_logger

class BackupEngine:
    def __init__(self, config_path: str = None):
        self.logger = get_logger("backup_engine")
        self.config = self._load_config(config_path)
        self.source_directories: List[Path] = []
        self.destination_path: Path = Path()
        self._load_sources_from_config()

    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        """Загрузка конфигурации"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "default_config.json"

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.logger.debug(f"Конфигурация загружена из {config_path}")
            return config
        except FileNotFoundError:
            self.logger.warning(f"Файл конфигурации не найден: {config_path}. Используем значения по умолчанию.")
            return self._get_default_config()
        except json.JSONDecodeError as e:
            self.logger.error(f"Ошибка парсинга конфигурации: {e}. Используем значения по умолчанию.")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Возврат конфигурации по умолчанию"""
        return {
            "backup": {
                "source_directories": [],
                "destination_path": "",
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

    def _load_sources_from_config(self):
        """Загрузка списка исходных директорий из конфигурации"""
        sources = self.config.get("backup", {}).get("source_directories", [])
        self.source_directories = [Path(s) for s in sources if Path(s).exists()]
        dest = self.config.get("backup", {}).get("destination_path", "")
        self.destination_path = Path(dest) if dest else Path()

        self.logger.info(f"Загружено {len(self.source_directories)} исходных директорий")
        self.logger.info(f"Директория назначения: {self.destination_path}")

    def add_source_directory(self, path: str):
        """Добавление исходной директории в список для бэкапа"""
        path_obj = Path(path)
        if path_obj.exists() and path_obj.is_dir():
            if path_obj not in self.source_directories:
                self.source_directories.append(path_obj)
                self.logger.info(f"Добавлена исходная директория: {path}")
                # TODO: Обновить конфигурационный файл
            else:
                self.logger.warning(f"Директория уже в списке: {path}")
        else:
            self.logger.error(f"Путь не существует или не является директорией: {path}")

    def remove_source_directory(self, path: str):
        """Удаление исходной директории из списка для бэкапа"""
        path_obj = Path(path)
        if path_obj in self.source_directories:
            self.source_directories.remove(path_obj)
            self.logger.info(f"Удалена исходная директория: {path}")
            # TODO: Обновить конфигурационный файл
        else:
            self.logger.warning(f"Директория не найдена в списке: {path}")

    def set_destination(self, path: str):
        """Установка директории назначения для бэкапа"""
        path_obj = Path(path)
        if path_obj.exists() and path_obj.is_dir():
            self.destination_path = path_obj
            self.logger.info(f"Установлена директория назначения: {path}")
            # TODO: Обновить конфигурационный файл
        else:
            self.logger.error(f"Путь не существует или не является директорией: {path}")

    def has_valid_destination(self) -> bool:
        """Проверка, что директория назначения установлена и доступна"""
        return bool(self.destination_path and self.destination_path.exists())

    def should_backup_file(self, file_path: Path) -> bool:
        """Определение, нужно ли бэкапить файл на основе расширений и исключений"""
        config = self.config.get("backup", {})
        extensions = config.get("file_extensions", ["*"])
        exclude_patterns = config.get("exclude_patterns", ["*.tmp", "*.temp", "~*"])
        max_size_mb = config.get("max_file_size_mb", 100)

        # Проверка размера файла
        try:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > max_size_mb:
                self.logger.debug(f"Файл слишком большой ({file_size_mb:.2f} МБ): {file_path}")
                return False
        except OSError:
            return False

        # Проверка расширений (если указано "*", то все подходят)
        if "*" not in extensions:
            extension_match = any(file_path.match(ext) for ext in extensions)
            if not extension_match:
                return False

        # Проверка исключений
        for pattern in exclude_patterns:
            if file_path.match(pattern):
                self.logger.debug(f"Файл исключен по шаблону {pattern}: {file_path}")
                return False

        return True

    def backup_directory(self, source: Path, destination: Path) -> Dict[str, Any]:
        """
        Бэкап одной директории
        Возвращает статистику: скопировано файлов, пропущено, ошибок
        """
        stats = {
            "copied": 0,
            "skipped": 0,
            "errors": 0,
            "files": []
        }

        if not source.exists():
            self.logger.error(f"Исходная директория не существует: {source}")
            return stats

        # Создаем директорию назначения, если её нет
        destination.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Начало бэкапа: {source} -> {destination}")

        for root, dirs, files in os.walk(source):
            root_path = Path(root)
            for file_name in files:
                file_path = root_path / file_name
                relative_path = file_path.relative_to(source)
                dest_file_path = destination / relative_path

                # Проверяем, нужно ли бэкапить этот файл
                if not self.should_backup_file(file_path):
                    stats["skipped"] += 1
                    continue

                try:
                    # Создаем поддиректории в назначении, если нужно
                    dest_file_path.parent.mkdir(parents=True, exist_ok=True)

                    # Копируем файл
                    shutil.copy2(file_path, dest_file_path)

                    # Проверяем копию, если включено в конфигурации
                    if self.config.get("backup", {}).get("verify_after_copy", True):
                        if not self._verify_copy(file_path, dest_file_path):
                            raise Exception("Проверка копии не удалась")

                    stats["copied"] += 1
                    stats["files"].append(str(relative_path))
                    self.logger.debug(f"Скопирован: {relative_path}")

                except Exception as e:
                    stats["errors"] += 1
                    self.logger.error(f"Ошибка при копировании {file_path}: {e}")

        self.logger.info(
            f"Бэкап завершен. Скопировано: {stats['copied']}, "
            f"Пропущено: {stats['skipped']}, Ошибок: {stats['errors']}"
        )
        return stats

    def _verify_copy(self, source: Path, destination: Path) -> bool:
        """Проверка идентичности исходного и скопированного файла по размеру"""
        try:
            return source.stat().st_size == destination.stat().st_size
        except OSError:
            return False

    def _check_disk_space(self, destination: Path, source_paths: list[Path]) -> tuple[bool, str]:
        """Проверка, достаточно ли места на диске назначения"""
        try:
            _, _, free_bytes = shutil.disk_usage(destination)
            total_needed = 0
            for src in source_paths:
                if src.is_dir():
                    for root, dirs, files in os.walk(src):
                        for f in files:
                            try:
                                total_needed += (Path(root) / f).stat().st_size
                            except OSError:
                                continue
                else:
                    total_needed += src.stat().st_size
            free_mb = free_bytes / (1024 * 1024)
            needed_mb = total_needed / (1024 * 1024)
            if needed_mb > free_mb:
                return False, f"На диске осталось {free_mb:.0f} МБ, нужно {needed_mb:.0f} МБ"
            return True, ""
        except OSError as e:
            return False, f"Не удалось проверить место на диске: {e}"

    def _check_writeable(self, destination: Path) -> tuple[bool, str]:
        """Проверка, доступен ли диск для записи"""
        try:
            destination.mkdir(parents=True, exist_ok=True)
            test_file = destination / ".beckyup_healthcheck"
            test_file.write_text("ok")
            test_file.unlink()
            return True, ""
        except OSError as e:
            return False, f"Диск {destination} не доступен для записи: {e}"

    def run_backup(self) -> Dict[str, Any]:
        """Выполнение полного бэкапа всех настроенных директорий"""
        if not self.source_directories:
            self.logger.warning("Нет настроенных исходных директорий для бэкапа")
            return {"error": "No source directories configured"}

        # Проверяем, что destination_path установлен (не равен Path() по умолчанию)
        if not self.destination_path or self.destination_path == Path():
            self.logger.error(f"Директория назначения не установлена: {self.destination_path}")
            return {"error": "Destination directory not set"}

        # Check if destination is writeable
        ok, msg = self._check_writeable(self.destination_path)
        if not ok:
            self.logger.error(msg)
            return {"error": msg}

        # Check if destination has enough space
        ok, msg = self._check_disk_space(self.destination_path, self.source_directories)
        if not ok:
            self.logger.error(msg)
            return {"error": msg}

        overall_stats = {
            "total_copied": 0,
            "total_skipped": 0,
            "total_errors": 0,
            "directories": []
        }

        for source in self.source_directories:
            # Создаем поддиректорию в назначении с именем исходной директории
            dest_dir = self.destination_path / source.name
            dir_stats = self.backup_directory(source, dest_dir)

            overall_stats["total_copied"] += dir_stats["copied"]
            overall_stats["total_skipped"] += dir_stats["skipped"]
            overall_stats["total_errors"] += dir_stats["errors"]
            overall_stats["directories"].append({
                "source": str(source),
                "destination": str(dest_dir),
                "stats": dir_stats
            })

        return overall_stats
