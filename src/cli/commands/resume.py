import asyncio
from pathlib import Path

import typer
from pydantic import ValidationError

from src.cli.commands.status import resolve_task_id
from src.cli.runner import resume_task_async
from src.domain.value_objects.agent_provider import AgentProvider
from src.infrastructure.agent.agent_factory import (
    ProviderNotConfiguredError,
    validate_provider_setup,
)
from src.infrastructure.git.repo_root import get_default_state_dir
from src.infrastructure.persistence.json_task_repo import JsonTaskRepo


def resume_task(
    task_id: str = typer.Argument(..., help="Task ID to resume (full or short prefix)"),
    state_dir: Path | None = typer.Option(None, "--state-dir", help="State directory"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Auto-approve"),
    show_thoughts: bool = typer.Option(
        True,
        "--show-thoughts",
        help="Show agent reasoning (if available)",
    ),
    provider: str = typer.Option(
        ...,
        "--provider",
        help="Agent provider (required): opencode, codex, claude",
    ),
) -> None:
    """Resume a blocked or stopped task."""
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

    async def _resume() -> None:
        sd = state_dir
        if sd is None:
            sd = await get_default_state_dir()

        repo = JsonTaskRepo(sd)
        resolved_id = await resolve_task_id(task_id, repo)
        if resolved_id is None:
            raise typer.Exit(1)

        await resume_task_async(resolved_id, sd, auto_approve, agent_provider, show_thoughts)

    try:
        asyncio.run(_resume())
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
