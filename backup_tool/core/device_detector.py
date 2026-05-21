import os
import re
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
        return set()

    def _get_windows_devices(self) -> set[tuple[str, str, str]]:
        return set()
