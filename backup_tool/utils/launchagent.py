from pathlib import Path


LAUNCHER_NAME = "com.beckyup.monitor"


def _beckyup_dir() -> Path:
    return Path.home() / ".beckyup"


def _launcher_path() -> Path:
    return _beckyup_dir() / "run.sh"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHER_NAME}.plist"


def install(project_dir: str) -> tuple[bool, str]:
    """Install beckyup LaunchAgent for autostart at login."""
    project_dir = str(Path(project_dir).resolve())

    # Create ~/.beckyup/
    _beckyup_dir().mkdir(parents=True, exist_ok=True)

    # Write launcher script
    launcher = _launcher_path()
    launcher.write_text(
        "#!/bin/bash\n"
        f"cd \"{project_dir}\" && exec uv run python main.py\n"
    )
    launcher.chmod(0o755)

    # Write plist
    plist = _plist_path()
    plist_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "  <key>Label</key>\n"
        f"  <string>{LAUNCHER_NAME}</string>\n"
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
    plist.write_text(plist_content)

    # Load with launchctl
    import subprocess
    result = subprocess.run(
        ["launchctl", "load", str(plist)],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        return True, "Автозапуск установлен. beckyup будет запускаться при входе в систему."
    else:
        return False, f"Ошибка launchctl: {result.stderr.strip()}"


def uninstall() -> tuple[bool, str]:
    """Remove beckyup LaunchAgent."""
    plist = _plist_path()
    if plist.exists():
        import subprocess
        subprocess.run(
            ["launchctl", "unload", str(plist)],
            capture_output=True, text=True, timeout=10
        )
        plist.unlink()
    launcher = _launcher_path()
    if launcher.exists():
        launcher.unlink()
    return True, "Автозапуск отключён."


def is_installed() -> bool:
    """Check if LaunchAgent is installed."""
    return _plist_path().exists()
