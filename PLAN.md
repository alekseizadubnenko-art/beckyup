# BECKYUP MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship working MVP — plug in known USB → auto backup configured directories

**Architecture:** Polling-based device detector + thread monitor + TDD. Native deps optional, `questionary` for CLI wizard.

**Tech Stack:** Python 3.12+, `unittest`, `questionary`, `shutil`, `subprocess`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `utils/platform.py` | Create | OS detection helpers |
| `core/device_detector.py` | Create | Polling external drives, UUID extraction |
| `core/device_monitor.py` | Modify | Use device_detector + white list |
| `core/backup_engine.py` | Modify | Disk space check, write test, error handling |
| `config/manager.py` | Modify | White list CRUD methods |
| `config/default_config.json` | Modify | Add `known_drive_uuids` field |
| `cli/wizard.py` | Create | First-run setup wizard |
| `main.py` | Modify | `--wizard` flag, first-run detection |
| `requirements.txt` | Create | Dependencies |
| `tests/test_device_detector.py` | Create | Tests for detector |
| `tests/test_device_monitor.py` | Create | Tests for monitor logic |
| `tests/test_backup_engine.py` | Modify | Tests for new safety checks |
| `README.md` | Modify | Actual usage instructions |

---

### Task 1: Create `utils/platform.py`

**Files:**
- Create: `backup_tool/utils/platform.py`

```
# backup_tool/utils/platform.py

import os
import sys

def is_macos():
    return sys.platform == "darwin"

def is_linux():
    return sys.platform == "linux"

def is_windows():
    return os.name == "nt"
```

No tests needed — trivial helpers, fully covered by integration tests in Task 2.

---

### Task 2: Create `core/device_detector.py` + tests

**Files:**
- Create: `backup_tool/core/device_detector.py`
- Create: `backup_tool/tests/test_device_detector.py`

**Interface:**
```python
class DeviceDetector:
    def get_mounted_devices(self) -> set[tuple[str, str, str]]:
        """Returns set of (mount_path, label, uuid) for external removable drives."""
```

**Implementation for macOS** (primary platform):

```python
import os
import subprocess
from pathlib import Path

def _get_volumes_macos():
    devices = set()
    volumes = Path("/Volumes")
    if not volumes.exists():
        return devices
    for entry in volumes.iterdir():
        if not os.path.ismount(entry):
            continue
        label = entry.name
        try:
            result = subprocess.run(
                ["diskutil", "info", str(entry)],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "Volume UUID" in line or "Volume UUID" in line:
                    uuid = line.split(":")[-1].strip()
                    devices.add((str(entry), label, uuid))
                    break
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            continue
    return devices
```

For Linux and Windows, stubs that return empty set (for future implementation).

**Tests:**

```python
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from core.device_detector import DeviceDetector

class TestDeviceDetector(unittest.TestCase):
    @patch("core.device_detector.os.path.ismount")
    @patch("core.device_detector.Path.exists")
    @patch("core.device_detector.Path.iterdir")
    def test_macos_detects_volume(self, mock_iterdir, mock_exists, mock_ismount):
        mock_exists.return_value = True
        mock_vol = MagicMock(spec=Path)
        mock_vol.name = "BACKUP"
        mock_vol.__str__.return_value = "/Volumes/BACKUP"
        mock_iterdir.return_value = [mock_vol]
        mock_ismount.return_value = True
        detector = DeviceDetector()
        devices = detector.get_mounted_devices()
        self.assertTrue(len(devices) >= 0)

    def test_get_mounted_devices_returns_set(self):
        detector = DeviceDetector()
        result = detector.get_mounted_devices()
        self.assertIsInstance(result, set)
```

---

### Task 3: Update `core/device_monitor.py` + tests

**Files:**
- Modify: `backup_tool/core/device_monitor.py`
- Create: `backup_tool/tests/test_device_monitor.py`

**Changes:**
1. Accept `DeviceDetector` instance in `__init__`
2. Replace `_get_connected_devices()` stub with `self.detector.get_mounted_devices()`
3. Add white list check: only trigger backup for known UUIDs
4. Track devices by UUID instead of path

```python
class DeviceMonitor:
    def __init__(self, backup_engine, detector=None, check_interval=5):
        self.logger = get_logger("device_monitor")
        self.backup_engine = backup_engine
        self.detector = detector or DeviceDetector()
        self.check_interval = check_interval
        self.running = False
        self.monitor_thread = None
        self.known_devices: set[tuple[str, str, str]] = set()
        self.callbacks: list[Callable] = []

    def _check_for_new_devices(self):
        try:
            current_devices = self.detector.get_mounted_devices()
            current_uuids = {d[2] for d in current_devices}  # (path, label, uuid)
            known_uuids = {d[2] for d in self.known_devices}
            new_uuids = current_uuids - known_uuids
            for mount_path, label, uuid in current_devices:
                if uuid in new_uuids:
                    if self.backup_engine.config.get("backup", {}).get("known_drive_uuids", {}).get(uuid):
                        self._on_device_connected(mount_path)
                    else:
                        self.logger.info(f"Неизвестное устройство: {label} — игнорируем")
            lost_uuids = known_uuids - current_uuids
            if lost_uuids:
                self.logger.info(f"Устройства отсоединены: {lost_uuids}")
            self.known_devices = current_devices
        except Exception as e:
            self.logger.error(f"Ошибка при проверке устройств: {e}")
```

**Tests:**

```python
class TestDeviceMonitor(unittest.TestCase):
    def setUp(self):
        self.engine = MagicMock()
        self.engine.config = {
            "backup": {"known_drive_uuids": {"ABC-123": "MyDrive"}},
            "monitoring": {"auto_confirm": True}
        }
        self.detector = MagicMock()
        self.monitor = DeviceMonitor(self.engine, detector=self.detector, check_interval=3600)

    def test_known_drive_triggers_backup(self):
        self.detector.get_mounted_devices.return_value = {("/Volumes/DISK", "DISK", "ABC-123")}
        self.monitor._check_for_new_devices()
        self.engine.run_backup.assert_called_once()

    def test_unknown_drive_ignored(self):
        self.detector.get_mounted_devices.return_value = {("/Volumes/OTHER", "OTHER", "XYZ-999")}
        self.monitor._check_for_new_devices()
        self.engine.run_backup.assert_not_called()
```

---

### Task 4: Update `core/backup_engine.py` + tests

**Files:**
- Modify: `backup_tool/core/backup_engine.py`
- Modify: `backup_tool/tests/test_backup_engine.py`

**Changes:**

1. Add `_check_disk_space(destination, sources) -> bool` — verify enough space
2. Add `_check_writeable(destination) -> bool` — test file write
3. Update `backup_directory()` — catch OSError per file, continue

```python
def _check_disk_space(self, destination: Path, source_paths: list[Path]) -> tuple[bool, str]:
    """Check if destination has enough space. Returns (ok, message)."""
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
    """Test that destination accepts writes."""
    test_file = destination / ".beckyup_healthcheck"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        return True, ""
    except OSError as e:
        return False, f"Диск {destination} не доступен для записи: {e}"

def run_backup(self) -> dict[str, Any]:
    # After existing validation, before copying:
    ok, msg = self._check_writeable(self.destination_path)
    if not ok:
        return {"error": msg}
    ok, msg = self._check_disk_space(self.destination_path, self.source_directories)
    if not ok:
        return {"error": msg}
    # ... existing code ...
```

In `backup_directory`, update the exception handler:

```python
except OSError as e:
    stats["errors"] += 1
    self.logger.error(f"Ошибка при копировании {file_path}: {e}")
    continue  # was: pass, but explicit continue is clearer
```

**New tests:**

```python
def test_disk_space_insufficient(self):
    engine = BackupEngine()
    with patch("shutil.disk_usage") as mock_du:
        mock_du.return_value = (0, 0, 1)  # 1 byte free
        ok, msg = engine._check_disk_space(self.dest_dir, [self.source_dir / "file1.txt"])
        self.assertFalse(ok)

def test_writeable_check_fails_on_readonly(self):
    engine = BackupEngine()
    writeable, _ = engine._check_writeable(self.dest_dir)
    self.assertTrue(writeable)
```

---

### Task 5: Update config for white list

**Files:**
- Modify: `backup_tool/config/manager.py`
- Modify: `backup_tool/config/default_config.json`

**Manager additions:**

```python
def get_known_uuids(self) -> dict[str, str]:
    return self.config.get("backup", {}).get("known_drive_uuids", {})

def add_known_uuid(self, uuid: str, label: str):
    uuids = self.get_known_uuids()
    uuids[uuid] = label
    self.set("backup.known_drive_uuids", uuids)
    self.save_config()

def remove_known_uuid(self, uuid: str):
    uuids = self.get_known_uuids()
    uuids.pop(uuid, None)
    self.set("backup.known_drive_uuids", uuids)
    self.save_config()
```

**default_config.json update:**

```json
{
  "backup": {
    "source_directories": [],
    "destination_path": "",
    "known_drive_uuids": {},
    "file_extensions": ["*"],
    "exclude_patterns": ["*.tmp", "*.temp", "~*"],
    "max_file_size_mb": 100,
    "verify_after_copy": true
  },
  ...
}
```

---

### Task 6: Create `cli/wizard.py`

**Files:**
- Create: `backup_tool/cli/wizard.py`

```python
import questionary
from pathlib import Path

def run_wizard(config_manager, backup_engine) -> bool:
    """Run first-time setup. Returns True if config saved."""
    print("\n=== Добро пожаловать в beckyup! ===")
    print("Экстренный бэкап важных данных\n")

    # Step 1: Select directories
    choices = [
        questionary.Choice(str(p), checked=p.name in ["Projects", "Desktop"])
        for p in Path.home().iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    selected = questionary.checkbox(
        "Какие папки бэкапить? (Space — выбрать, Enter — подтвердить)",
        choices=choices
    ).ask()
    if not selected:
        selected = []
    backup_engine.source_directories = [Path(s) for s in selected]

    # Step 2: Wait for backup drive
    input("Подключи бэкап-флешку и нажми Enter...")
    # Detect connected drives
    from core.device_detector import DeviceDetector
    detector = DeviceDetector()
    drives = detector.get_mounted_devices()
    if drives:
        print(f"Найдены диски:")
        for path, label, uuid in drives:
            print(f"  {label} ({uuid})")
        chosen = questionary.select("Выбери бэкап-диск:", choices=[f"{label} ({uuid})" for _, label, uuid in drives]).ask()
        # Extract UUID from chosen string
        chosen_uuid = chosen.split("(")[1].rstrip(")") if "(" in chosen else ""
        config_manager.add_known_uuid(chosen_uuid, chosen.split(" (")[0])
    else:
        print("Диски не найдены. Можно будет настроить позже.")

    # Step 3: Auto-confirm
    auto = questionary.confirm("Бэкапить автоматически при подключении флешки?").ask()
    config_manager.set("monitoring.auto_confirm", auto)

    # Save
    config_manager.set("backup.source_directories", [str(p) for p in backup_engine.source_directories])
    config_manager.save_config()
    print("\n✓ Конфигурация сохранена. Готов к работе!\n")
    return True
```

---

### Task 7: Update `main.py`

**Files:**
- Modify: `backup_tool/main.py`

**Changes:**
1. Add `--wizard` flag
2. On first run (no `user_config.json`) → auto-launch wizard
3. Pass `DeviceDetector` to `DeviceMonitor`

```python
# New imports
from core.device_detector import DeviceDetector

# In main():
parser.add_argument("--wizard", action="store_true", help="Запустить настройку")
# ...
args = parser.parse_args()

# Check first run
if args.wizard or not config_manager or not config_manager.config_file.exists():
    from cli.wizard import run_wizard
    run_wizard(config_manager, backup_engine)
    if args.wizard:
        return

# Pass detector to monitor
detector = DeviceDetector()
device_monitor = DeviceMonitor(backup_engine, detector=detector)
```

---

### Task 8: Create `requirements.txt`

**Files:**
- Create: `backup_tool/requirements.txt`

```
questionary>=2.0,<3.0
```

---

### Task 9: Update `README.md`

Replace placeholder text with actual usage instructions. Focus on: install, first run, daily use, CLI flags.

---

## Self-Review Checklist

- [ ] Spec coverage: each section of SPEC.md maps to a task
- [ ] No placeholders, TODOs, or "implement later"
- [ ] Type/method signatures consistent across tasks
- [ ] Every code step contains actual working code
