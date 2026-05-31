#!/usr/bin/env python3
"""
Экстренный бэкап важных данных
Главный модуль приложения
"""

import sys
import signal
import argparse
from pathlib import Path
from typing import Optional
from core.backup_engine import BackupEngine
from core.device_monitor import DeviceMonitor
from config.manager import ConfigManager
from utils.logger import setup_logger
from utils.ui import show_banner, show_startup, show_backup_result, print_error, console

try:
    from __init__ import __version__
except ImportError:
    __version__ = "0.0.0"


backup_engine = None
device_monitor = None
config_manager = None


def signal_handler(signum, frame):
    print_error("\nПолучен сигнал завершения.")
    shutdown()
    sys.exit(0)


def shutdown():
    global device_monitor
    if device_monitor:
        device_monitor.stop_monitoring()
    console.print("[dim]Приложение остановлено.[/dim]")


def _get_detected_drive() -> Optional[Path]:
    """Find a mounted known backup drive. Returns mount path or None."""
    from core.device_detector import DeviceDetector
    detector = DeviceDetector()
    devices = detector.get_mounted_devices()
    for mount_path, label, uuid in devices:
        c = ConfigManager()
        known = c.get_known_uuids()
        if uuid in known:
            return Path(mount_path)
    return None


def cmd_snapshots():
    """List snapshots on connected backup drive."""
    drive = _get_detected_drive()
    if not drive:
        print_error("Подключи знакомую бэкап-флешку.")
        return
    from core.snapshot import SnapshotManager
    from cli.snapshot_ui import pick_snapshot, show_diff_result, pick_two_snapshots
    store = drive / ".beckyup"
    mgr = SnapshotManager(store)
    snaps = mgr.list_snapshots()
    if not snaps:
        console.print("[yellow]Нет снепшотов на этом диске.[/yellow]")
        return
    console.print(f"[bold]Снепшоты на {drive}[/bold]")
    import questionary
    while True:
        choices = [
            *[f"{i+1:>3}.  {s['created_at'][:19]}  {s['file_count']:>6} files  {s['total_size']/(1024*1024):.1f} MB"
              for i, s in enumerate(snaps)],
            questionary.Separator(),
            "[D] Diff",
            "[R] Restore",
            "[V] Verify",
            "[Q] Выход",
        ]
        action = questionary.select(
            f"Снепшоты на {drive.name}:",
            choices=choices
        ).ask()
        if not action or action == "[Q] Выход":
            break
        if action == "[D] Diff":
            pair = pick_two_snapshots(snaps, drive.name)
            if pair:
                m1 = mgr.load_manifest(pair[0]["path"])
                m2 = mgr.load_manifest(pair[1]["path"])
                diff = mgr.diff(m1, m2)
                console.print(f"\n[bold]Изменения {pair[0]['created_at'][:10]} \u2192 {pair[1]['created_at'][:10]}:[/bold]")
                show_diff_result(diff)
        elif action == "[R] Restore":
            snap = pick_snapshot(snaps, drive.name)
            if snap:
                m = mgr.load_manifest(snap["path"])
                default_dest = str(Path.home() / "beckyup_restore" / snap["id"])
                dest_str = questionary.text("Куда восстановить?", default=default_dest).ask()
                if dest_str:
                    dest = Path(dest_str)
                    dest.mkdir(parents=True, exist_ok=True)
                    mgr.restore(m, store / "blobs", dest)
                    console.print(f"[green]\u2713 Восстановлено в {dest}[/green]")
        elif action == "[V] Verify":
            snap = pick_snapshot(snaps, drive.name)
            if snap:
                m = mgr.load_manifest(snap["path"])
                result = mgr.verify(m, store / "blobs", store / "verify-key")
                if result["valid"]:
                    console.print(f"[green]\u2713 {result['checked']} файлов целы[/green]")
                else:
                    console.print(f"[red]\u2717 {len(result['errors'])} ошибок[/red]")


def cmd_restore():
    """Interactive restore from snapshot."""
    drive = _get_detected_drive()
    if not drive:
        print_error("Подключи знакомую бэкап-флешку.")
        return
    from core.snapshot import SnapshotManager
    from cli.snapshot_ui import pick_snapshot
    store = drive / ".beckyup"
    mgr = SnapshotManager(store)
    snaps = mgr.list_snapshots()
    snap = pick_snapshot(snaps, drive.name)
    if not snap:
        return
    m = mgr.load_manifest(snap["path"])
    default_dest = str(Path.home() / "beckyup_restore" / snap["id"])
    import questionary
    dest_str = questionary.text("Куда восстановить?", default=default_dest).ask()
    if dest_str:
        dest = Path(dest_str)
        dest.mkdir(parents=True, exist_ok=True)
        mgr.restore(m, store / "blobs", dest)
        console.print(f"[green]\u2713 Восстановлено в {dest}[/green]")


def cmd_diff():
    """Interactive diff between two snapshots."""
    drive = _get_detected_drive()
    if not drive:
        print_error("Подключи знакомую бэкап-флешку.")
        return
    from core.snapshot import SnapshotManager
    from cli.snapshot_ui import pick_two_snapshots, show_diff_result
    store = drive / ".beckyup"
    mgr = SnapshotManager(store)
    snaps = mgr.list_snapshots()
    pair = pick_two_snapshots(snaps, drive.name)
    if pair:
        m1 = mgr.load_manifest(pair[0]["path"])
        m2 = mgr.load_manifest(pair[1]["path"])
        diff = mgr.diff(m1, m2)
        console.print(f"\n[bold]Изменения {pair[0]['created_at'][:10]} \u2192 {pair[1]['created_at'][:10]}:[/bold]")
        show_diff_result(diff)


def cmd_verify():
    """Verify integrity of latest snapshot."""
    drive = _get_detected_drive()
    if not drive:
        print_error("Подключи знакомую бэкап-флешку.")
        return
    from core.snapshot import SnapshotManager
    from cli.snapshot_ui import pick_snapshot
    store = drive / ".beckyup"
    mgr = SnapshotManager(store)
    snaps = mgr.list_snapshots()
    snap = pick_snapshot(snaps, drive.name)
    if not snap:
        return
    m = mgr.load_manifest(snap["path"])
    result = mgr.verify(m, store / "blobs", store / "verify-key")
    if result["valid"]:
        console.print(f"[green]\u2713 {result['checked']} файлов целы, подпись верна[/green]")
    else:
        console.print(f"[red]\u2717 {len(result['errors'])} ошибок целостности[/red]")


def main():
    global backup_engine, device_monitor, config_manager

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description="Экстренный бэкап важных данных")
    parser.add_argument("--source", help="Исходная директория для одноразового бэкапа")
    parser.add_argument("--destination", help="Директория назначения для одноразового бэкапа")
    parser.add_argument("--config", help="Путь к файлу конфигурации", default=None)
    parser.add_argument("--wizard", action="store_true", help="Запустить настройку заново")
    parser.add_argument("--backup", action="store_true", help="Запустить бэкап со снепшотами")
    parser.add_argument("--snapshots", action="store_true", help="Показать список снепшотов")
    parser.add_argument("--restore", action="store_true", help="Восстановить из снепшота")
    parser.add_argument("--diff", action="store_true", help="Сравнить два снепшота")
    parser.add_argument("--verify", action="store_true", help="Проверить целостность снепшота")
    parser.add_argument("--version", action="store_true", help="Показать версию")
    args = parser.parse_args()

    if args.version:
        console.print(f"beckyup v{__version__}")
        return

    logger = setup_logger()
    logger.info("Запуск экстренного бэкапа важных данных")

    try:
        if args.snapshots:
            cmd_snapshots()
            return
        if args.restore:
            cmd_restore()
            return
        if args.diff:
            cmd_diff()
            return
        if args.verify:
            cmd_verify()
            return
        if args.backup:
            show_banner()
            backup_engine = BackupEngine(args.config)
            stats = backup_engine.run_backup()
            show_backup_result(stats)
            logger.info(f"Бэкап завершен: {stats}")
            return

        if args.source and args.destination:
            logger.info("Запуск одноразового бэкапа")
            show_banner()
            backup_engine = BackupEngine(args.config)
            dest = Path(args.destination)
            dest.mkdir(parents=True, exist_ok=True)
            backup_engine.source_directories = [Path(args.source)]
            backup_engine.destination_path = dest
            stats = backup_engine.run_backup()
            console.print(f"[bold]Источник:[/bold] {args.source}")
            console.print(f"[bold]Назначение:[/bold] {args.destination}")
            show_backup_result(stats)
            logger.info(f"Одноразовый бэкап завершен: {stats}")
            return

        config_manager = ConfigManager()

        if args.wizard or not config_manager.config_file.exists():
            try:
                from cli.wizard import run_wizard
                backup_engine = BackupEngine(args.config)
                run_wizard(config_manager, backup_engine)
            except ImportError:
                logger.error("questionary не установлен. Выполни: pip install -r requirements.txt")
                sys.exit(1)
            if args.wizard:
                return

        drive_path = _get_detected_drive()
        if drive_path and not args.wizard and not args.source:
            console.print(f"[dim]Флешка {drive_path.name} подключена. "
                          f"Используй --snapshots для управления снепшотами.[/dim]")

        logger.info("Запуск в режиме мониторинга")
        backup_engine = BackupEngine(args.config)
        from core.device_detector import DeviceDetector
        detector = DeviceDetector()
        device_monitor = DeviceMonitor(backup_engine, detector=detector)

        def on_device_connected(device_path):
            logger.info(f"Обнаружено новое устройство: {device_path}")

        device_monitor.add_callback(on_device_connected)
        device_monitor.start_monitoring()

        logger.info("Приложение запущено и готово к работе")
        show_startup(str(config_manager.config_file) if config_manager else None)

        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки от пользователя")
        finally:
            shutdown()

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        print_error(f"Критическая ошибка: {e}")
        shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()
