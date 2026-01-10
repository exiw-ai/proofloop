from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from src.application.dto.final_result import FinalResult
from src.domain.value_objects.condition_enums import CheckStatus
from src.domain.value_objects.task_status import TaskStatus


def format_result(console: Console, result: FinalResult) -> None:
    if result.status == TaskStatus.DONE:
        console.print("\n[bold green]✅ Task Complete![/]")
        console.print()
    elif result.status == TaskStatus.BLOCKED:
        console.print("\n[bold red]❌ Task Blocked[/]")
        if result.blocked_reason:
            console.print(f"[red]   {result.blocked_reason}[/]")
        console.print()
    elif result.status == TaskStatus.STOPPED:
        console.print("\n[bold yellow]⏸️  Task Stopped[/]")
        if result.stopped_reason:
            console.print(f"[yellow]   {result.stopped_reason}[/]")
        console.print()

    console.print(f"[bold]📝 Summary:[/] {result.summary}")

    if result.conditions:
        console.print("\n[bold]✓ Conditions:[/]")
        passed = sum(1 for c in result.conditions if c.check_status == CheckStatus.PASS)
        total = len(result.conditions)
        console.print(f"   {passed}/{total} conditions passed")

        # Show failed conditions if any
        failed = [c for c in result.conditions if c.check_status != CheckStatus.PASS]
        if failed:
            console.print("\n[yellow]   Failed conditions:[/]")
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

        console.print(f"\n[bold]📁 Changes:[/] {file_count} files")
        console.print(f"   [green]+{added}[/] [red]-{removed}[/] lines")

        # Show preview only if not too long
        if len(diff_lines) <= 30:
            diff_preview = "\n".join(diff_lines)
            syntax = Syntax(diff_preview, "diff", theme="monokai", line_numbers=False)
            console.print(syntax)
        else:
            console.print("[dim]   (run 'git diff' to see full changes)[/]")

    if result.evidence_refs:
        console.print(f"\n[dim]📎 Evidence: {len(result.evidence_refs)} artifacts[/]")


def format_blocked_instructions(console: Console, result: FinalResult) -> None:
    if result.status != TaskStatus.BLOCKED:
        return

    task_id_short = result.task_id.hex[:8]
    panel = Panel(
        f"""[bold]Task is blocked.[/]

Reason: {result.blocked_reason or "Unknown"}

To continue:
1. Address the blocking issue
2. Run: [cyan]proofloop task resume {task_id_short}[/]

Or with auto-approve:
  [cyan]proofloop task resume {task_id_short} --auto-approve[/]
""",
        title="Blocked",
        border_style="red",
    )
    console.print(panel)


def format_stopped_instructions(console: Console, result: FinalResult) -> None:
    if result.status != TaskStatus.STOPPED:
        return

    task_id_short = result.task_id.hex[:8]
    panel = Panel(
        f"""[bold]Task was stopped.[/]

Reason: {result.stopped_reason or "Budget exhausted"}

Options:
1. Increase timeout: [cyan]--timeout 120[/]
2. Increase iterations: modify TaskInput
3. Review and adjust conditions

To resume with more budget:
  [cyan]proofloop task resume {task_id_short} --timeout 120[/]
""",
        title="Stopped",
        border_style="yellow",
    )
    console.print(panel)
