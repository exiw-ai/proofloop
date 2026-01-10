from pathlib import Path
from uuid import UUID, uuid4

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from src.application.dto.task_input import TaskInput
from src.application.orchestrator import Orchestrator
from src.application.use_cases.select_mcp_servers import MCPSuggestion
from src.cli.formatters.result_formatter import format_result
from src.cli.formatters.stage_formatter import (
    format_conditions,
    format_plan,
    format_research_stage_complete,
    format_research_stage_header,
    format_stage_complete,
    format_stage_header,
)
from src.cli.formatters.tool_formatter import create_tool_callback
from src.cli.mcp.ui import interactive_mcp_selection
from src.domain.entities.condition import Condition
from src.domain.entities.plan import Plan
from src.domain.value_objects.agent_provider import AgentProvider
from src.domain.value_objects.clarification import (
    ClarificationAnswer,
    ClarificationQuestion,
)
from src.domain.value_objects.condition_enums import ConditionRole
from src.infrastructure.agent.agent_factory import create_agent
from src.infrastructure.checks.command_check_runner import CommandCheckRunner
from src.infrastructure.git.git_diff_adapter import GitDiffAdapter
from src.infrastructure.git.repo_root import get_default_state_dir
from src.infrastructure.mcp.registry import get_default_registry
from src.infrastructure.persistence.json_task_repo import JsonTaskRepo
from src.infrastructure.verification.project_analyzer import ProjectAnalyzer

console = Console()


def interactive_clarifications(
    questions: list[ClarificationQuestion],
) -> list[ClarificationAnswer]:
    """Show clarification questions to user and collect answers.

    Returns list of answers (one per question).
    """
    if not questions:
        return []

    console.print("\n[bold cyan]═══ CLARIFICATION NEEDED ═══[/]")
    console.print("[dim]The agent has some questions before creating the plan.[/]\n")

    answers: list[ClarificationAnswer] = []

    for q in questions:
        # Show question with context
        console.print(f"[bold]{q.question}[/]")
        if q.context:
            console.print(f"[dim]{q.context}[/]")
        console.print()

        # Show options as table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="cyan", width=6)
        table.add_column("Label", style="bold")
        table.add_column("Description", style="dim")

        for i, opt in enumerate(q.options, 1):
            table.add_row(f"[{i}]", opt.label, opt.description)

        console.print(table)
        console.print("  [c] Custom answer")
        console.print()

        # Get user choice
        while True:
            choice = console.input("[bold]Your choice:[/] ").strip().lower()

            if choice == "c":
                custom_value = console.input("[cyan]Enter your answer:[/] ").strip()
                answers.append(
                    ClarificationAnswer(
                        question_id=q.id,
                        selected_option="custom",
                        custom_value=custom_value,
                    )
                )
                break
            elif choice == "auto" or choice == "a":
                answers.append(
                    ClarificationAnswer(
                        question_id=q.id,
                        selected_option="_auto",
                    )
                )
                break
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(q.options):
                    selected = q.options[idx]
                    answers.append(
                        ClarificationAnswer(
                            question_id=q.id,
                            selected_option=selected.key,
                        )
                    )
                    break
                else:
                    console.print("[red]Invalid choice. Try again.[/]")
            elif choice == "":
                # Default to "auto" if user presses Enter
                answers.append(
                    ClarificationAnswer(
                        question_id=q.id,
                        selected_option="_auto",
                    )
                )
                break
            else:
                # Try to match by key directly
                matching = [opt for opt in q.options if opt.key.lower() == choice]
                if matching:
                    answers.append(
                        ClarificationAnswer(
                            question_id=q.id,
                            selected_option=matching[0].key,
                        )
                    )
                    break
                console.print("[red]Invalid choice. Enter number, 'c' for custom, or 'auto'.[/]")

        console.print()

    return answers


def interactive_conditions_editor(
    conditions: list[Condition],
) -> list[Condition]:
    """Interactive editor for conditions. Allows adding, editing, and deleting
    conditions.

    Returns the modified list of conditions.
    """
    working_conditions = list(conditions)  # Make a copy

    while True:
        console.print("\n[bold cyan]═══ CONDITIONS EDITOR ═══[/]")
        format_conditions(console, working_conditions)

        console.print("\n[bold]Options:[/]")
        if not working_conditions:
            console.print("  [bold cyan]a[/]    - Add new condition [bold](recommended)[/]")
            console.print("  [dim]done[/] - Finish editing (no conditions)")
        else:
            console.print("  [green]done[/] - Finish editing")
            console.print("  [cyan]a[/]    - Add new condition")
            console.print("  [yellow]e N[/]  - Edit condition N (e.g., 'e 1')")
            console.print("  [red]d N[/]  - Delete condition N (e.g., 'd 1')")
            console.print("  [magenta]t N[/]  - Toggle role of condition N (blocking ↔ signal)")
        console.print()

        choice = console.input("[bold]Your choice:[/] ").strip().lower()

        # Normalize Cyrillic lookalikes to Latin (common keyboard layout issue)
        cyrillic_to_latin = {"а": "a", "е": "e", "с": "c", "т": "t", "д": "d"}
        choice = "".join(cyrillic_to_latin.get(c, c) for c in choice)

        if choice == "done" or choice == "":
            break

        elif choice == "a":
            console.print("\n[cyan]Enter condition description:[/]")
            desc = console.input("> ").strip()
            if not desc:
                console.print("[red]Description cannot be empty[/]")
                continue

            console.print("[cyan]Role? [1] BLOCKING (default), [2] SIGNAL:[/]")
            role_choice = console.input("> ").strip()
            role = ConditionRole.SIGNAL if role_choice == "2" else ConditionRole.BLOCKING

            from src.domain.value_objects.condition_enums import ApprovalStatus

            new_condition = Condition(
                id=uuid4(),
                description=desc,
                role=role,
                approval_status=ApprovalStatus.APPROVED,  # User-added = auto-approved
            )
            working_conditions.append(new_condition)
            console.print(f"[green]Added: {desc} (approved)[/]")

        elif choice.startswith("e "):
            try:
                idx = int(choice[2:]) - 1
                if 0 <= idx < len(working_conditions):
                    cond = working_conditions[idx]
                    console.print(f"\n[cyan]Current: {cond.description}[/]")
                    console.print("[cyan]New description (Enter to keep):[/]")
                    new_desc = console.input("> ").strip()
                    if new_desc:
                        cond.description = new_desc
                        console.print("[green]Updated[/]")
                else:
                    console.print("[red]Invalid number[/]")
            except ValueError:
                console.print("[red]Invalid format. Use: e N[/]")

        elif choice.startswith("d "):
            try:
                idx = int(choice[2:]) - 1
                if 0 <= idx < len(working_conditions):
                    removed = working_conditions.pop(idx)
                    console.print(f"[yellow]Deleted: {removed.description}[/]")
                else:
                    console.print("[red]Invalid number[/]")
            except ValueError:
                console.print("[red]Invalid format. Use: d N[/]")

        elif choice.startswith("t "):
            try:
                idx = int(choice[2:]) - 1
                if 0 <= idx < len(working_conditions):
                    cond = working_conditions[idx]
                    if cond.role == ConditionRole.BLOCKING:
                        cond.role = ConditionRole.SIGNAL
                        console.print(f"[yellow]Changed to SIGNAL: {cond.description}[/]")
                    else:
                        cond.role = ConditionRole.BLOCKING
                        console.print(f"[red]Changed to BLOCKING: {cond.description}[/]")
                else:
                    console.print("[red]Invalid number[/]")
            except ValueError:
                console.print("[red]Invalid format. Use: t N[/]")

        else:
            console.print("[red]Unknown command[/]")

    return working_conditions


def interactive_plan_and_conditions_review(
    plan: Plan,
    conditions: list[Condition],
) -> tuple[bool, str | None, list[Condition]]:
    """Show plan and conditions, ask user for approval.

    Returns:
        (True, None, conditions) - approved with possibly modified conditions
        (False, feedback, conditions) - not approved, with feedback for plan refinement
        (False, None, conditions) - rejected
    """
    console.print("\n[bold magenta]═══ PLAN REVIEW ═══[/]")
    format_plan(console, plan)

    console.print("\n[bold magenta]═══ COMPLETION CONDITIONS ═══[/]")
    format_conditions(console, conditions)

    console.print("\n[bold]Options:[/]")
    console.print("  [green]y[/] - Approve plan and conditions")
    console.print("  [yellow]n[/] - Reject")
    console.print("  [cyan]f[/] - Provide feedback to refine the plan")
    console.print("  [magenta]c[/] - Edit conditions (add/edit/delete)")
    console.print()

    raw_choice = console.input("[bold]Your choice [y/n/f/c]:[/] ")
    choice = raw_choice.strip().lower()

    # Normalize Cyrillic lookalikes to Latin
    cyrillic_to_latin = {"а": "a", "у": "y", "с": "c", "н": "n", "е": "e"}
    choice = "".join(cyrillic_to_latin.get(c, c) for c in choice)

    # Debug: log exact input for troubleshooting (sanitize to avoid encoding errors)
    from loguru import logger

    safe_raw = raw_choice.encode("utf-8", errors="replace").decode("utf-8")
    logger.debug(f"Plan review choice: raw={safe_raw!r}, normalized={choice!r}")

    if choice == "y":
        return (True, None, conditions)
    elif choice == "":
        # Don't auto-approve on Enter if no conditions defined
        if not conditions:
            console.print(
                "[yellow]No conditions defined. Use 'c' to add conditions or 'y' to approve anyway.[/]"
            )
            return interactive_plan_and_conditions_review(plan, conditions)
        return (True, None, conditions)
    elif choice == "c":
        modified_conditions = interactive_conditions_editor(conditions)
        # After editing, show again and ask for approval
        return interactive_plan_and_conditions_review(plan, modified_conditions)
    elif choice == "f":
        console.print("\n[cyan]Enter your feedback (press Enter twice to finish):[/]")
        lines: list[str] = []
        while True:
            line = console.input()
            if line == "":
                break
            lines.append(line)
        feedback = "\n".join(lines)
        return (False, feedback if feedback else None, conditions)
    elif choice == "n":
        return (False, None, conditions)
    else:
        console.print(f"[yellow]Unknown choice: {repr(choice)}. Please enter y/n/f/c[/]")
        return interactive_plan_and_conditions_review(plan, conditions)


def interactive_plan_approval(plan: Plan) -> tuple[bool, str | None]:
    """
    Show plan and ask user for approval.
    DEPRECATED: Use interactive_plan_and_conditions_review instead.

    Returns:
        (True, None) - approved
        (False, feedback) - not approved, with user feedback for refinement
        (False, None) - rejected without feedback
    """
    console.print("\n[bold magenta]═══ PLAN REVIEW ═══[/]")
    format_plan(console, plan)

    console.print("[bold]Options:[/]")
    console.print("  [green]y[/] - Approve and execute")
    console.print("  [yellow]n[/] - Reject")
    console.print("  [cyan]f[/] - Provide feedback to refine the plan")
    console.print()

    choice = console.input("[bold]Your choice [y/n/f]:[/] ").strip().lower()

    if choice == "y" or choice == "":
        return (True, None)
    elif choice == "f":
        console.print("\n[cyan]Enter your feedback (press Enter twice to finish):[/]")
        lines: list[str] = []
        while True:
            line = console.input()
            if line == "":
                break
            lines.append(line)
        feedback = "\n".join(lines)
        return (False, feedback if feedback else None)
    else:
        return (False, None)


async def run_task_async(
    description: str,
    path: Path,
    auto_approve: bool = False,
    baseline: bool = False,
    timeout: int = 60,
    verbose: bool = False,  # noqa: ARG001
    state_dir: Path | None = None,
    task_id: UUID | None = None,  # noqa: ARG001
    allow_mcp: bool = False,
    mcp_servers: list[str] | None = None,
    provider: AgentProvider = AgentProvider.CLAUDE,
) -> None:
    """Run a task asynchronously."""
    # Setup state directory
    if state_dir is None:
        state_dir = await get_default_state_dir(path)
    state_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold blue]Starting task:[/] {description}")
    console.print(f"[dim]State dir: {state_dir}[/]")
    console.print(f"[dim]Workspace: {path.absolute()}[/]")
    console.print(f"[dim]Provider: {provider.value}[/]")

    # Setup infrastructure
    agent = create_agent(provider)
    check_runner = CommandCheckRunner()
    diff_port = GitDiffAdapter()
    task_repo = JsonTaskRepo(state_dir)
    verification_port = ProjectAnalyzer(agent)

    # Get MCP registry if MCP is enabled
    mcp_registry = get_default_registry() if allow_mcp else None
    if allow_mcp:
        console.print("[dim]MCP support: enabled[/]")

    # Create orchestrator
    orchestrator = Orchestrator(
        agent=agent,
        verification_port=verification_port,
        check_runner=check_runner,
        diff_port=diff_port,
        task_repo=task_repo,
        state_dir=state_dir,
        mcp_registry=mcp_registry,
    )

    # Create input
    task_input = TaskInput(
        description=description,
        workspace_path=path.absolute(),
        sources=[str(path.absolute())],
        auto_approve=auto_approve,
        baseline=baseline,
        timeout_minutes=timeout,
        mcp_enabled=allow_mcp,
        mcp_servers=mcp_servers or [],
    )

    # Set callbacks if not auto-approve
    plan_conditions_callback = None if auto_approve else interactive_plan_and_conditions_review
    clarification_callback = None if auto_approve else interactive_clarifications
    tool_callback = create_tool_callback(console, cwd=str(path.absolute()))

    # MCP selection callback
    def mcp_selection_callback(suggestions: list[MCPSuggestion]) -> list[str]:
        """Handle MCP server selection."""
        return interactive_mcp_selection(suggestions, mcp_registry, console)

    mcp_callback = mcp_selection_callback if allow_mcp and not auto_approve else None

    def stage_callback(name: str, is_starting: bool, duration: float) -> None:
        """Display stage progress."""
        if is_starting:
            format_stage_header(console, name)
        else:
            format_stage_complete(console, name, duration)

    # Run pipeline
    try:
        result = await orchestrator.run(
            task_input,
            plan_and_conditions_callback=plan_conditions_callback,
            clarification_callback=clarification_callback,
            mcp_selection_callback=mcp_callback,
            on_agent_message=tool_callback,
            on_stage=stage_callback,
        )

        # Display result
        format_result(console, result)

    except Exception as e:
        logger.exception("Task failed")
        console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1) from e


async def resume_task_async(
    task_id: UUID,
    state_dir: Path,
    auto_approve: bool = False,
    provider: AgentProvider = AgentProvider.CLAUDE,
) -> None:
    """Resume a task asynchronously."""
    # Setup infrastructure
    agent = create_agent(provider)
    check_runner = CommandCheckRunner()
    diff_port = GitDiffAdapter()
    task_repo = JsonTaskRepo(state_dir)
    verification_port = ProjectAnalyzer(agent)

    # Load task
    task = await task_repo.load(task_id)
    if not task:
        console.print(f"[bold red]Task not found:[/] {task_id}")
        raise typer.Exit(1)

    console.print(f"[bold blue]Resuming task:[/] {task.description}")
    console.print(f"[dim]Current status: {task.status.value}[/]")
    console.print(f"[dim]Provider: {provider.value}[/]")

    # Determine workspace path from sources
    workspace_path = Path(task.sources[0]) if task.sources else Path(".")

    # Create orchestrator and resume
    orchestrator = Orchestrator(
        agent=agent,
        verification_port=verification_port,
        check_runner=check_runner,
        diff_port=diff_port,
        task_repo=task_repo,
        state_dir=state_dir,
    )

    task_input = TaskInput(
        description=task.description,
        workspace_path=workspace_path,
        sources=task.sources,
        auto_approve=auto_approve,
    )

    result = await orchestrator.resume(task, task_input)
    format_result(console, result)


async def run_research_async(
    description: str,
    path: Path,
    preset: str = "standard",
    research_type: str = "general",
    repo_context: str = "off",
    template: str = "general_default",
    auto_approve: bool = False,
    verbose: bool = False,  # noqa: ARG001
    state_dir: Path | None = None,
    provider: AgentProvider = AgentProvider.CLAUDE,
) -> None:
    """Run a research task asynchronously."""
    from src.application.orchestrator import ResearchTaskInput
    from src.domain.value_objects import (
        ReportPackTemplate,
        ResearchPreset,
        ResearchType,
    )

    # Setup state directory
    if state_dir is None:
        state_dir = await get_default_state_dir(path)
    state_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold blue]Starting research task:[/] {description}")
    console.print(f"[dim]Preset: {preset} | Type: {research_type} | Template: {template}[/]")
    console.print(f"[dim]State dir: {state_dir}[/]")
    console.print(f"[dim]Workspace: {path.absolute()}[/]")
    console.print(f"[dim]Provider: {provider.value}[/]")

    # Setup infrastructure
    agent = create_agent(provider)
    check_runner = CommandCheckRunner()
    diff_port = GitDiffAdapter()
    task_repo = JsonTaskRepo(state_dir)
    verification_port = ProjectAnalyzer(agent)

    # Create orchestrator
    orchestrator = Orchestrator(
        agent=agent,
        verification_port=verification_port,
        check_runner=check_runner,
        diff_port=diff_port,
        task_repo=task_repo,
        state_dir=state_dir,
    )

    # Parse enums (values are lowercase in the enums)
    try:
        preset_enum = ResearchPreset(preset.lower())
    except ValueError as e:
        console.print(f"[red]Invalid preset: {preset}[/]")
        raise typer.Exit(1) from e

    try:
        research_type_enum = ResearchType(research_type.lower())
    except ValueError as e:
        console.print(f"[red]Invalid research type: {research_type}[/]")
        raise typer.Exit(1) from e

    try:
        template_enum = ReportPackTemplate(template.lower())
    except ValueError as e:
        console.print(f"[red]Invalid template: {template}[/]")
        raise typer.Exit(1) from e

    # Create research input
    research_input = ResearchTaskInput(
        description=description,
        workspace_path=path.absolute(),
        preset=preset_enum,
        research_type=research_type_enum,
        repo_context=repo_context,
        template=template_enum,
        auto_approve=auto_approve,
    )

    # Set callbacks
    tool_callback = create_tool_callback(console, cwd=str(path.absolute()))

    def stage_callback(name: str, is_starting: bool, duration: float) -> None:
        """Display stage progress with human-readable names."""
        if is_starting:
            format_research_stage_header(console, name)
        else:
            format_research_stage_complete(console, name, duration)

    # Run research pipeline
    try:
        result = await orchestrator.run_research(
            research_input,
            on_agent_message=tool_callback,
            on_stage=stage_callback,
        )

        # Display research result with user-friendly output
        console.print("\n[bold green]✅ Research Complete![/]")
        console.print()

        if result.metrics:
            sources = int(result.metrics.get("sources_count", 0))
            findings = int(result.metrics.get("findings_count", 0))
            coverage = result.metrics.get("coverage", 0)
            console.print("[bold]📊 Results:[/]")
            console.print(f"   • {sources} sources analyzed")
            console.print(f"   • {findings} findings extracted")
            console.print(f"   • {coverage:.0%} topic coverage")

        # Show where to find the report
        output_dir = path / "research-output"
        if output_dir.exists():
            console.print(f"\n[bold]📄 Report saved to:[/] [cyan]{output_dir}[/]")
            console.print("[dim]   Open the .md files to read the research report[/]")

        if result.conditions_failed:
            console.print("\n[yellow]⚠ Some conditions were not met:[/]")
            for failure in result.conditions_failed:
                console.print(f"   • {failure}")

    except Exception as e:
        logger.exception("Research task failed")
        console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1) from e
