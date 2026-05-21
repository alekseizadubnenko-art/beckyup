import unittest
import tempfile
import os
import shutil
from pathlib import Path
import sys

# Добавляем корневую директорию проекта в путь, чтобы импортировать модули
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.backup_engine import BackupEngine

class TestBackupEngine(unittest.TestCase):
    def setUp(self):
        """Настройка перед каждым тестом"""
        # Создаем временную директорию для тестов
        self.test_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.test_dir) / "source"
        self.source_dir.mkdir()
        self.dest_dir = Path(self.test_dir) / "destination"
        self.dest_dir.mkdir()

        # Создаем несколько тестовых файлов
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.jpg").write_text("content2")
        (self.source_dir / "file3.tmp").write_text("temporary")
        (self.source_dir / "subdir").mkdir()
        (self.source_dir / "subdir" / "file4.txt").write_text("content3")

        # Создаем большой файл (более 100 МБ по умолчанию в конфигурации)
        # Но для тестов создадим файл размером 150 МБ, чтобы проверить исключение по размеру
        # Однако создание такого файла может быть долгим, поэтому мы будем мокировать проверку размера
        # Вместо этого, мы проверим логику через конфигурацию

    def tearDown(self):
        """Очистка после каждого теста"""
        shutil.rmtree(self.test_dir)

    def test_should_backup_file_default_config(self):
        """Тест should_backup_file с конфигурацией по умолчанию"""
        engine = BackupEngine()
        # Устанавливаем тестовые директории
        engine.source_directories = [self.source_dir]
        engine.destination_path = self.dest_dir

        # Тестируем various files
        # file1.txt - должен быть скопирован (нет исключений, расширение * подходит)
        self.assertTrue(engine.should_backup_file(self.source_dir / "file1.txt"))
        # file2.jpg - аналогично
        self.assertTrue(engine.should_backup_file(self.source_dir / "file2.jpg"))
        # file3.tmp - исключен по шаблону *.tmp
        self.assertFalse(engine.should_backup_file(self.source_dir / "file3.tmp"))
        # Файл в поддиректории
        self.assertTrue(engine.should_backup_file(self.source_dir / "subdir" / "file4.txt"))

    def test_should_backup_file_custom_extensions(self):
        """Тест should_backup_file с пользовательскими расширениями"""
        engine = BackupEngine()
        # Переопределяем конфигурацию, чтобы принимать только .txt файлы
        engine.config["backup"]["file_extensions"] = ["*.txt"]
        engine.source_directories = [self.source_dir]
        engine.destination_path = self.dest_dir

        self.assertTrue(engine.should_backup_file(self.source_dir / "file1.txt"))
        self.assertFalse(engine.should_backup_file(self.source_dir / "file2.jpg"))  # не .txt
        self.assertFalse(engine.should_backup_file(self.source_dir / "file3.tmp"))  # не .txt и исключено
        self.assertTrue(engine.should_backup_file(self.source_dir / "subdir" / "file4.txt"))

    def test_should_backup_file_size_limit(self):
        """Тест should_backup_file с ограничением по размеру"""
        engine = BackupEngine()
        # Устанавливаем лимит размера в 0 байт (чтобы никакие файлы не проходили)
        engine.config["backup"]["max_file_size_mb"] = 0
        engine.source_directories = [self.source_dir]
        engine.destination_path = self.dest_dir

        # Ни один файл не должен проходить, так как все имеют размер > 0
        self.assertFalse(engine.should_backup_file(self.source_dir / "file1.txt"))
        self.assertFalse(engine.should_backup_file(self.source_dir / "file2.jpg"))

        # Устанавливаем большой лимит
        engine.config["backup"]["max_file_size_mb"] = 1000  # 1000 МБ
        self.assertTrue(engine.should_backup_file(self.source_dir / "file1.txt"))

    def test_backup_directory_empty_source(self):
        """Тест бэкапа пустой директории"""
        engine = BackupEngine()
        empty_source = self.source_dir / "empty"
        empty_source.mkdir()
        engine.source_directories = [empty_source]
        engine.destination_path = self.dest_dir

        stats = engine.backup_directory(empty_source, self.dest_dir / "empty_backup")
        self.assertEqual(stats["copied"], 0)
        self.assertEqual(stats["skipped"], 0)
        self.assertEqual(stats["errors"], 0)

    def test_backup_directory_with_files(self):
        """Тест бэкапа директории с файлами"""
        engine = BackupEngine()
        engine.source_directories = [self.source_dir]
        engine.destination_path = self.dest_dir

        # Запускаем бэкап
        stats = engine.backup_directory(self.source_dir, self.dest_dir / "backup")

        # Проверяем, что файлы были скопированы
        # Ожидаем: file1.txt, file2.jpg, subdir/file4.txt (file3.tmp исключен)
        self.assertEqual(stats["copied"], 3)
        self.assertEqual(stats["skipped"], 1)  # file3.tmp
        self.assertEqual(stats["errors"], 0)

        # Проверяем, что файлы действительно существуют в назначении
        backup_path = self.dest_dir / "backup"
        self.assertTrue((backup_path / "file1.txt").exists())
        self.assertTrue((backup_path / "file2.jpg").exists())
        self.assertTrue((backup_path / "subdir" / "file4.txt").exists())
        self.assertFalse((backup_path / "file3.tmp").exists())

    def test_run_backup_no_sources(self):
        """Тест run_backup без настроенных источников"""
        engine = BackupEngine()
        # Не устанавливаем source_directories (по умолчанию пустой список)
        engine.destination_path = self.dest_dir

        result = engine.run_backup()
        self.assertIn("error", result)
        self.assertEqual(result["error"], "No source directories configured")

    def test_run_backup_no_destination(self):
        """Тест run_backup без директории назначения"""
        engine = BackupEngine()
        engine.source_directories = [self.source_dir]
        # Не устанавливаем destination_path (по умолчанию пустой Path)

        result = engine.run_backup()
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Destination directory does not exist or not set")

if __name__ == '__main__':
    unittest.main()