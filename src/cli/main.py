import asyncio
import sys
from datetime import datetime
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src import __version__
from src.cli.commands import list_tasks, resume, run, status
from src.cli.theme import theme
from src.infrastructure.git.repo_root import get_xdg_data_home
from src.infrastructure.mcp.registry import get_default_registry

console = Console()


def show_full_help() -> None:
    """Display comprehensive help for all commands."""
    help_text = Text()

    # Header
    help_text.append("proofloop", style=theme.INFO_BOLD)
    help_text.append(" - agents that run until done\n\n", style=theme.DIM)

    # Global options
    help_text.append("Global Options:\n", style=theme.WARNING_BOLD)
    help_text.append("  -v, --verbose    ", style=theme.INFO)
    help_text.append("Enable verbose output\n")
    help_text.append("  -V, --version    ", style=theme.INFO)
    help_text.append("Show version and exit\n")
    help_text.append("  --help           ", style=theme.INFO)
    help_text.append("Show this help message\n\n")

    # run command
    help_text.append("proofloop run ", style=theme.SUCCESS_BOLD)
    help_text.append("<description> ", style=theme.INFO)
    help_text.append("-p <path>\n", style=theme.INFO)
    help_text.append("  Run a coding task autonomously.\n\n", style=theme.DIM)
    help_text.append("  Required:\n", style=theme.WARNING)
    help_text.append("    -p, --path PATH           ", style=theme.INFO)
    help_text.append("Workspace path\n")
    help_text.append("  Options:\n", style=theme.WARNING)
    help_text.append("    -y, --auto-approve        ", style=theme.INFO)
    help_text.append("Skip interactive approvals\n")
    help_text.append("    --baseline                ", style=theme.INFO)
    help_text.append("Run baseline checks first\n")
    help_text.append("    -t, --timeout HOURS       ", style=theme.INFO)
    help_text.append("Timeout (default: 4)\n")
    help_text.append("    --provider NAME           ", style=theme.INFO)
    help_text.append("Agent: opencode, codex, claude\n")
    help_text.append("    --allow-mcp               ", style=theme.INFO)
    help_text.append("Enable MCP server support\n")
    help_text.append("    -m, --mcp-server NAME     ", style=theme.INFO)
    help_text.append("Pre-select MCP servers\n\n")

    # task subcommands
    help_text.append("proofloop task list\n", style=theme.SUCCESS_BOLD)
    help_text.append("  List all tasks.\n\n", style=theme.DIM)

    help_text.append("proofloop task status ", style=theme.SUCCESS_BOLD)
    help_text.append("<task_id>\n", style=theme.INFO)
    help_text.append(
        "  Show task status. Accepts full UUID or 4+ char prefix.\n\n", style=theme.DIM
    )

    help_text.append("proofloop task resume ", style=theme.SUCCESS_BOLD)
    help_text.append("<task_id>\n", style=theme.INFO)
    help_text.append("  Resume a blocked or stopped task.\n\n", style=theme.DIM)
    help_text.append("  Options:\n", style=theme.WARNING)
    help_text.append("    -y, --auto-approve        ", style=theme.INFO)
    help_text.append("Skip interactive approvals\n")
    help_text.append("    --provider NAME           ", style=theme.INFO)
    help_text.append("Agent: opencode, codex, claude\n\n")

    # mcp subcommands
    help_text.append("proofloop mcp list ", style=theme.SUCCESS_BOLD)
    help_text.append("[-c CATEGORY]\n", style=theme.INFO)
    help_text.append("  List available MCP servers.\n\n", style=theme.DIM)

    help_text.append("proofloop mcp configure ", style=theme.SUCCESS_BOLD)
    help_text.append("<server_name>\n", style=theme.INFO)
    help_text.append("  Configure an MCP server with credentials.\n\n", style=theme.DIM)

    help_text.append("proofloop mcp installed\n", style=theme.SUCCESS_BOLD)
    help_text.append("  List configured MCP servers.\n\n", style=theme.DIM)

    # Examples
    help_text.append("Examples:\n", style=theme.WARNING_BOLD)
    help_text.append("  proofloop run ", style=theme.SUCCESS)
    help_text.append('"Add login endpoint" ', style=theme.TEXT)
    help_text.append("-p ./my-project\n", style=theme.INFO)
    help_text.append("  proofloop run ", style=theme.SUCCESS)
    help_text.append('"Fix auth bug" ', style=theme.TEXT)
    help_text.append("-p . -y\n", style=theme.INFO)
    help_text.append("  proofloop task resume ", style=theme.SUCCESS)
    help_text.append("a1b2\n", style=theme.INFO)

    console.print(Panel(help_text, border_style=theme.BORDER_INFO, padding=(1, 2)))


def get_log_dir() -> Path:
    """Return XDG-compliant log directory."""
    return get_xdg_data_home() / "proofloop" / "logs"


def setup_logging(verbose: bool = False, task_id: str | None = None) -> Path:
    """Configure loguru logging to XDG-compliant location.

    Args:
        verbose: If True, also log to stderr.
        task_id: Optional task ID to include in log filename.

    Returns:
        Path to the log file for bug reports.
    """
    logger.remove()

    # Global log directory
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    # Session log file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_name = f"{timestamp}_{task_id}.log" if task_id else f"{timestamp}.log"
    log_file = log_dir / log_name

    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )

    if verbose:
        logger.add(
            sys.stderr,
            format="{time:HH:mm:ss} | {level: <8} | {message}",
            level="DEBUG",
        )

    return log_file


app = typer.Typer(
    name="proofloop",
    help="Proofloop - agents that run until done",
    no_args_is_help=False,
    add_completion=False,
    pretty_exceptions_enable=False,
)

# Register commands
app.command(name="run")(run.run_task)

# Task subcommand group
task_app = typer.Typer(help="Task management commands", pretty_exceptions_enable=False)
task_app.command(name="status")(status.task_status)
task_app.command(name="resume")(resume.resume_task)
task_app.command(name="list")(list_tasks.list_all_tasks)
app.add_typer(task_app, name="task")

# MCP subcommand group
mcp_app = typer.Typer(help="MCP server management commands", pretty_exceptions_enable=False)


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
        console.print(f"[{theme.WARNING}]No MCP servers found.[/]")
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
        console.print(f"[{theme.ERROR}]Unknown MCP server: {server_name}[/]")
        console.print(f"[{theme.DIM}]Use 'proofloop mcp list' to see available servers.[/]")
        raise typer.Exit(1)

    configurator = MCPConfigurator()
    installer = MCPInstaller()

    config = asyncio.run(interactive_mcp_configuration(template, configurator, installer, console))

    if config:
        console.print(f"[{theme.SUCCESS}]Server '{server_name}' configured successfully.[/]")
    else:
        console.print(f"[{theme.WARNING}]Configuration cancelled.[/]")


@mcp_app.command(name="installed")
def mcp_installed() -> None:
    """List configured MCP servers."""
    from src.infrastructure.mcp.configurator import MCPConfigurator

    console = Console()
    configurator = MCPConfigurator()
    servers = configurator.list_configured_servers()

    if not servers:
        console.print(f"[{theme.DIM}]No MCP servers configured.[/]")
        console.print(f"[{theme.DIM}]Use 'proofloop mcp configure <server>' to configure one.[/]")
        return

    console.print(f"[{theme.HEADER}]Configured MCP Servers:[/]")
    for name in servers:
        console.print(f"  [{theme.INFO}]{name}[/]")


app.add_typer(mcp_app, name="mcp")


def help_callback(value: bool) -> None:
    """Show full help and exit."""
    if value:
        show_full_help()
        raise typer.Exit()


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        console.print(f"proofloop {__version__}")
        raise typer.Exit()


@app.command(name="logs")
def logs_command() -> None:
    """Show logs directory location and recent log files."""
    log_dir = get_log_dir()

    if not log_dir.exists():
        console.print(f"[{theme.DIM}]Logs directory: {log_dir}[/]")
        console.print(f"[{theme.DIM}]No logs yet.[/]")
        return

    console.print(f"[{theme.HEADER}]Logs directory:[/] {log_dir}")

    # List recent log files (last 10)
    log_files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]

    if log_files:
        console.print(f"\n[{theme.HEADER}]Recent logs:[/]")
        for log_file in log_files:
            size_kb = log_file.stat().st_size / 1024
            console.print(f"  [{theme.INFO}]{log_file.name}[/] [{theme.DIM}]({size_kb:.1f} KB)[/]")
    else:
        console.print(f"[{theme.DIM}]No log files found.[/]")


@app.command(name="doctor")
def doctor_command() -> None:
    """Check environment and dependencies."""
    import shutil

    console.print(f"[{theme.HEADER}]Proofloop Doctor[/]\n")

    # Version
    console.print(f"[{theme.INFO}]Version:[/] {__version__}")

    # Python
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    console.print(f"[{theme.INFO}]Python:[/] {py_version}")

    # Check required tools
    tools = ["git", "uv", "claude", "codex", "opencode"]
    console.print(f"\n[{theme.HEADER}]Tools:[/]")
    for tool in tools:
        path = shutil.which(tool)
        if path:
            console.print(f"  [{theme.SUCCESS}]{tool}[/] {path}")
        else:
            console.print(f"  [{theme.DIM}]{tool}[/] not found")

    # Logs directory
    log_dir = get_log_dir()
    console.print(f"\n[{theme.INFO}]Logs:[/] {log_dir}")

    # State directory
    state_dir = get_xdg_data_home() / "proofloop"
    console.print(f"[{theme.INFO}]State:[/] {state_dir}")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output", is_eager=True),
    _version: bool = typer.Option(
        False, "--version", "-V", callback=version_callback, is_eager=True, help="Show version"
    ),
    _help: bool = typer.Option(
        False, "--help", "-h", callback=help_callback, is_eager=True, help="Show help"
    ),
) -> None:
    """Proofloop - agents that run until done."""
    setup_logging(verbose=verbose)
    # Show help if no command provided
    if ctx.invoked_subcommand is None:
        show_full_help()
        raise typer.Exit()


if __name__ == "__main__":
    app()
