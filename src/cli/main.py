import asyncio
import sys
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console

from src.cli.commands import derive_code, list_tasks, resume, run, status
from src.infrastructure.mcp.registry import get_default_registry


def setup_logging(verbose: bool = False, log_file: Path | None = None) -> None:
    """Configure loguru logging."""
    logger.remove()

    file_path = log_file or Path("output.log")
    logger.add(
        file_path,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",
        encoding="utf-8",
    )

    if verbose:
        logger.add(
            sys.stderr,
            format="{time:HH:mm:ss} | {level: <8} | {message}",
            level="DEBUG",
        )


app = typer.Typer(
    name="proofloop",
    help="Proofloop - autonomous coding agent powered by Claude",
    no_args_is_help=True,
)

# Register commands
app.command(name="run")(run.run_task)
app.command(name="derive-code")(derive_code.derive_code)

# Task subcommand group
task_app = typer.Typer(help="Task management commands")
task_app.command(name="status")(status.task_status)
task_app.command(name="resume")(resume.resume_task)
task_app.command(name="list")(list_tasks.list_all_tasks)
app.add_typer(task_app, name="task")

# MCP subcommand group
mcp_app = typer.Typer(help="MCP server management commands")


@mcp_app.command(name="list")
def mcp_list(
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category"),
) -> None:
    """List available MCP servers."""
    from src.cli.mcp.ui import show_mcp_servers_table

    console = Console()
    registry = get_default_registry()

    if category:
        templates = registry.list_by_category(category)
        title = f"MCP Servers - {category}"
    else:
        templates = registry.list_all()
        title = "Available MCP Servers"

    if not templates:
        console.print("[yellow]No MCP servers found.[/]")
        return

    show_mcp_servers_table(console, templates, title)


@mcp_app.command(name="configure")
def mcp_configure(
    server_name: str = typer.Argument(..., help="MCP server name to configure"),
) -> None:
    """Configure an MCP server with credentials."""
    from src.cli.mcp.ui import interactive_mcp_configuration
    from src.infrastructure.mcp.configurator import MCPConfigurator
    from src.infrastructure.mcp.installer import MCPInstaller

    console = Console()
    registry = get_default_registry()
    template = registry.get(server_name)

    if not template:
        console.print(f"[red]Unknown MCP server: {server_name}[/]")
        console.print("[dim]Use 'proofloop mcp list' to see available servers.[/]")
        raise typer.Exit(1)

    configurator = MCPConfigurator()
    installer = MCPInstaller()

    config = asyncio.run(interactive_mcp_configuration(template, configurator, installer, console))

    if config:
        console.print(f"[green]Server '{server_name}' configured successfully.[/]")
    else:
        console.print("[yellow]Configuration cancelled.[/]")


@mcp_app.command(name="installed")
def mcp_installed() -> None:
    """List configured MCP servers."""
    from src.infrastructure.mcp.configurator import MCPConfigurator

    console = Console()
    configurator = MCPConfigurator()
    servers = configurator.list_configured_servers()

    if not servers:
        console.print("[dim]No MCP servers configured.[/]")
        console.print("[dim]Use 'proofloop mcp configure <server>' to configure one.[/]")
        return

    console.print("[bold]Configured MCP Servers:[/]")
    for name in servers:
        console.print(f"  [cyan]{name}[/]")


app.add_typer(mcp_app, name="mcp")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output", is_eager=True),
) -> None:
    """Proofloop - autonomous coding agent powered by Claude."""
    setup_logging(verbose=verbose)


if __name__ == "__main__":
    app()
