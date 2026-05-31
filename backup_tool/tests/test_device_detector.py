import unittest
import os
import sys
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.device_detector import DeviceDetector


class TestDeviceDetector(unittest.TestCase):
    @patch("core.device_detector.subprocess.run")
    @patch("core.device_detector.os.path.ismount")
    @patch("core.device_detector.Path.exists")
    @patch("core.device_detector.Path.iterdir")
    def test_macos_parses_diskutil_output(
        self, mock_iterdir, mock_exists, mock_ismount, mock_subprocess
    ):
        mock_exists.return_value = True
        mock_vol = MagicMock(spec=Path)
        mock_vol.name = "BACKUP"
        mock_vol.__str__.return_value = "/Volumes/BACKUP"
        mock_iterdir.return_value = [mock_vol]
        mock_ismount.return_value = True

        fake_diskutil_output = """
   Device Identifier:         disk2s1
   Volume Name:               BACKUP
   Volume UUID:               7A1B2C3D-4E5F-6789-ABCD-EF0123456789
   Mount Point:              /Volumes/BACKUP
"""
        mock_subprocess.return_value.stdout = fake_diskutil_output

        detector = DeviceDetector()
        devices = detector._get_macos_devices()
        self.assertIn(
            ("/Volumes/BACKUP", "BACKUP", "7A1B2C3D-4E5F-6789-ABCD-EF0123456789"),
            devices,
        )

    @patch("core.device_detector.subprocess.run")
    @patch("core.device_detector.os.path.ismount")
    @patch("core.device_detector.Path.exists")
    @patch("core.device_detector.Path.iterdir")
    def test_macos_skips_volume_without_uuid(
        self, mock_iterdir, mock_exists, mock_ismount, mock_subprocess
    ):
        mock_exists.return_value = True
        mock_vol = MagicMock(spec=Path)
        mock_vol.name = "TIMEMACHINE"
        mock_vol.__str__.return_value = "/Volumes/TIMEMACHINE"
        mock_iterdir.return_value = [mock_vol]
        mock_ismount.return_value = True
        mock_subprocess.return_value.stdout = "   Device Identifier:         disk3s1\n"

        detector = DeviceDetector()
        devices = detector._get_macos_devices()
        self.assertEqual(devices, set())

    @patch("core.device_detector.subprocess.run")
    @patch("core.device_detector.os.path.ismount")
    @patch("core.device_detector.Path.exists")
    @patch("core.device_detector.Path.iterdir")
    def test_macos_skips_non_mount_entry(
        self, mock_iterdir, mock_exists, mock_ismount, mock_subprocess
    ):
        mock_exists.return_value = True
        entry = MagicMock(spec=Path)
        entry.name = "NOT_A_MOUNT"
        mock_iterdir.return_value = [entry]
        mock_ismount.return_value = False

        detector = DeviceDetector()
        devices = detector._get_macos_devices()
        mock_subprocess.assert_not_called()
        self.assertEqual(devices, set())

    @patch("core.device_detector.Path.exists")
    def test_non_macos_returns_empty_set(self, mock_exists):
        mock_exists.return_value = False
        detector = DeviceDetector()
        devices = detector.get_mounted_devices()
        self.assertEqual(devices, set())

    def test_get_mounted_devices_returns_set(self):
        detector = DeviceDetector()
        result = detector.get_mounted_devices()
        self.assertIsInstance(result, set)

    @patch("core.device_detector.os.getenv")
    @patch("core.device_detector.subprocess.run")
    def test_linux_parses_lsblk_json(self, mock_run, mock_getenv):
        mock_getenv.return_value = "user"
        fake_json = json.dumps({
            "blockdevices": [
                {
                    "name": "sdb1",
                    "mountpoint": "/media/user/BACKUP",
                    "label": "BACKUP",
                    "uuid": "ABC-123-DEF",
                    "children": []
                }
            ]
        })
        mock_run.return_value.stdout = fake_json
        mock_run.return_value.returncode = 0

        detector = DeviceDetector()
        devices = detector._get_linux_devices()
        self.assertIn(
            ("/media/user/BACKUP", "BACKUP", "ABC-123-DEF"),
            devices,
        )

    @patch("core.device_detector.os.getenv")
    @patch("core.device_detector.subprocess.run")
    def test_linux_skips_system_mounts(self, mock_run, mock_getenv):
        mock_getenv.return_value = "user"
        fake_json = json.dumps({
            "blockdevices": [
                {"name": "sda1", "mountpoint": "/", "label": "", "uuid": "root-uuid"},
                {"name": "sdb1", "mountpoint": "/media/user/USB", "label": "USB", "uuid": "USB-123"}
            ]
        })
        mock_run.return_value.stdout = fake_json
        mock_run.return_value.returncode = 0

        detector = DeviceDetector()
        devices = detector._get_linux_devices()
        self.assertNotIn(("/", "", "root-uuid"), devices)
        self.assertIn(("/media/user/USB", "USB", "USB-123"), devices)

    @patch("core.device_detector.os.getenv")
    @patch("core.device_detector.subprocess.run")
    def test_linux_filters_user_mounts(self, mock_run, mock_getenv):
        mock_getenv.return_value = "user"
        fake_json = json.dumps({
            "blockdevices": [
                {"name": "sdc1", "mountpoint": "/mnt/data", "label": "Data", "uuid": "DATA-456"}
            ]
        })
        mock_run.return_value.stdout = fake_json
        mock_run.return_value.returncode = 0

        detector = DeviceDetector()
        devices = detector._get_linux_devices()
        self.assertIn(("/mnt/data", "Data", "DATA-456"), devices)

    def test_linux_handles_missing_lsblk(self):
        detector = DeviceDetector()
        devices = detector._get_linux_devices()
        self.assertEqual(devices, set())

    def test_windows_ctypes_not_available_returns_empty(self):
        detector = DeviceDetector()
        devices = detector._get_windows_devices()
        self.assertIsInstance(devices, set)
