import subprocess
import sys
import os
import bcrypt
from pathlib import Path


def _is_macos():
    return sys.platform == "darwin"


def _is_linux():
    return sys.platform == "linux"


def _is_windows():
    return os.name == "nt"


def _osascript_dialog(message: str, buttons: list[str], default: str = None,
                      icon: str = "note", title: str = "beckyup",
                      hidden_answer: bool = False, extra: str = None) -> str | None:
    """Show macOS native dialog via osascript. Returns button text or None."""
    if not _is_macos():
        return None
    opts = f'with title "{title}" buttons {{'
    opts += ", ".join(f'"{b}"' for b in buttons)
    opts += "}"
    if default:
        opts += f' default button "{default}"'
    if icon:
        opts += f' with icon {icon}'
    if hidden_answer:
        opts += " default answer \"\" with hidden answer"
    elif extra:
        opts += f' default answer "{extra}"'
    script = f'display dialog "{message}" {opts}'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return None
        out = result.stdout.strip()
        if "text returned:" in out:
            return out.split("text returned:")[-1].strip()
        if "button returned:" in out:
            return out.split("button returned:")[-1].split(",")[0].strip()
        return "OK"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _linux_dialog(message: str, buttons: list[str], default: str = None,
                  title: str = "beckyup", hidden_answer: bool = False) -> str | None:
    """Show Linux dialog via zenity (GNOME) or kdialog (KDE). Falls back to terminal."""
    if not _is_linux():
        return None

    # Try zenity
    try:
        ok_label = default or buttons[-1]
        cancel_label = buttons[0] if len(buttons) > 1 else ""
        cmd = ["zenity", "--question", f"--title={title}", f"--text={message}",
               f"--ok-label={ok_label}"]
        if cancel_label:
            cmd.append(f"--cancel-label={cancel_label}")
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        return ok_label if result.returncode == 0 else cancel_label
    except FileNotFoundError:
        pass

    # Try kdialog
    try:
        cmd = ["kdialog", "--yesno", message, "--title", title]
        if default:
            cmd.extend(["--yes-label", default])
        result = subprocess.run(cmd, capture_output=True, timeout=15)
        return default or "OK" if result.returncode == 0 else "Отмена"
    except FileNotFoundError:
        pass

    # Terminal fallback
    print(f"\n[{title}] {message}")
    print(f"  [{', '.join(buttons)}]")
    choice = input(f"  > {default or buttons[-1]}: ").strip()
    return choice if choice else (default or buttons[-1])


def _windows_dialog(message: str, buttons: list[str], default: str = None,
                    title: str = "beckyup") -> str | None:
    """Show Windows dialog via PowerShell. Falls back to terminal."""
    if not _is_windows():
        return None

    # PowerShell popup
    try:
        btn_map = {b: i for i, b in enumerate(buttons)}
        default_btn = btn_map.get(default, 0)
        ps_code = (
            f'Add-Type -AssemblyName System.Windows.Forms; '
            f'$r = [System.Windows.Forms.MessageBox]::Show('
            f'"{message}", "{title}", '
            f'[System.Windows.Forms.MessageBoxButtons]::YesNo, '
            f'[System.Windows.Forms.MessageBoxIcon]::Question'
            f'); exit @{{"Yes"=0;"No"=1}}[$r]'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_code],
            capture_output=True, timeout=15
        )
        if result.returncode == 0:
            return "OK"
        return "Отмена"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Terminal fallback
    print(f"\n[{title}] {message}")
    print(f"  [{', '.join(buttons)}]")
    choice = input(f"  > {default or buttons[-1]}: ").strip()
    return choice if choice else (default or buttons[-1])


def _platform_dialog(message: str, buttons: list[str], default: str = None,
                     icon: str = "note", title: str = "beckyup",
                     hidden_answer: bool = False) -> str | None:
    """Route to the right platform dialog."""
    if _is_macos():
        return _osascript_dialog(message, buttons, default, icon, title, hidden_answer)
    if _is_linux():
        return _linux_dialog(message, buttons, default, title, hidden_answer)
    if _is_windows():
        return _windows_dialog(message, buttons, default, title)
    # Fallback
    print(f"\n[{title}] {message}")
    r = input(f"  > {default or buttons[-1]}: ").strip()
    return r or default or buttons[-1]


def _system_auth() -> bool:
    """Prompt for system password. Platform-specific."""
    if _is_macos():
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'do shell script "echo beckyup_auth_ok" with administrator privileges'],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    if _is_linux():
        try:
            result = subprocess.run(
                ["pkexec", "echo", "beckyup_auth_ok"],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # fallback: sudo with terminal
        try:
            result = subprocess.run(
                ["sudo", "echo", "beckyup_auth_ok"],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    if _is_windows():
        # Windows UAC via PowerShell
        try:
            ps_code = (
                'Start-Process cmd -Verb RunAs -ArgumentList '
                '"/c echo beckyup_auth_ok" | Out-Null; '
                'Write-Host "OK"'
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_code],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    return False


def _custom_auth(auth_hash: str) -> bool:
    """Prompt for custom password. Returns True if hash matches."""
    if _is_macos():
        pwd = _osascript_dialog(
            "Введи пароль для подтверждения бэкапа:",
            buttons=["Отмена", "OK"], default="OK",
            hidden_answer=True
        )
    else:
        print("\nВведи пароль для подтверждения бэкапа:")
        import getpass
        pwd = getpass.getpass("Пароль: ")

    if pwd is None or pwd == "":
        return False
    return bcrypt.checkpw(pwd.encode(), auth_hash.encode())


def hash_password(password: str) -> str:
    """Hash a custom password for storage."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def confirm_backup(drive_label: str, source_summary: str,
                   auth_mode: str, auth_hash: str = "") -> bool:
    """
    Show appropriate confirmation dialog based on auth mode.
    Returns True if user confirmed (and authenticated if needed).
    """
    message = f"Начинаем бэкап на {drive_label}?\n\nИсточники: {source_summary}"

    if auth_mode == "none":
        result = _platform_dialog(
            message, buttons=["Отмена", "Начать"], default="Начать",
            icon="note"
        )
        return result == "Начать"

    if auth_mode == "system":
        result = _platform_dialog(
            f"Требуется подтверждение для бэкапа на {drive_label}",
            buttons=["Отмена", "OK"], default="OK",
            icon="caution"
        )
        if result != "OK":
            return False
        return _system_auth()

    if auth_mode == "custom":
        return _custom_auth(auth_hash)

    return False


def setup_password(wizard_mode: bool = True) -> tuple[str, str]:
    """
    Interactive password setup. Returns (auth_mode, auth_hash).
    wizard_mode: if True, uses questionary. Otherwise uses platform dialogs.
    """
    platform_name = "macOS" if _is_macos() else "Linux" if _is_linux() else "Windows" if _is_windows() else "OS"

    if wizard_mode:
        import questionary
        choices = [
            "Без пароля — спрашивать каждый раз",
            "Без пароля — бэкапить автоматически",
        ]
        if _is_macos():
            choices.append("Пароль системы macOS")
        if _is_linux():
            choices.append(f"Пароль системы {platform_name}")
        if _is_windows():
            choices.append(f"Пароль системы {platform_name}")
        choices.append("Свой пароль")

        mode = questionary.select(
            f"Выбери способ подтверждения бэкапа ({platform_name}):",
            choices=choices
        ).ask()

        if mode == "Без пароля — бэкапить автоматически":
            return "none", ""
        if mode == "Без пароля — спрашивать каждый раз":
            return "none", ""
        if "Пароль системы" in (mode or ""):
            return "system", ""
        if mode == "Свой пароль":
            pwd1 = questionary.password("Придумай пароль:").ask()
            pwd2 = questionary.password("Повтори пароль:").ask()
            if pwd1 and pwd2 and pwd1 == pwd2 and len(pwd1) >= 4:
                return "custom", hash_password(pwd1)
            print("Пароль не подошёл (мин. 4 символа). Попробуй ещё раз.")
            return setup_password(wizard_mode=True)

    return "none", ""


def get_auto_confirm(auth_mode: str) -> bool:
    """auto_confirm only applies when auth_mode is 'none'."""
    return False
