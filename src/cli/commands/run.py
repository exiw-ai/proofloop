import asyncio
from pathlib import Path
from uuid import UUID

import typer

from src.cli.runner import run_research_async, run_task_async
from src.domain.value_objects.agent_provider import AgentProvider


def run_task(
    description: str = typer.Argument(..., help="Task description"),
    path: Path = typer.Option(..., "--path", "-p", help="Workspace path (required)"),
    goal: list[str] = typer.Option([], "--goal", "-g", help="Task goals"),  # noqa: ARG001
    constraint: list[str] = typer.Option([], "--constraint", "-c", help="Constraints"),  # noqa: ARG001
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Auto-approve"),
    baseline: bool = typer.Option(False, "--baseline", help="Run baseline checks"),
    timeout: int = typer.Option(60, "--timeout", "-t", help="Timeout in minutes"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    state_dir: Path | None = typer.Option(None, "--state-dir", help="State directory"),
    task_id: str | None = typer.Option(None, "--task-id", help="Custom task ID"),
    allow_mcp: bool = typer.Option(False, "--allow-mcp", help="Enable MCP server support"),
    mcp_server: list[str] = typer.Option([], "--mcp-server", "-m", help="Pre-select MCP servers"),
    provider: str = typer.Option(
        "claude",
        "--provider",
        help="Agent provider: claude, codex, opencode",
    ),
    research: bool = typer.Option(False, "--research", help="Run as research task"),
    preset: str = typer.Option(
        "standard",
        "--preset",
        help="Research preset: minimal, standard, thorough, exhaustive",
    ),
    research_type: str = typer.Option(
        "general",
        "--research-type",
        help="Research type: academic, market, technical, general",
    ),
    repo_context: str = typer.Option(
        "off",
        "--repo-context",
        help="Repo context mode: off, light, full",
    ),
    template: str = typer.Option(
        "general_default",
        "--template",
        help="Report template: general_default, academic_review, market_landscape, technical_best_practices",
    ),
) -> None:
    """Run a new task."""
    tid = UUID(task_id) if task_id else None

    # Parse provider
    try:
        agent_provider = AgentProvider(provider.lower())
    except ValueError:
        raise typer.BadParameter(
            f"Invalid provider: {provider}. Must be one of: claude, codex, opencode"
        ) from None

    if research:
        asyncio.run(
            run_research_async(
                description=description,
                path=path,
                preset=preset,
                research_type=research_type,
                repo_context=repo_context,
                template=template,
                auto_approve=auto_approve,
                verbose=verbose,
                state_dir=state_dir,
                provider=agent_provider,
            )
        )
    else:
        asyncio.run(
            run_task_async(
                description=description,
                path=path,
                auto_approve=auto_approve,
                baseline=baseline,
                timeout=timeout,
                verbose=verbose,
                state_dir=state_dir,
                task_id=tid,
                allow_mcp=allow_mcp,
                mcp_servers=mcp_server,
                provider=agent_provider,
            )
        )
