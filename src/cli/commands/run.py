import asyncio
from pathlib import Path
from uuid import UUID

import typer
from pydantic import ValidationError

from src.cli.runner import run_task_async
from src.domain.value_objects.agent_provider import AgentProvider
from src.infrastructure.agent.agent_factory import (
    ProviderNotConfiguredError,
    validate_provider_setup,
)


def run_task(
    description: str = typer.Argument(..., help="Task description"),
    path: Path = typer.Option(..., "--path", "-p", help="Workspace path (required)"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Auto-approve"),
    baseline: bool = typer.Option(False, "--baseline", help="Run baseline checks"),
    timeout: float = typer.Option(4.0, "--timeout", "-t", help="Timeout in hours"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    show_hints: bool = typer.Option(
        True,
        "--hints/--no-hints",
        help="Show educational hints explaining each stage",
    ),
    state_dir: Path | None = typer.Option(None, "--state-dir", help="State directory"),
    task_id: str | None = typer.Option(None, "--task-id", help="Custom task ID"),
    allow_mcp: bool = typer.Option(False, "--allow-mcp", help="Enable MCP server support"),
    mcp_server: list[str] = typer.Option([], "--mcp-server", "-m", help="Pre-select MCP servers"),
    provider: str = typer.Option(
        ...,
        "--provider",
        help="Agent provider (required): opencode, codex, claude",
    ),
) -> None:
    """Run a new task."""
    tid = UUID(task_id) if task_id else None

    # Parse provider
    try:
        agent_provider = AgentProvider(provider.lower())
    except ValueError:
        raise typer.BadParameter(
            f"Invalid provider: {provider}. Must be one of: opencode, codex, claude"
        ) from None

    # Validate provider is set up before starting
    try:
        validate_provider_setup(agent_provider)
    except ProviderNotConfiguredError as e:
        from rich.console import Console

        console = Console(stderr=True)
        console.print(f"\n[bold red]Error:[/] {e.provider} is not configured.\n")
        console.print(f"[dim]{e.setup_instructions}[/]\n")
        raise typer.Exit(1) from None

    # Convert hours to minutes for internal use
    timeout_minutes = int(timeout * 60)

    try:
        asyncio.run(
            run_task_async(
                description=description,
                path=path,
                auto_approve=auto_approve,
                baseline=baseline,
                timeout=timeout_minutes,
                verbose=verbose,
                show_thoughts=True,  # Always show thoughts
                show_hints=show_hints,
                state_dir=state_dir,
                task_id=tid,
                allow_mcp=allow_mcp,
                mcp_servers=mcp_server,
                provider=agent_provider,
            )
        )
    except ValidationError as e:
        for error in e.errors():
            loc = error.get("loc", ())
            field = str(loc[0]) if loc else ""
            msg = error.get("msg", str(error))
            # Clean up Pydantic message format
            if msg.startswith("Value error, "):
                msg = msg[13:]
            if field:
                typer.echo(f"Error: --{field.replace('_', '-')}: {msg}", err=True)
            else:
                typer.echo(f"Error: {msg}", err=True)
        raise typer.Exit(1) from None
