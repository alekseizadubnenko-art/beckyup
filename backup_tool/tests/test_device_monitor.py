import unittest
from unittest.mock import MagicMock, patch
from core.device_monitor import DeviceMonitor


class TestDeviceMonitor(unittest.TestCase):
    def setUp(self):
        self.engine = MagicMock()
        self.engine.config = {
            "backup": {"known_drive_uuids": {"ABC-123": "MyDrive"}},
            "monitoring": {"auto_confirm": True},
        }
        self.detector = MagicMock()
        self.monitor = DeviceMonitor(
            self.engine, detector=self.detector, check_interval=3600
        )

    def test_known_drive_triggers_backup(self):
        self.detector.get_mounted_devices.return_value = {
            ("/Volumes/DISK", "DISK", "ABC-123")
        }
        self.monitor._check_for_new_devices()
        self.engine.run_backup.assert_called_once()

    def test_unknown_drive_ignored(self):
        self.detector.get_mounted_devices.return_value = {
            ("/Volumes/OTHER", "OTHER", "XYZ-999")
        }
        self.monitor._check_for_new_devices()
        self.engine.run_backup.assert_not_called()

    def test_no_new_devices_no_backup(self):
        self.detector.get_mounted_devices.return_value = set()
        self.monitor._check_for_new_devices()
        self.engine.run_backup.assert_not_called()
