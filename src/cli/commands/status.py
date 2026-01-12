import asyncio
from pathlib import Path
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

from src.cli.theme import theme
from src.infrastructure.git.repo_root import get_default_state_dir
from src.infrastructure.persistence.json_task_repo import JsonTaskRepo

console = Console()


async def resolve_task_id(task_id_str: str, repo: JsonTaskRepo) -> UUID | None:
    """Resolve a task ID string to a full UUID.

    Supports both full UUIDs and short prefixes (minimum 4 characters).
    Returns None if not found or ambiguous.
    """
    # Try parsing as full UUID first
    try:
        return UUID(task_id_str)
    except ValueError:
        pass

    # Try prefix matching
    task_id_str = task_id_str.lower().replace("-", "")
    if len(task_id_str) < 4:
        console.print(f"[{theme.ERROR}]Task ID prefix must be at least 4 characters[/]")
        return None

    task_ids = await repo.list_tasks()
    matches = [tid for tid in task_ids if tid.hex.startswith(task_id_str)]

    if len(matches) == 0:
        console.print(f"[{theme.ERROR}]No task found with prefix: {task_id_str}[/]")
        return None
    elif len(matches) > 1:
        console.print(
            f"[{theme.ERROR}]Ambiguous prefix '{task_id_str}' matches {len(matches)} tasks:[/]"
        )
        for m in matches[:5]:
            console.print(f"  [{theme.DIM}]{m}[/]")
        if len(matches) > 5:
            console.print(f"  [{theme.DIM}]...and {len(matches) - 5} more[/]")
        return None

    return matches[0]


def task_status(
    task_id: str = typer.Argument(..., help="Task ID (full or short prefix)"),
    state_dir: Path | None = typer.Option(None, "--state-dir", help="State directory"),
) -> None:
    """Show task status."""
    asyncio.run(_show_status(task_id, state_dir))


async def _show_status(task_id_str: str, state_dir: Path | None) -> None:
    if state_dir is None:
        state_dir = await get_default_state_dir()

    repo = JsonTaskRepo(state_dir)

    task_id = await resolve_task_id(task_id_str, repo)
    if task_id is None:
        raise typer.Exit(1)

    task = await repo.load(task_id)

    if not task:
        console.print(f"[{theme.ERROR_BOLD}]Task not found:[/] {task_id}")
        raise typer.Exit(1)

    table = Table(title=f"Task {task_id.hex[:8]}")
    table.add_column("Property", style=theme.INFO)
    table.add_column("Value")

    table.add_row("Description", task.description)
    table.add_row("Status", task.status.value)
    table.add_row("Workspace", str(task.workspace_path) if task.workspace_path else "-")
    table.add_row("Iterations", str(len(task.iterations)))
    table.add_row("Conditions", str(len(task.conditions)))

    console.print(table)
