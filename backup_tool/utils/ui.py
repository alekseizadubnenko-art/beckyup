from pathlib import Path

_has_rich = False
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    _has_rich = True
except ImportError:
    class _FallbackConsole:
        def print(self, *args, **kwargs):
            text = args[0] if args else ""
            import re
            clean = re.sub(r'\[/?\w+(?:=.*?)?\]', '', str(text))
            clean = clean.strip()
            if clean:
                print(clean)

    console = _FallbackConsole()

LOGO = r"""
    __              __
   / /_  ___  _____/ /____  ____  ______
  / __ \/ _ \/ ___/ //_/ / / / / / / __ \
 / /_/ /  __/ /__/ ,< / /_/ / /_/ / /_/ /
/_.___/\___/\___/_/|_|\__, /\__,_/ .___/
                     /____/     /_/
"""


def show_banner():
    if _has_rich:
        console.print(Panel(LOGO, style="bold cyan", border_style="bright_blue"), justify="center")
    else:
        console.print("=== BECKYUP ===")
    console.print()


def show_startup(config_path=None):
    show_banner()
    if config_path:
        console.print(f"[blue]*[/blue] Config: {config_path}")
    console.print("[green]*[/green] Monitoring started. Press Ctrl+C to exit.")


def show_backup_result(stats: dict):
    if "error" in stats:
        console.print(f"\n[red]ERROR: {stats['error']}[/red]\n")
        return

    copied = stats.get("total_copied", 0)
    skipped = stats.get("total_skipped", 0)
    errors = stats.get("total_errors", 0)

    if _has_rich:
        table = Table(show_header=False, border_style="bright_blue", box=None)
        table.add_column(style="bold")
        table.add_column()
        table.add_row("Copied", f"[green]{copied}[/green] files")
        if skipped:
            table.add_row("Skipped", f"[yellow]{skipped}[/yellow] files")
        if errors:
            table.add_row("Errors", f"[red]{errors}[/red]")
        table.add_row("Status", "[green]OK[/green]" if not errors else "[yellow]With errors[/yellow]")
        console.print()
        console.print(Panel(table, title="[bold]Backup complete[/bold]", border_style="bright_blue"))
    else:
        print(f"\nBackup complete: {copied} copied, {skipped} skipped, {errors} errors\n")


def print_info(msg: str):
    console.print(f"[blue]*[/blue] {msg}")


def print_ok(msg: str):
    console.print(f"[green]*[/green] {msg}")


def print_warn(msg: str):
    console.print(f"[yellow]*[/yellow] {msg}")


def print_error(msg: str):
    console.print(f"[red]*[/red] {msg}")
