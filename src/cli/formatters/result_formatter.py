from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from src.application.dto.final_result import FinalResult
from src.cli.theme import theme
from src.domain.value_objects.condition_enums import CheckStatus
from src.domain.value_objects.task_status import TaskStatus


def format_result(console: Console, result: FinalResult) -> None:
    if result.status == TaskStatus.DONE:
        console.print(f"\n[{theme.STATUS_DONE}]✅ Task Complete![/]")
        if result.summary:
            console.print(f"\n[{theme.HEADER}]What was done:[/]")
            console.print(f"   {result.summary}")
        console.print()
    elif result.status == TaskStatus.BLOCKED:
        console.print(f"\n[{theme.STATUS_BLOCKED}]❌ Task Blocked[/]")
        if result.blocked_reason:
            console.print(f"[{theme.ERROR}]   {result.blocked_reason}[/]")
        console.print()
    elif result.status == TaskStatus.STOPPED:
        console.print(f"\n[{theme.STATUS_STOPPED}]⏸️  Task Stopped[/]")
        if result.stopped_reason:
            console.print(f"[{theme.WARNING}]   {result.stopped_reason}[/]")
        console.print()

    console.print(f"[{theme.HEADER}]📝 Summary:[/] {result.summary}")

    if result.conditions:
        console.print(f"\n[{theme.HEADER}]✓ Conditions:[/]")
        passed = sum(1 for c in result.conditions if c.check_status == CheckStatus.PASS)
        total = len(result.conditions)
        console.print(f"   {passed}/{total} conditions passed")

        # Show failed conditions if any
        failed = [c for c in result.conditions if c.check_status != CheckStatus.PASS]
        if failed:
            console.print(f"\n[{theme.WARNING}]   Failed conditions:[/]")
            for cond in failed:
                console.print(f"   • {cond.description[:60]}")

    if result.diff:
        # Count changed files and lines
        diff_lines = result.diff.split("\n")
        file_count = sum(1 for line in diff_lines if line.startswith("diff --git"))
        added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        removed = sum(
            1 for line in diff_lines if line.startswith("-") and not line.startswith("---")
        )

        console.print(f"\n[{theme.HEADER}]📁 Changes:[/] {file_count} files")
        console.print(f"   [{theme.DIFF_ADD}]+{added}[/] [{theme.DIFF_REMOVE}]-{removed}[/] lines")

        # Show preview only if not too long
        if len(diff_lines) <= 30:
            diff_preview = "\n".join(diff_lines)
            syntax = Syntax(diff_preview, "diff", theme="monokai", line_numbers=False)
            console.print(syntax)
        else:
            console.print(f"[{theme.DIM}]   (run 'git diff' to see full changes)[/]")


def format_blocked_instructions(console: Console, result: FinalResult) -> None:
    if result.status != TaskStatus.BLOCKED:
        return

    task_id_short = result.task_id.hex[:8]
    panel = Panel(
        f"""[{theme.HEADER}]Task is blocked.[/]

Reason: {result.blocked_reason or "Unknown"}

To continue:
1. Address the blocking issue
2. Run: [{theme.INFO}]proofloop task resume {task_id_short}[/]

Or with auto-approve:
  [{theme.INFO}]proofloop task resume {task_id_short} --auto-approve[/]
""",
        title="Blocked",
        border_style=theme.BORDER_ERROR,
    )
    console.print(panel)


def format_stopped_instructions(console: Console, result: FinalResult) -> None:
    if result.status != TaskStatus.STOPPED:
        return

    task_id_short = result.task_id.hex[:8]
    panel = Panel(
        f"""[{theme.HEADER}]Task was stopped.[/]

Reason: {result.stopped_reason or "Budget exhausted"}

Options:
1. Review and adjust conditions
2. Check if the task needs to be broken into smaller steps

To resume:
  [{theme.INFO}]proofloop task resume {task_id_short}[/]

Or with auto-approve:
  [{theme.INFO}]proofloop task resume {task_id_short} --auto-approve[/]
""",
        title="Stopped",
        border_style=theme.BORDER_WARNING,
    )
    console.print(panel)
