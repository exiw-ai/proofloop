from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.cli.formatters.stage_hints import get_stage_hint
from src.cli.theme import theme
from src.domain.entities.condition import Condition
from src.domain.entities.plan import Plan
from src.domain.value_objects.condition_enums import ConditionRole
from src.domain.value_objects.task_status import TaskStatus

STAGE_ICONS: dict[TaskStatus, str] = {
    TaskStatus.INTAKE: "[inbox]",
    TaskStatus.STRATEGY: "[target]",
    TaskStatus.VERIFICATION_INVENTORY: "[search]",
    TaskStatus.PLANNING: "[list]",
    TaskStatus.CONDITIONS: "[check]",
    TaskStatus.APPROVAL_CONDITIONS: "[thumbsup]",
    TaskStatus.APPROVAL_PLAN: "[thumbsup]",
    TaskStatus.EXECUTING: "[bolt]",
    TaskStatus.QUALITY: "[sparkles]",
    TaskStatus.FINALIZE: "[flag]",
    TaskStatus.DONE: "[party]",
    TaskStatus.BLOCKED: "[stop]",
    TaskStatus.STOPPED: "[pause]",
    # Research pipeline statuses
    TaskStatus.RESEARCH_INTAKE: "[inbox]",
    TaskStatus.RESEARCH_STRATEGY: "[target]",
    TaskStatus.RESEARCH_SOURCE_SELECTION: "[search]",
    TaskStatus.RESEARCH_REPO_CONTEXT: "[folder]",
    TaskStatus.RESEARCH_INVENTORY: "[list]",
    TaskStatus.RESEARCH_PLANNING: "[list]",
    TaskStatus.RESEARCH_CONDITIONS: "[check]",
    TaskStatus.RESEARCH_APPROVAL: "[thumbsup]",
    TaskStatus.RESEARCH_BASELINE: "[play]",
    TaskStatus.RESEARCH_DISCOVERY: "[magnifier]",
    TaskStatus.RESEARCH_DEEPENING: "[dive]",
    TaskStatus.RESEARCH_CITATION_VALIDATE: "[check]",
    TaskStatus.RESEARCH_REPORT_GENERATION: "[document]",
    TaskStatus.RESEARCH_FINALIZED: "[flag]",
    TaskStatus.RESEARCH_FAILED: "[stop]",
    TaskStatus.RESEARCH_STAGNATED: "[pause]",
}

STAGE_COLORS: dict[TaskStatus, str] = {
    TaskStatus.INTAKE: "blue",
    TaskStatus.STRATEGY: "cyan",
    TaskStatus.VERIFICATION_INVENTORY: "yellow",
    TaskStatus.PLANNING: "magenta",
    TaskStatus.CONDITIONS: "green",
    TaskStatus.APPROVAL_CONDITIONS: "green",
    TaskStatus.APPROVAL_PLAN: "green",
    TaskStatus.EXECUTING: "bold yellow",
    TaskStatus.QUALITY: "cyan",
    TaskStatus.FINALIZE: "blue",
    TaskStatus.DONE: "bold green",
    TaskStatus.BLOCKED: "bold red",
    TaskStatus.STOPPED: "bold yellow",
    # Research pipeline statuses
    TaskStatus.RESEARCH_INTAKE: "blue",
    TaskStatus.RESEARCH_STRATEGY: "cyan",
    TaskStatus.RESEARCH_SOURCE_SELECTION: "yellow",
    TaskStatus.RESEARCH_REPO_CONTEXT: "magenta",
    TaskStatus.RESEARCH_INVENTORY: "cyan",
    TaskStatus.RESEARCH_PLANNING: "magenta",
    TaskStatus.RESEARCH_CONDITIONS: "green",
    TaskStatus.RESEARCH_APPROVAL: "green",
    TaskStatus.RESEARCH_BASELINE: "yellow",
    TaskStatus.RESEARCH_DISCOVERY: "bold cyan",
    TaskStatus.RESEARCH_DEEPENING: "bold magenta",
    TaskStatus.RESEARCH_CITATION_VALIDATE: "yellow",
    TaskStatus.RESEARCH_REPORT_GENERATION: "cyan",
    TaskStatus.RESEARCH_FINALIZED: "bold green",
    TaskStatus.RESEARCH_FAILED: "bold red",
    TaskStatus.RESEARCH_STAGNATED: "bold yellow",
}


STAGE_NAMES: dict[str, str] = {
    "inventory": "VERIFICATION INVENTORY",
    "clarification": "CLARIFICATIONS",
    "planning": "PLANNING",
    "conditions": "CONDITIONS",
    "approval": "APPROVAL",
    "delivery": "DELIVERY",
    "quality": "QUALITY CHECK",
    "finalize": "FINALIZATION",
}

# Code pipeline - human-readable info with step numbers
# Format: (step_number, display_name, description)
# Keys match the stage names used in orchestrator.py
CODE_STAGE_INFO: dict[str, tuple[int, str, str]] = {
    # Actual stage names from orchestrator
    "inventory": (1, "Exploring Codebase", "Analyzing project structure and dependencies..."),
    "mcp_selection": (2, "Selecting Tools", "Choosing additional tools for the task..."),
    "clarification": (3, "Clarifications", "Gathering additional information..."),
    "planning": (4, "Creating Plan", "Designing implementation steps..."),
    "delivery": (5, "Implementing Changes", "Writing code and making changes..."),
    # Legacy/fallback names (TaskStatus values)
    "intake": (1, "Analyzing Task", "Understanding what needs to be done..."),
    "strategy": (1, "Planning Strategy", "Determining the best approach..."),
    "verification_inventory": (1, "Exploring Codebase", "Analyzing project structure..."),
    "conditions": (4, "Defining Conditions", "Setting up completion criteria..."),
    "approval_conditions": (4, "Awaiting Approval", "Waiting for your approval..."),
    "approval_plan": (4, "Awaiting Approval", "Waiting for plan approval..."),
    "executing": (5, "Implementing Changes", "Writing code and making changes..."),
    "quality": (6, "Quality Check", "Verifying changes meet conditions..."),
    "finalize": (7, "Finalizing", "Completing the task..."),
    "done": (7, "Complete", "Task finished successfully!"),
    "blocked": (0, "Blocked", "Task cannot proceed..."),
    "stopped": (0, "Stopped", "Task was stopped..."),
}

CODE_TOTAL_STEPS = 7

# Research pipeline - human-readable info with step numbers
# Format: (step_number, display_name, description)
RESEARCH_STAGE_INFO: dict[str, tuple[int, str, str]] = {
    "research_intake": (1, "Starting Research", "Initializing research task..."),
    "research_strategy": (
        2,
        "Selecting Sources",
        "Analyzing which sources are best for your topic...",
    ),
    "research_repo_context": (3, "Analyzing Codebase", "Understanding your project structure..."),
    "research_inventory": (
        4,
        "Building Research Plan",
        "Creating search queries and identifying key topics...",
    ),
    "research_baseline": (
        5,
        "Capturing Baseline",
        "Running initial searches to establish baseline...",
    ),
    "research_discovery": (
        6,
        "Discovering Information",
        "Searching and collecting information from sources...",
    ),
    "research_deepening": (7, "Synthesizing Findings", "Analyzing and connecting findings..."),
    "research_report_generation": (8, "Writing Report", "Generating research report sections..."),
    "research_citation_validate": (
        9,
        "Validating Citations",
        "Checking that all citations are valid...",
    ),
    "research_conditions": (
        10,
        "Verifying Completeness",
        "Checking that all requirements are met...",
    ),
    "research_handoff": (11, "Preparing Handoff", "Creating implementation summary..."),
    "research_finalize": (12, "Finalizing", "Saving results and cleaning up..."),
}

RESEARCH_TOTAL_STEPS = 12


def format_stage_header(
    console: Console,
    stage: str,
    show_hints: bool = True,
    total_steps: int | None = None,
    step_offset: int = 0,
) -> None:
    """Display stage header with step number and description.

    Args:
        console: Rich console for output
        stage: Stage name (e.g., "inventory", "planning")
        show_hints: Whether to show hint text
        total_steps: Override for total step count (for skipped stages)
        step_offset: Subtract from step number (for stages after skipped ones)

    Example:
    ⚡ Step 4/10: Creating Plan
       Designing implementation steps...
       ℹ  Creating a step-by-step plan you can review and approve.
    """
    info = CODE_STAGE_INFO.get(stage)
    total = total_steps if total_steps is not None else CODE_TOTAL_STEPS
    if info:
        step_num, display_name, description = info
        adjusted_step = max(1, step_num - step_offset) if step_num > 0 else 0
        console.print()
        if adjusted_step > 0:
            console.print(f"[{theme.INFO_BOLD}]⚡ Step {adjusted_step}/{total}: {display_name}[/]")
        else:
            # Blocked/Stopped states don't have step numbers
            console.print(f"[{theme.WARNING_BOLD}]⚠ {display_name}[/]")
        console.print(f"[{theme.DIM}]   {description}[/]")

        if show_hints:
            hint = get_stage_hint(stage)
            if hint:
                for line in hint.split("\n"):
                    console.print(f"[{theme.DIM_ITALIC}]   ℹ  {line}[/]")
    else:
        # Fallback for unknown stages
        name = STAGE_NAMES.get(stage, stage.upper())
        console.print(f"\n[{theme.INFO_BOLD}]═══ {name} ═══[/]")


def format_stage_complete(console: Console, stage: str, duration_seconds: float) -> None:
    """Display stage completion with timing."""
    info = CODE_STAGE_INFO.get(stage)

    if duration_seconds >= 60:
        time_str = f"{int(duration_seconds / 60)}m {int(duration_seconds % 60)}s"
    else:
        time_str = f"{int(duration_seconds)}s"

    if info:
        _, display_name, _ = info
        console.print(f"[{theme.SUCCESS}]   ✓[/] {display_name} [{theme.DIM}]({time_str})[/]\n")
    else:
        name = STAGE_NAMES.get(stage, stage.upper()).title()
        console.print(f"[{theme.SUCCESS}]✓[/] {name} complete [{theme.DIM}]({time_str})[/]\n")


def format_research_stage_header(console: Console, stage: str, show_hints: bool = True) -> None:
    """Display research stage header with step number and description.

    Example:
    🔍 Step 6/12: Discovering Information
       Searching and collecting information from sources...
       ℹ  Actively searching and collecting information.
    """
    info = RESEARCH_STAGE_INFO.get(stage)
    if info:
        step_num, display_name, description = info
        console.print()
        console.print(
            f"[{theme.INFO_BOLD}]🔍 Step {step_num}/{RESEARCH_TOTAL_STEPS}: {display_name}[/]"
        )
        console.print(f"[{theme.DIM}]   {description}[/]")

        if show_hints:
            hint = get_stage_hint(stage)
            if hint:
                for line in hint.split("\n"):
                    console.print(f"[{theme.DIM_ITALIC}]   ℹ  {line}[/]")
    else:
        # Fallback for unknown stages
        name = stage.replace("research_", "").replace("_", " ").title()
        console.print(f"\n[{theme.INFO_BOLD}]🔍 {name}[/]")


def format_research_stage_complete(console: Console, stage: str, duration_seconds: float) -> None:
    """Display research stage completion with timing."""
    info = RESEARCH_STAGE_INFO.get(stage)

    if duration_seconds >= 60:
        time_str = f"{int(duration_seconds / 60)}m {int(duration_seconds % 60)}s"
    else:
        time_str = f"{int(duration_seconds)}s"

    if info:
        _, display_name, _ = info
        console.print(f"[{theme.SUCCESS}]   ✓[/] {display_name} [{theme.DIM}]({time_str})[/]\n")
    else:
        name = stage.replace("research_", "").replace("_", " ").title()
        console.print(f"[{theme.SUCCESS}]   ✓[/] {name} [{theme.DIM}]({time_str})[/]\n")


def format_stage(console: Console, status: TaskStatus, message: str = "") -> None:
    icon = STAGE_ICONS.get(status, ">")
    color = STAGE_COLORS.get(status, "white")

    text = Text()
    text.append(f"{icon} ", style="bold")
    text.append(status.value.upper(), style=color)
    if message:
        text.append(f" - {message}", style="dim")

    console.print(text)


def format_stage_panel(console: Console, status: TaskStatus, content: str) -> None:
    icon = STAGE_ICONS.get(status, ">")
    color = STAGE_COLORS.get(status, "white")

    panel = Panel(
        content,
        title=f"{icon} {status.value}",
        border_style=color,
    )
    console.print(panel)


def format_plan(console: Console, plan: Plan) -> None:
    """Display plan with steps for user review."""
    console.print(f"\n[{theme.INFO_BOLD}]Goal:[/] {plan.goal}\n")

    if plan.approach:
        console.print(f"[{theme.HEADER}]Approach:[/]")
        for line in plan.approach.strip().split("\n"):
            console.print(f"  [{theme.DIM}]{line}[/]")
        console.print()

    if plan.boundaries:
        console.print(f"[{theme.HEADER}]Boundaries (will NOT do):[/]")
        for b in plan.boundaries:
            console.print(f"  [{theme.DIM}]• {b}[/]")
        console.print()

    table = Table(title="Execution Steps", show_header=True)
    table.add_column("#", style=theme.DIM, width=3)
    table.add_column("Description")
    table.add_column("Files", style=theme.DIM)

    for step in plan.steps:
        files = ", ".join(step.target_files[:3]) if step.target_files else "-"
        if len(step.target_files) > 3:
            files += f" (+{len(step.target_files) - 3})"
        table.add_row(str(step.number), step.description, files)

    console.print(table)

    if plan.risks:
        console.print(f"\n[{theme.WARNING_BOLD}]Risks:[/]")
        for r in plan.risks:
            console.print(f"  [{theme.WARNING}]⚠ {r}[/]")

    if plan.assumptions:
        console.print(f"\n[{theme.HEADER}]Assumptions:[/]")
        for a in plan.assumptions:
            console.print(f"  [{theme.DIM}]• {a}[/]")

    console.print()


def format_conditions(console: Console, conditions: list[Condition]) -> None:
    """Display conditions for user review."""
    if not conditions:
        console.print(f"[{theme.DIM}]No conditions defined yet.[/]")
        console.print(f"[{theme.DIM}]Add conditions to define what 'done' means for this task.[/]")
        return

    table = Table(title="Completion Conditions (Definition of Done)", show_header=True)
    table.add_column("#", style=theme.DIM, width=3)
    table.add_column("Role", width=10)
    table.add_column("Description")
    table.add_column("Check", style=theme.DIM, width=12)

    for i, cond in enumerate(conditions, 1):
        role_style = theme.BLOCKING if cond.role == ConditionRole.BLOCKING else theme.SIGNAL
        role_text = f"[{role_style}]{cond.role.value.upper()}[/]"
        check_text = "auto" if cond.check_id else "manual"
        table.add_row(str(i), role_text, cond.description, check_text)

    console.print(table)

    blocking_count = len([c for c in conditions if c.role == ConditionRole.BLOCKING])
    signal_count = len([c for c in conditions if c.role == ConditionRole.SIGNAL])

    console.print(
        f"\n[{theme.BLOCKING}]BLOCKING ({blocking_count}):[/] [{theme.DIM}]Task won't complete until these pass[/]"
    )
    console.print(
        f"[{theme.SIGNAL}]SIGNAL ({signal_count}):[/] [{theme.DIM}]For tracking only, won't block completion[/]"
    )
