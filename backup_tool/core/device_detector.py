import os
import re
import sys
import json
import subprocess
from pathlib import Path


class DeviceDetector:
    def get_mounted_devices(self) -> set[tuple[str, str, str]]:
        """Returns set of (mount_path, label, uuid) for external drives."""
        return self._get_macos_devices() | self._get_linux_devices() | self._get_windows_devices()

    def _get_macos_devices(self) -> set[tuple[str, str, str]]:
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
                m = re.search(r'Volume UUID:\s+(\S+)', result.stdout)
                if m:
                    devices.add((str(entry), label, m.group(1)))
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                continue
        return devices

    def _get_linux_devices(self) -> set[tuple[str, str, str]]:
        """Detect external drives on Linux via lsblk."""
        devices = set()
        try:
            result = subprocess.run(
                ["lsblk", "-o", "NAME,MOUNTPOINT,LABEL,UUID", "-J"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return devices
            data = json.loads(result.stdout)
            user = os.getenv("USER", "")
            allowed_prefixes = (
                f"/media/{user}", "/mnt",
                f"/run/media/{user}", "/run/mount"
            )
            for blockdev in data.get("blockdevices", []):
                mounts = self._flatten_lsblk(blockdev)
                for mount_point, label, uuid in mounts:
                    if not mount_point or not uuid:
                        continue
                    if mount_point.startswith(allowed_prefixes):
                        devices.add((mount_point, label or "USB", uuid))
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError,
                subprocess.CalledProcessError, KeyError):
            pass
        return devices

    def _flatten_lsblk(self, entry, parent_mount=None):
        """Recursively extract (mountpoint, label, uuid) from lsblk tree."""
        results = []
        name = entry.get("name", "")
        mount = entry.get("mountpoint") or parent_mount
        label = entry.get("label", "") or ""
        uuid = entry.get("uuid", "") or ""
        if mount:
            results.append((mount, label, uuid))
        for child in entry.get("children", []):
            results.extend(self._flatten_lsblk(child, mount))
        return results

    def _get_windows_devices(self) -> set[tuple[str, str, str]]:
        """Detect removable drives on Windows via ctypes WinAPI."""
        devices = set()
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            DRIVE_REMOVABLE = 2

            GetLogicalDrives = kernel32.GetLogicalDrives
            GetLogicalDrives.restype = wintypes.DWORD

            GetDriveTypeW = kernel32.GetDriveTypeW
            GetDriveTypeW.restype = wintypes.UINT
            GetDriveTypeW.argtypes = [wintypes.LPCWSTR]

            GetVolumeInformationW = kernel32.GetVolumeInformationW
            GetVolumeInformationW.restype = wintypes.BOOL
            GetVolumeInformationW.argtypes = [
                wintypes.LPCWSTR,
                wintypes.LPWSTR, wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                wintypes.POINTER(wintypes.DWORD),
                wintypes.POINTER(wintypes.DWORD),
                wintypes.LPWSTR, wintypes.DWORD,
            ]

            drive_bits = GetLogicalDrives()
            for i in range(26):
                if drive_bits & (1 << i):
                    root = f"{chr(65 + i)}:\\"
                    if GetDriveTypeW(root) != DRIVE_REMOVABLE:
                        continue
                    vol_name_buf = ctypes.create_unicode_buffer(256)
                    vol_serial = wintypes.DWORD(0)
                    success = GetVolumeInformationW(
                        root, vol_name_buf, 256,
                        ctypes.byref(vol_serial), None, None, None, 0
                    )
                    if success:
                        label = vol_name_buf.value or "USB"
                        uuid = f"{vol_serial.value:08X}"
                        devices.add((root, label, uuid))
        except (ImportError, AttributeError, OSError):
            pass
        return devices
