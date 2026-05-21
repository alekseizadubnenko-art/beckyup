import unittest
import os
import sys
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
