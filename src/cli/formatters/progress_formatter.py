from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table


@contextmanager
def iteration_progress(console: Console, total: int) -> Iterator[Progress]:
    _ = total  # Available for caller to use with progress.add_task
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        yield progress


def format_iteration(console: Console, number: int, goal: str, decision: str) -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Label", style="dim")
    table.add_column("Value")

    table.add_row("Iteration", f"[bold]{number}[/]")
    table.add_row("Goal", goal)
    table.add_row("Decision", f"[cyan]{decision}[/]")

    console.print(table)


def format_check_results(console: Console, results: dict[str, Any]) -> None:
    table = Table(title="Check Results", show_lines=True)
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Duration")

    for check_name, result in results.items():
        status_style = "green" if result["status"] == "pass" else "red"
        table.add_row(
            check_name,
            f"[{status_style}]{result['status'].upper()}[/]",
            f"{result.get('duration_ms', 0)}ms",
        )

    console.print(table)


def format_budget_status(console: Console, budget: Any) -> None:
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(
            "Iterations",
            completed=budget.iteration_count,
            total=budget.max_iterations,
        )
