from pathlib import Path
from typing import Optional

from utils.ui import console

try:
    import questionary
except ImportError:
    questionary = None  # type: ignore


def _format_snapshots_table(snapshots: list[dict]) -> list[str]:
    """Format snapshots as human-readable list. Returns list of choice labels."""
    choices = []
    for i, s in enumerate(snapshots, 1):
        file_count = s.get("file_count", 0)
        total_size = s.get("total_size", 0)
        size_str = f"{total_size / (1024*1024):.1f} MB" if total_size > 0 else "\u2014"
        label = f"{i:>3}.  {s['created_at'][:19]}  {file_count:>6} files  {size_str}"
        choices.append(label)
    return choices


def pick_snapshot(snapshots: list[dict], drive_label: str) -> Optional[dict]:
    """Interactive snapshot picker. Returns selected snapshot dict or None."""
    if questionary is None:
        console.print("[red]questionary not installed. Run: pip install -r requirements.txt[/red]")
        return _fallback_pick(snapshots)
    if not snapshots:
        console.print("[yellow]\u041d\u0435\u0442 \u0441\u043d\u0435\u043f\u0448\u043e\u0442\u043e\u0432 \u043d\u0430 \u044d\u0442\u043e\u043c \u0434\u0438\u0441\u043a\u0435.[/yellow]")
        return None

    choices = _format_snapshots_table(snapshots)
    chosen = questionary.select(
        f"\u0421\u043d\u0435\u043f\u0448\u043e\u0442\u044b \u043d\u0430 {drive_label}:",
        choices=choices
    ).ask()
    if not chosen:
        return None
    idx = int(chosen.split(".")[0].strip()) - 1
    return snapshots[idx]


def pick_two_snapshots(snapshots: list[dict], drive_label: str
                       ) -> Optional[tuple[dict, dict]]:
    """Pick two snapshots A \u2192 B for diff. Returns (snap_a, snap_b) or None."""
    if questionary is None:
        console.print("[red]questionary not installed. Run: pip install -r requirements.txt[/red]")
        return None
    if len(snapshots) < 2:
        console.print("[yellow]\u041d\u0443\u0436\u043d\u043e \u043c\u0438\u043d\u0438\u043c\u0443\u043c 2 \u0441\u043d\u0435\u043f\u0448\u043e\u0442\u0430 \u0434\u043b\u044f \u0441\u0440\u0430\u0432\u043d\u0435\u043d\u0438\u044f.[/yellow]")
        return None

    choices = _format_snapshots_table(snapshots)
    a_label = questionary.select(
        f"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043f\u0435\u0440\u0432\u044b\u0439 \u0441\u043d\u0435\u043f\u0448\u043e\u0442 (A) \u043d\u0430 {drive_label}:",
        choices=choices
    ).ask()
    if not a_label:
        return None
    idx_a = int(a_label.split(".")[0].strip()) - 1

    b_label = questionary.select(
        f"\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0432\u0442\u043e\u0440\u043e\u0439 \u0441\u043d\u0435\u043f\u0448\u043e\u0442 (B) \u043d\u0430 {drive_label}:",
        choices=[c for i, c in enumerate(choices) if i != idx_a]
    ).ask()
    if not b_label:
        return None
    idx_b = int(b_label.split(".")[0].strip()) - 1

    return snapshots[idx_a], snapshots[idx_b]


def _fallback_pick(snapshots: list[dict]) -> Optional[dict]:
    """Fallback: print table and prompt for number."""
    if not snapshots:
        return None
    console.print("[yellow]questionary not available, using fallback picker[/yellow]")
    for i, s in enumerate(snapshots, 1):
        console.print(f"  {i:>3}.  {s['created_at'][:19]}")
    try:
        choice = input("\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043d\u043e\u043c\u0435\u0440: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(snapshots):
            return snapshots[idx]
    except (ValueError, IndexError):
        pass
    return None


def show_diff_result(diff: dict):
    """Display diff result in human-readable format."""
    added = diff.get("added", set())
    modified = diff.get("modified", set())
    deleted = diff.get("deleted", set())

    if added:
        console.print(f"[green]  ADDED ({len(added)}):[/green] {', '.join(sorted(added))}")
    if modified:
        console.print(f"[yellow]  MODIFIED ({len(modified)}):[/yellow] {', '.join(sorted(modified))}")
    if deleted:
        console.print(f"[red]  DELETED ({len(deleted)}):[/red] {', '.join(sorted(deleted))}")
    if not added and not modified and not deleted:
        console.print("[dim]  \u041d\u0435\u0442 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0439[/dim]")
