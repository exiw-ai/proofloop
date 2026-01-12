import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from src.cli.theme import theme
from src.infrastructure.git.repo_root import get_default_state_dir
from src.infrastructure.persistence.json_task_repo import JsonTaskRepo

console = Console()


def list_all_tasks(
    state_dir: Path | None = typer.Option(None, "--state-dir", help="State directory"),
) -> None:
    """List all tasks."""
    asyncio.run(_list_tasks(state_dir))


async def _list_tasks(state_dir: Path | None) -> None:
    if state_dir is None:
        state_dir = await get_default_state_dir()

    repo = JsonTaskRepo(state_dir)
    task_ids = await repo.list_tasks()

    if not task_ids:
        console.print(f"[{theme.DIM}]No tasks found[/]")
        return

    table = Table(title="Tasks")
    table.add_column("ID", style=theme.INFO)
    table.add_column("Description")
    table.add_column("Workspace", style=theme.DIM)
    table.add_column("Status")

    for tid in task_ids:
        task = await repo.load(tid)
        if task:
            workspace = str(task.workspace_path.name) if task.workspace_path else "-"
            table.add_row(
                str(tid),
                task.description[:50],
                workspace,
                task.status.value,
            )

    console.print(table)
