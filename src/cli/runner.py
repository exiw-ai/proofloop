from pathlib import Path
from uuid import UUID, uuid4

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from src.application.dto.task_input import TaskInput
from src.application.orchestrator import OrchestrationCallbacks, Orchestrator
from src.application.use_cases.select_mcp_servers import MCPSuggestion
from src.cli.formatters.result_formatter import (
    format_blocked_instructions,
    format_result,
    format_stopped_instructions,
)
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
from src.cli.theme import theme
from src.cli.utils import sanitize_terminal_input
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

    console.print(f"\n[{theme.INFO_BOLD}]═══ CLARIFICATION NEEDED ═══[/]")
    console.print(f"[{theme.DIM}]The agent has some questions before creating the plan.[/]\n")

    answers: list[ClarificationAnswer] = []

    for q in questions:
        # Show question with context
        console.print(f"[{theme.HEADER}]{q.question}[/]")
        if q.context:
            console.print(f"[{theme.DIM}]{q.context}[/]")
        console.print()

        # Show options as table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style=theme.TABLE_ID, width=6)
        table.add_column("Label", style=theme.TABLE_VALUE)
        table.add_column("Description", style=theme.TABLE_LABEL)

        for i, opt in enumerate(q.options, 1):
            table.add_row(f"[{i}]", opt.label, opt.description)

        console.print(table)
        console.print(f"  [{theme.DIM}]Or type your own answer directly[/]")
        console.print()

        # Get user choice
        while True:
            raw_choice = console.input(f"[{theme.HEADER}]Your choice:[/] ").strip()
            choice = raw_choice.lower()

            # Normalize Cyrillic lookalikes to Latin (common keyboard layout issue)
            cyrillic_to_latin = {"а": "a", "с": "c", "е": "e"}
            choice = "".join(cyrillic_to_latin.get(c, c) for c in choice)

            if choice == "c":
                raw_custom = console.input(f"[{theme.PROMPT}]Enter your answer:[/] ").strip()
                custom_value = sanitize_terminal_input(raw_custom)
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
                    console.print(f"[{theme.ERROR}]Invalid choice. Try again.[/]")
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
                # Treat any other input as custom answer directly
                answers.append(
                    ClarificationAnswer(
                        question_id=q.id,
                        selected_option="custom",
                        custom_value=sanitize_terminal_input(raw_choice),
                    )
                )
                break

        console.print()

    return answers


def _handle_edit_command(choice: str, conditions: list[Condition], console: Console) -> None:
    """Handle the 'e N' command to edit a condition's description."""
    try:
        idx = int(choice[2:]) - 1
        if 0 <= idx < len(conditions):
            cond = conditions[idx]
            console.print(f"\n[{theme.PROMPT}]Current: {cond.description}[/]")
            console.print(f"[{theme.PROMPT}]New description (Enter to keep):[/]")
            new_desc = sanitize_terminal_input(console.input("> ").strip())
            if new_desc:
                cond.description = new_desc
                console.print(f"[{theme.SUCCESS}]Updated[/]")
        else:
            console.print(f"[{theme.ERROR}]Invalid number[/]")
    except ValueError:
        console.print(f"[{theme.ERROR}]Invalid format. Use: e N[/]")


def _handle_delete_command(choice: str, conditions: list[Condition], console: Console) -> None:
    """Handle the 'd N' command to delete a condition."""
    try:
        idx = int(choice[2:]) - 1
        if 0 <= idx < len(conditions):
            removed = conditions.pop(idx)
            console.print(f"[{theme.WARNING}]Deleted: {removed.description}[/]")
        else:
            console.print(f"[{theme.ERROR}]Invalid number[/]")
    except ValueError:
        console.print(f"[{theme.ERROR}]Invalid format. Use: d N[/]")


def _handle_toggle_command(choice: str, conditions: list[Condition], console: Console) -> None:
    """Handle the 't N' command to toggle a condition's role between BLOCKING
    and SIGNAL."""
    try:
        idx = int(choice[2:]) - 1
        if 0 <= idx < len(conditions):
            cond = conditions[idx]
            if cond.role == ConditionRole.BLOCKING:
                cond.role = ConditionRole.SIGNAL
                console.print(f"[{theme.SIGNAL}]Changed to SIGNAL: {cond.description}[/]")
            else:
                cond.role = ConditionRole.BLOCKING
                console.print(f"[{theme.BLOCKING}]Changed to BLOCKING: {cond.description}[/]")
        else:
            console.print(f"[{theme.ERROR}]Invalid number[/]")
    except ValueError:
        console.print(f"[{theme.ERROR}]Invalid format. Use: t N[/]")


def interactive_conditions_editor(
    conditions: list[Condition],
) -> list[Condition]:
    """Interactive editor for conditions. Allows adding, editing, and deleting
    conditions.

    Returns the modified list of conditions.
    """
    working_conditions = list(conditions)

    while True:
        console.print(f"\n[{theme.INFO_BOLD}]═══ CONDITIONS EDITOR ═══[/]")
        format_conditions(console, working_conditions)

        console.print(f"\n[{theme.HEADER}]Options:[/]")
        if not working_conditions:
            console.print(
                f"  [{theme.INFO_BOLD}]a[/]    - Add new condition [{theme.HEADER}](recommended)[/]"
            )
            console.print(f"  [{theme.DIM}]done[/] - Finish editing (no conditions)")
        else:
            console.print(f"  [{theme.OPTION_APPROVE}]done[/] - Finish editing")
            console.print(f"  [{theme.INFO}]a[/]    - Add new condition")
            console.print(f"  [{theme.OPTION_REJECT}]e N[/]  - Edit condition N (e.g., 'e 1')")
            console.print(f"  [{theme.ERROR}]d N[/]  - Delete condition N (e.g., 'd 1')")
            console.print(
                f"  [{theme.OPTION_EDIT}]t N[/]  - Toggle role of condition N (blocking ↔ signal)"
            )
        console.print()

        choice = console.input(f"[{theme.HEADER}]Your choice:[/] ").strip().lower()

        # Normalize Cyrillic lookalikes to Latin (common keyboard layout issue)
        cyrillic_to_latin = {"а": "a", "е": "e", "с": "c", "т": "t", "д": "d"}
        choice = "".join(cyrillic_to_latin.get(c, c) for c in choice)

        if choice == "done" or choice == "":
            break

        elif choice == "a":
            console.print(f"\n[{theme.PROMPT}]Enter condition description:[/]")
            desc = sanitize_terminal_input(console.input("> ").strip())
            if not desc:
                console.print(f"[{theme.ERROR}]Description cannot be empty[/]")
                continue

            console.print(f"[{theme.PROMPT}]Role? [1] BLOCKING (default), [2] SIGNAL:[/]")
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
            console.print(f"[{theme.SUCCESS}]Added: {desc} (approved)[/]")

        elif choice.startswith("e "):
            _handle_edit_command(choice, working_conditions, console)

        elif choice.startswith("d "):
            _handle_delete_command(choice, working_conditions, console)

        elif choice.startswith("t "):
            _handle_toggle_command(choice, working_conditions, console)

        else:
            console.print(f"[{theme.ERROR}]Unknown command[/]")

    return working_conditions


def _get_multiline_input(console: Console) -> str:
    """Collect multi-line input from user until an empty line is entered."""
    lines: list[str] = []
    while True:
        line = sanitize_terminal_input(console.input())
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


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
    console.print(f"\n[{theme.HEADER_SECTION}]═══ PLAN REVIEW ═══[/]")
    format_plan(console, plan)

    console.print(f"\n[{theme.HEADER_SECTION}]═══ COMPLETION CONDITIONS ═══[/]")
    format_conditions(console, conditions)

    console.print(f"\n[{theme.HEADER}]Options:[/]")
    console.print(f"  [{theme.OPTION_FEEDBACK}]f[/] - Refine plan with feedback")
    console.print(f"  [{theme.OPTION_EDIT}]c[/] - Edit conditions")
    console.print(f"  [{theme.OPTION_APPROVE}]y[/] - Approve and execute")
    console.print(f"  [{theme.OPTION_REJECT}]n[/] - Reject task")
    console.print()

    raw_choice = console.input(f"[{theme.HEADER}]Your choice [y/n/f/c]:[/] ")
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
                f"[{theme.WARNING}]No conditions defined. Use 'c' to add conditions or 'y' to approve anyway.[/]"
            )
            return interactive_plan_and_conditions_review(plan, conditions)
        return (True, None, conditions)
    elif choice == "c":
        modified_conditions = interactive_conditions_editor(conditions)
        # After editing, show again and ask for approval
        return interactive_plan_and_conditions_review(plan, modified_conditions)
    elif choice == "f":
        console.print(f"\n[{theme.PROMPT}]Enter your feedback (press Enter twice to finish):[/]")
        feedback = _get_multiline_input(console)
        return (False, feedback if feedback else None, conditions)
    elif choice == "n":
        return (False, None, conditions)
    else:
        console.print(f"[{theme.WARNING}]Unknown choice: {repr(choice)}. Please enter y/n/f/c[/]")
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
    console.print(f"\n[{theme.HEADER_SECTION}]═══ PLAN REVIEW ═══[/]")
    format_plan(console, plan)

    console.print(f"[{theme.HEADER}]Options:[/]")
    console.print(f"  [{theme.OPTION_APPROVE}]y[/] - Approve and execute")
    console.print(f"  [{theme.OPTION_REJECT}]n[/] - Reject")
    console.print(f"  [{theme.OPTION_FEEDBACK}]f[/] - Provide feedback to refine the plan")
    console.print()

    choice = console.input(f"[{theme.HEADER}]Your choice [y/n/f]:[/] ").strip().lower()

    if choice == "y" or choice == "":
        return (True, None)
    elif choice == "f":
        console.print(f"\n[{theme.PROMPT}]Enter your feedback (press Enter twice to finish):[/]")
        feedback = _get_multiline_input(console)
        return (False, feedback if feedback else None)
    else:
        return (False, None)


async def run_task_async(
    description: str,
    path: Path,
    auto_approve: bool = False,
    baseline: bool = False,
    timeout: int = 60,
    verbose: bool = False,
    show_thoughts: bool = True,  # noqa: ARG001
    show_hints: bool = True,
    state_dir: Path | None = None,
    task_id: UUID | None = None,  # noqa: ARG001
    allow_mcp: bool = False,
    mcp_servers: list[str] | None = None,
    provider: AgentProvider = AgentProvider.CLAUDE,
) -> None:
    """Run a task asynchronously."""
    # Setup logging
    from src.cli.main import setup_logging

    setup_logging(verbose=verbose)

    # Setup state directory
    if state_dir is None:
        state_dir = await get_default_state_dir(path)
    state_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[{theme.INFO_BOLD}]Starting task:[/] {description}")
    console.print(f"[{theme.DIM}]Workspace: {path.absolute()}[/]")
    console.print(f"[{theme.DIM}]Provider: {provider.value}[/]")

    def task_created_callback(task_id: UUID) -> None:
        """Display task ID for resume purposes."""
        short_id = str(task_id)[:8]
        console.print(f"[{theme.DIM}]Task:[/] [{theme.INFO}]{short_id}[/]")

    # Setup infrastructure
    agent = create_agent(provider)
    check_runner = CommandCheckRunner()
    diff_port = GitDiffAdapter()
    task_repo = JsonTaskRepo(state_dir)
    verification_port = ProjectAnalyzer(agent)

    # Get MCP registry if MCP is enabled
    mcp_registry = get_default_registry() if allow_mcp else None
    if allow_mcp:
        console.print(f"[{theme.DIM}]MCP support: enabled[/]")

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

    # Step numbering adjustment when MCP is skipped
    mcp_skipped = not allow_mcp
    total_steps = 6 if mcp_skipped else 7
    # Stages after MCP (step 2) need offset when MCP is skipped
    stages_after_mcp = {"clarification", "planning", "delivery", "quality", "finalize"}

    def stage_callback(name: str, is_starting: bool, duration: float) -> None:
        """Display stage progress."""
        if is_starting:
            step_offset = 1 if mcp_skipped and name in stages_after_mcp else 0
            format_stage_header(
                console,
                name,
                show_hints=show_hints,
                total_steps=total_steps,
                step_offset=step_offset,
            )
        else:
            format_stage_complete(console, name, duration)

    # Run pipeline
    try:
        result = await orchestrator.run(
            task_input,
            callbacks=OrchestrationCallbacks(
                plan_and_conditions=plan_conditions_callback,
                clarification=clarification_callback,
                mcp_selection=mcp_callback,
                on_agent_message=tool_callback,
                on_stage=stage_callback,
                on_task_created=task_created_callback,
            ),
        )

        # Display result
        format_result(console, result)
        format_blocked_instructions(console, result)
        format_stopped_instructions(console, result)

    except Exception as e:
        logger.error(f"Task failed: {e}")
        logger.debug("Full traceback:", exc_info=True)
        console.print(f"[{theme.ERROR_BOLD}]Error:[/] {e}")
        raise typer.Exit(1) from e


async def resume_task_async(
    task_id: UUID,
    state_dir: Path,
    auto_approve: bool = False,
    provider: AgentProvider = AgentProvider.CLAUDE,
    show_thoughts: bool = True,  # noqa: ARG001
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
        console.print(f"[{theme.ERROR_BOLD}]Task not found:[/] {task_id}")
        raise typer.Exit(1)

    console.print(f"[{theme.INFO_BOLD}]Resuming task:[/] {task.description}")
    console.print(f"[{theme.DIM}]Current status: {task.status.value}[/]")
    console.print(f"[{theme.DIM}]Provider: {provider.value}[/]")

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
    verbose: bool = False,
    show_thoughts: bool = True,  # noqa: ARG001
    show_hints: bool = True,
    state_dir: Path | None = None,
    provider: AgentProvider = AgentProvider.CLAUDE,
) -> None:
    """Run a research task asynchronously."""
    from src.application.research_orchestrator import ResearchTaskInput
    from src.cli.main import setup_logging
    from src.domain.value_objects import (
        ReportPackTemplate,
        ResearchPreset,
        ResearchType,
    )

    # Setup logging
    setup_logging(verbose=verbose)

    # Setup state directory
    if state_dir is None:
        state_dir = await get_default_state_dir(path)
    state_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[{theme.INFO_BOLD}]Starting research task:[/] {description}")
    console.print(
        f"[{theme.DIM}]Preset: {preset} | Type: {research_type} | Template: {template}[/]"
    )
    console.print(f"[{theme.DIM}]State dir: {state_dir}[/]")
    console.print(f"[{theme.DIM}]Workspace: {path.absolute()}[/]")
    console.print(f"[{theme.DIM}]Provider: {provider.value}[/]")

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
        console.print(f"[{theme.ERROR}]Invalid preset: {preset}[/]")
        raise typer.Exit(1) from e

    try:
        research_type_enum = ResearchType(research_type.lower())
    except ValueError as e:
        console.print(f"[{theme.ERROR}]Invalid research type: {research_type}[/]")
        raise typer.Exit(1) from e

    try:
        template_enum = ReportPackTemplate(template.lower())
    except ValueError as e:
        console.print(f"[{theme.ERROR}]Invalid template: {template}[/]")
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
            format_research_stage_header(console, name, show_hints=show_hints)
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
        console.print(f"\n[{theme.SUCCESS_BOLD}]Research Complete![/]")
        console.print()

        if result.metrics:
            sources = int(result.metrics.get("sources_count", 0))
            findings = int(result.metrics.get("findings_count", 0))
            coverage = result.metrics.get("coverage", 0)
            console.print(f"[{theme.HEADER}]Results:[/]")
            console.print(f"   - {sources} sources analyzed")
            console.print(f"   - {findings} findings extracted")
            console.print(f"   - {coverage:.0%} topic coverage")

        # Show where to find the report
        output_dir = path / "research-output"
        if output_dir.exists():
            console.print(f"\n[{theme.HEADER}]Report saved to:[/] [{theme.INFO}]{output_dir}[/]")
            console.print(f"[{theme.DIM}]   Open the .md files to read the research report[/]")

        if result.conditions_failed:
            console.print(f"\n[{theme.WARNING}]Some conditions were not met:[/]")
            for failure in result.conditions_failed:
                console.print(f"   - {failure}")

    except Exception as e:
        logger.error(f"Research task failed: {e}")
        logger.debug("Full traceback:", exc_info=True)
        console.print(f"[{theme.ERROR_BOLD}]Error:[/] {e}")
        raise typer.Exit(1) from e
