import asyncio
from pathlib import Path
from uuid import UUID

import typer

from src.cli.runner import resume_task_async
from src.domain.value_objects.agent_provider import AgentProvider
from src.infrastructure.git.repo_root import get_default_state_dir


def resume_task(
    task_id: str = typer.Argument(..., help="Task ID to resume"),
    state_dir: Path | None = typer.Option(None, "--state-dir", help="State directory"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Auto-approve"),
    provider: str = typer.Option(
        "claude",
        "--provider",
        help="Agent provider: claude, codex, opencode",
    ),
) -> None:
    """Resume a blocked or stopped task."""
    # Parse provider
    try:
        agent_provider = AgentProvider(provider.lower())
    except ValueError:
        raise typer.BadParameter(
            f"Invalid provider: {provider}. Must be one of: claude, codex, opencode"
        ) from None

    async def _resume() -> None:
        sd = state_dir
        if sd is None:
            sd = await get_default_state_dir()
        await resume_task_async(UUID(task_id), sd, auto_approve, agent_provider)

    asyncio.run(_resume())
