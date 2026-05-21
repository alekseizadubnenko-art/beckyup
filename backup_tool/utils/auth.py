import subprocess
import bcrypt
from pathlib import Path


def _osascript_dialog(message: str, buttons: list[str], default: str = None,
                      icon: str = "note", title: str = "beckyup",
                      hidden_answer: bool = False, extra: str = None) -> str | None:
    """Show macOS native dialog via osascript. Returns button text or None."""
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


def _system_auth() -> bool:
    """Prompt for macOS system password. Returns True if authenticated."""
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'do shell script "echo beckyup_auth_ok" with administrator privileges'],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _custom_auth(auth_hash: str) -> bool:
    """Prompt for custom password. Returns True if hash matches."""
    pwd = _osascript_dialog(
        "Введи пароль для подтверждения бэкапа:",
        buttons=["Отмена", "OK"], default="OK",
        hidden_answer=True
    )
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
        result = _osascript_dialog(
            message, buttons=["Отмена", "Начать"], default="Начать",
            icon="note"
        )
        return result == "Начать"

    if auth_mode == "system":
        # First explain, then auth
        result = _osascript_dialog(
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
    wizard_mode: if True, uses questionary. Otherwise uses osascript dialogs.
    """
    if wizard_mode:
        import questionary
        mode = questionary.select(
            "Выбери способ подтверждения бэкапа:",
            choices=[
                "Без пароля — спрашивать каждый раз",
                "Без пароля — бэкапить автоматически",
                "Пароль системы macOS",
                "Свой пароль",
            ]
        ).ask()

        if mode == "Без пароля — бэкапить автоматически":
            return "none", ""
        if mode == "Без пароля — спрашивать каждый раз":
            return "none", ""
        if mode == "Пароль системы macOS":
            return "system", ""
        if mode == "Свой пароль":
            pwd1 = questionary.password("Придумай пароль:").ask()
            pwd2 = questionary.password("Повтори пароль:").ask()
            if pwd1 and pwd2 and pwd1 == pwd2 and len(pwd1) >= 4:
                return "custom", hash_password(pwd1)
            print("Пароль не подошёл (мин. 4 символа). Попробуй ещё раз.")
            return setup_password(wizard_mode=True)  # retry

    return "none", ""


def get_auto_confirm(auth_mode: str) -> bool:
    """auto_confirm only applies when auth_mode is 'none'."""
    return False
