import os
import sys
import subprocess
from pathlib import Path


SERVICE_NAME = "beckyup"


def _is_macos():
    return sys.platform == "darwin"


def _is_linux():
    return sys.platform == "linux"


def _is_windows():
    return os.name == "nt"


def _beckyup_dir() -> Path:
    return Path.home() / ".beckyup"


def _launcher_path() -> Path:
    return _beckyup_dir() / "run.sh"


# ── macOS LaunchAgent ──

def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"com.{SERVICE_NAME}.monitor.plist"


def _install_macos(project_dir: str) -> tuple[bool, str]:
    _beckyup_dir().mkdir(parents=True, exist_ok=True)
    launcher = _launcher_path()
    launcher.write_text(
        "#!/bin/bash\n"
        f"cd \"{project_dir}\" && exec uv run python main.py\n"
    )
    launcher.chmod(0o755)

    plist = _plist_path()
    plist.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "  <key>Label</key>\n"
        f"  <string>com.{SERVICE_NAME}.monitor</string>\n"
        "  <key>ProgramArguments</key>\n"
        "  <array>\n"
        f"    <string>{launcher}</string>\n"
        "  </array>\n"
        "  <key>RunAtLoad</key>\n"
        "  <true/>\n"
        "  <key>KeepAlive</key>\n"
        "  <true/>\n"
        "  <key>StandardOutPath</key>\n"
        f"  <string>{_beckyup_dir() / 'beckyup.log'}</string>\n"
        "  <key>StandardErrorPath</key>\n"
        f"  <string>{_beckyup_dir() / 'beckyup.log'}</string>\n"
        "</dict>\n"
        "</plist>\n"
    )

    result = subprocess.run(
        ["launchctl", "load", str(plist)],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        return True, "Автозапуск установлен. beckyup будет запускаться при входе в систему."
    return False, f"Ошибка launchctl: {result.stderr.strip()}"


def _uninstall_macos() -> tuple[bool, str]:
    plist = _plist_path()
    if plist.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist)],
            capture_output=True, text=True, timeout=10
        )
        plist.unlink()
    launcher = _launcher_path()
    if launcher.exists():
        launcher.unlink()
    return True, "Автозапуск отключён."


def _is_installed_macos() -> bool:
    return _plist_path().exists()


# ── Linux systemd user service ──

def _systemd_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"


def _install_linux(project_dir: str) -> tuple[bool, str]:
    _beckyup_dir().mkdir(parents=True, exist_ok=True)
    launcher = _launcher_path()
    launcher.write_text(
        "#!/bin/bash\n"
        f"cd \"{project_dir}\" && exec uv run python main.py\n"
    )
    launcher.chmod(0o755)

    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)

    svc = _systemd_path()
    svc.write_text(
        f"[Unit]\n"
        f"Description=beckyup — emergency backup monitor\n"
        f"After=default.target\n\n"
        f"[Service]\n"
        f"Type=simple\n"
        f"ExecStart={launcher}\n"
        f"Restart=on-failure\n"
        f"RestartSec=10\n\n"
        f"[Install]\n"
        f"WantedBy=default.target\n"
    )

    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True, timeout=10
    )
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", str(svc)],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        return True, "Автозапуск установлен (systemd user service)."
    return False, f"Ошибка systemctl: {result.stderr.strip()}"


def _uninstall_linux() -> tuple[bool, str]:
    svc = _systemd_path()
    if svc.exists():
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", SERVICE_NAME],
            capture_output=True, timeout=10
        )
        svc.unlink()
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            capture_output=True, timeout=10
        )
    launcher = _launcher_path()
    if launcher.exists():
        launcher.unlink()
    return True, "Автозапуск отключён."


def _is_installed_linux() -> bool:
    return _systemd_path().exists()


# ── Windows Startup folder ──

def _startup_script_path() -> Path:
    return _beckyup_dir() / "run.bat"


def _startup_link_path() -> Path:
    startup = Path(os.getenv("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / f"{SERVICE_NAME}.lnk"


def _install_windows(project_dir: str) -> tuple[bool, str]:
    _beckyup_dir().mkdir(parents=True, exist_ok=True)

    bat = _startup_script_path()
    bat.write_text(
        f'@echo off\n'
        f'cd /d "{project_dir}"\n'
        f'uv run python main.py\n'
    )

    # Create a .vbs script that runs the bat silently (no console window)
    vbs = _beckyup_dir() / "run.vbs"
    vbs.write_text(
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run chr(34) & "{bat}" & Chr(34), 0\n'
        'Set WshShell = Nothing\n'
    )

    # Add to Startup via HKCU Run registry
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, SERVICE_NAME, 0, winreg.REG_SZ, str(vbs))
        winreg.CloseKey(key)
        return True, "Автозапуск установлен (реестр HKCU\\Run)."
    except Exception as e:
        return False, f"Ошибка реестра: {e}"


def _uninstall_windows() -> tuple[bool, str]:
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, SERVICE_NAME)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception:
        pass

    for p in [_startup_script_path(), _beckyup_dir() / "run.vbs"]:
        if p.exists():
            p.unlink()
    return True, "Автозапуск отключён."


def _is_installed_windows() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        try:
            winreg.QueryValueEx(key, SERVICE_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


# ── Public API ──

def install(project_dir: str) -> tuple[bool, str]:
    """Install autostart for current platform."""
    project_dir = str(Path(project_dir).resolve())
    if _is_macos():
        return _install_macos(project_dir)
    if _is_linux():
        return _install_linux(project_dir)
    if _is_windows():
        return _install_windows(project_dir)
    return False, "Платформа не поддерживается."


def uninstall() -> tuple[bool, str]:
    """Remove autostart for current platform."""
    if _is_macos():
        return _uninstall_macos()
    if _is_linux():
        return _uninstall_linux()
    if _is_windows():
        return _uninstall_windows()
    return False, "Платформа не поддерживается."


def is_installed() -> bool:
    """Check if autostart is configured for current platform."""
    if _is_macos():
        return _is_installed_macos()
    if _is_linux():
        return _is_installed_linux()
    if _is_windows():
        return _is_installed_windows()
    return False
