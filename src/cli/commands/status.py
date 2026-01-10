import asyncio
from pathlib import Path
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

from src.infrastructure.git.repo_root import get_default_state_dir
from src.infrastructure.persistence.json_task_repo import JsonTaskRepo

console = Console()


def task_status(
    task_id: str = typer.Argument(..., help="Task ID"),
    state_dir: Path | None = typer.Option(None, "--state-dir", help="State directory"),
) -> None:
    """Show task status."""
    asyncio.run(_show_status(UUID(task_id), state_dir))


async def _show_status(task_id: UUID, state_dir: Path | None) -> None:
    if state_dir is None:
        state_dir = await get_default_state_dir()

    repo = JsonTaskRepo(state_dir)
    task = await repo.load(task_id)

    if not task:
        console.print(f"[bold red]Task not found:[/] {task_id}")
        raise typer.Exit(1)

    table = Table(title=f"Task {task_id.hex[:8]}")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Description", task.description)
    table.add_row("Status", task.status.value)
    table.add_row("Iterations", str(len(task.iterations)))
    table.add_row("Conditions", str(len(task.conditions)))

    console.print(table)
