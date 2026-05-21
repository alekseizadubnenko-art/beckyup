import questionary
from pathlib import Path
from utils.ui import show_banner, console
from utils.auth import setup_password, get_auto_confirm
from utils.launchagent import install as install_agent, is_installed


def _select_source_dirs() -> list[Path]:
    """Interactive selection of source directories."""
    sources = []
    home = Path.home()

    # Step 1a: common home folders
    common_names = ["Desktop", "Documents", "Downloads", "Projects", "Pictures", "Music", "Movies"]
    common = [p for p in common_names if (home / p).exists()]
    other = sorted([
        p for p in home.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in common_names
    ])
    all_choices = [str(home / c) for c in common] + [str(p) for p in other]

    console.print("[bold]Шаг 1:[/bold] выбери папки для бэкапа")
    selected = questionary.checkbox(
        "Какие папки бэкапить? (Space — выбрать, Enter — продолжить)",
        choices=all_choices
    ).ask()
    if selected:
        sources.extend(Path(s) for s in selected)

    # Step 1b: add custom paths
    add_more = questionary.confirm("Добавить папку из другого места?", default=False).ask()
    while add_more:
        custom = questionary.path("Путь к папке:").ask()
        if custom:
            p = Path(custom)
            if p.exists() and p.is_dir():
                sources.append(p)
                console.print(f"[green]✓[/green] Добавлено: {p}")
            else:
                console.print("[red]Папка не найдена[/red]")
        add_more = questionary.confirm("Добавить ещё?", default=False).ask()

    # Step 1c: file type filter
    console.print("\n[bold]Фильтр:[/bold] какие файлы бэкапить?")
    file_mode = questionary.select(
        "Типы файлов:",
        choices=[
            "Все файлы",
            "Только документы (pdf, doc, txt, md)",
            "Только изображения (jpg, png, gif)",
            "Только код (py, js, ts, go, rs, sh)",
            "Архивы (zip, tar, gz, rar)",
            "Свои расширения",
        ]
    ).ask()

    ext_map = {
        "Все файлы": ["*"],
        "Только документы (pdf, doc, txt, md)": ["*.pdf", "*.doc", "*.docx", "*.txt", "*.md"],
        "Только изображения (jpg, png, gif)": ["*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp"],
        "Только код (py, js, ts, go, rs, sh)": ["*.py", "*.js", "*.ts", "*.go", "*.rs", "*.sh"],
        "Архивы (zip, tar, gz, rar)": ["*.zip", "*.tar", "*.gz", "*.rar"],
    }
    if file_mode in ext_map:
        extensions = ext_map[file_mode]
    else:
        raw = questionary.text("Расширения через запятую (например .txt,.pdf,.md):").ask()
        extensions = [f"*{e.strip()}" if not e.strip().startswith("*") else e.strip()
                      for e in (raw or "").split(",") if e.strip()]
        if not extensions:
            extensions = ["*"]

    return sources, extensions


def run_wizard(config_manager, backup_engine) -> bool:
    """Run the first-time setup wizard. Returns True if config was saved."""
    show_banner()
    console.print("[bold]Добро пожаловать![/bold] Настроим бэкап за пару минут.\n")

    sources, extensions = _select_source_dirs()
    backup_engine.source_directories = sources
    config_manager.set("backup.file_extensions", extensions)

    # Step 2: Detect backup drive
    console.print("\n[bold]Шаг 2:[/bold] настрой бэкап-диск")
    from core.device_detector import DeviceDetector
    detector = DeviceDetector()
    drives = detector.get_mounted_devices()
    if drives:
        console.print("Найдены диски:")
        for path, label, uuid in drives:
            console.print(f"  {label} — {path} ({uuid})")
        choices = [f"{label} ({uuid})" for _, label, uuid in drives]
        chosen = questionary.select(
            "Выбери бэкап-диск:",
            choices=choices
        ).ask()
        if chosen:
            chosen_uuid = chosen.split("(")[1].rstrip(")") if "(" in chosen else ""
            chosen_label = chosen.split(" (")[0]
            config_manager.add_known_uuid(chosen_uuid, chosen_label)
    else:
        console.print("[yellow]Диски не найдены.[/yellow] Подключи флешку и запусти настройку позже: [bold]beckyup --wizard[/bold]")

    # Step 3: Security
    console.print("\n[bold]Шаг 3:[/bold] безопасность")
    auth_mode, auth_hash = setup_password(wizard_mode=True)
    config_manager.set_auth_mode(auth_mode)
    if auth_hash:
        config_manager.set_auth_hash(auth_hash)
    config_manager.set_auto_confirm(get_auto_confirm(auth_mode))

    # Step 4: Autostart
    console.print("\n[bold]Шаг 4:[/bold] автозапуск")
    auto_start = questionary.confirm(
        "Запускать beckyup автоматически при входе в систему?",
        default=True
    ).ask()
    if auto_start:
        ok, msg = install_agent(str(Path(__file__).parent.parent))
        if ok:
            console.print(f"[green]{msg}[/green]")
        else:
            console.print(f"[red]{msg}[/red]")
    else:
        console.print("\nЧтобы запустить beckyup вручную:")
        console.print("  [bold]cd backup_tool && uv run python main.py[/bold]\n")

    # Save
    config_manager.set("backup.source_directories", [str(p) for p in backup_engine.source_directories])
    config_manager.save_config()
    console.print("\n[bold green]✓ Конфигурация сохранена. Готов к работе![/bold green]\n")
    return True
