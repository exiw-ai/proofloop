"""Interactive MCP UI components for CLI."""

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.application.use_cases.select_mcp_servers import MCPSuggestion
from src.cli.theme import theme
from src.domain.value_objects.mcp_types import (
    MCPServerConfig,
    MCPServerRegistry,
    MCPServerTemplate,
)
from src.infrastructure.mcp.configurator import MCPConfigurator
from src.infrastructure.mcp.installer import MCPInstaller


def show_mcp_servers_table(
    console: Console,
    templates: list[MCPServerTemplate],
    title: str = "Available MCP Servers",
) -> None:
    """Display a table of MCP server templates."""
    table = Table(title=title, show_header=True)
    table.add_column("Name", style=theme.MCP_NAME)
    table.add_column("Category", style=theme.MCP_CATEGORY)
    table.add_column("Description")
    table.add_column("Credentials", style=theme.MCP_CREDENTIALS)

    for template in templates:
        creds = ", ".join(template.required_credentials) if template.required_credentials else "-"
        table.add_row(
            template.name,
            template.category,
            template.description,
            creds,
        )

    console.print(table)


def show_mcp_suggestions(
    console: Console,
    suggestions: list[MCPSuggestion],
) -> None:
    """Display MCP suggestions from agent analysis."""
    if not suggestions:
        console.print(f"[{theme.DIM}]No MCP servers suggested for this task.[/]")
        return

    console.print(f"\n[{theme.INFO_BOLD}]═══ SUGGESTED MCP SERVERS ═══[/]")
    console.print(f"[{theme.DIM}]The agent suggests these servers based on task analysis:[/]\n")

    table = Table(show_header=True, box=None)
    table.add_column("#", style=theme.MCP_NAME, width=3)
    table.add_column("Server", style=theme.HEADER)
    table.add_column("Confidence", style=theme.MCP_CATEGORY)
    table.add_column("Reason")

    for i, suggestion in enumerate(suggestions, 1):
        conf_str = f"{suggestion.confidence:.0%}"
        conf_style = (
            theme.MCP_CONFIDENCE_HIGH if suggestion.confidence >= 0.8 else theme.MCP_CONFIDENCE_LOW
        )
        table.add_row(
            str(i),
            suggestion.server_name,
            f"[{conf_style}]{conf_str}[/]",
            suggestion.reason,
        )

    console.print(table)


def interactive_mcp_selection(
    suggestions: list[MCPSuggestion],
    registry: MCPServerRegistry | None = None,
    console: Console | None = None,
) -> list[str]:
    """Interactive selection of MCP servers.

    Shows suggestions from agent, allows selecting from them or adding others.

    Args:
        suggestions: List of MCP suggestions from agent analysis.
        registry: Optional registry for browsing all available servers.
        console: Rich console for output.

    Returns:
        List of selected server names.
    """
    console = console or Console()

    # Show suggestions
    show_mcp_suggestions(console, suggestions)

    # Quick select options
    console.print(f"\n[{theme.HEADER}]Options:[/]")
    console.print(f"  [{theme.OPTION_APPROVE}]y[/] - Accept all suggested servers")
    console.print(f"  [{theme.INFO}]n[/] - Select specific servers")
    console.print(f"  [{theme.WARNING}]b[/] - Browse all available servers")
    console.print(f"  [{theme.ERROR}]s[/] - Skip MCP (no servers)")
    console.print()

    choice = Prompt.ask(
        f"[{theme.HEADER}]Your choice[/]",
        choices=["y", "n", "b", "s"],
        default="y" if suggestions else "s",
    )

    if choice == "s":
        return []

    if choice == "y" and suggestions:
        return [s.server_name for s in suggestions]

    if choice == "b" and registry:
        return _browse_and_select(console, registry)

    if choice == "n":
        return _select_from_suggestions(console, suggestions, registry)

    return []


def _select_from_suggestions(
    console: Console,
    suggestions: list[MCPSuggestion],
    registry: MCPServerRegistry | None,
) -> list[str]:
    """Select specific servers from suggestions."""
    if not suggestions:
        if registry:
            return _browse_and_select(console, registry)
        return []

    console.print(f"\n[{theme.DIM}]Enter server numbers (comma-separated) or 'a' to add more:[/]")
    selection = Prompt.ask("Select servers", default="1")

    selected: list[str] = []

    if selection.lower() == "a" and registry:
        return _browse_and_select(console, registry)

    for part in selection.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(suggestions):
                selected.append(suggestions[idx].server_name)

    return selected


def _browse_and_select(
    console: Console,
    registry: MCPServerRegistry,
) -> list[str]:
    """Browse all available servers and select."""
    categories = registry.get_categories()

    console.print(f"\n[{theme.INFO_BOLD}]═══ AVAILABLE MCP SERVERS ═══[/]")

    # Show by category
    for category in categories:
        cat_templates = registry.list_by_category(category)
        if cat_templates:
            console.print(f"\n[{theme.HEADER_SECTION}]{category.upper()}[/]")
            for t in cat_templates:
                creds = (
                    f" [{theme.DIM}](requires: {', '.join(t.required_credentials)})[/]"
                    if t.required_credentials
                    else ""
                )
                console.print(f"  [{theme.MCP_NAME}]{t.name}[/] - {t.description}{creds}")

    console.print(f"\n[{theme.DIM}]Enter server names (comma-separated):[/]")
    selection = Prompt.ask("Select servers", default="")

    selected: list[str] = []
    for name in selection.split(","):
        name = name.strip()
        if name and registry.get(name):
            selected.append(name)

    return selected


async def interactive_mcp_configuration(
    template: MCPServerTemplate,
    configurator: MCPConfigurator,
    installer: MCPInstaller,
    console: Console | None = None,
) -> MCPServerConfig | None:
    """Interactive configuration of an MCP server.

    Handles installation and credential collection.

    Args:
        template: Server template to configure.
        configurator: MCP configurator service.
        installer: MCP installer service.
        console: Rich console for output.

    Returns:
        Configured MCPServerConfig or None if cancelled.
    """
    console = console or Console()

    console.print(f"\n[{theme.INFO_BOLD}]Configuring: {template.name}[/]")
    console.print(f"[{theme.DIM}]{template.description}[/]")

    # Check installation
    status = await installer.check_status(template)
    if status.value == "not_installed":
        console.print(f"\n[{theme.WARNING}]Server '{template.name}' is not installed.[/]")
        if template.install_package:
            console.print(
                f"[{theme.DIM}]Install command: {template.install_source.value} {template.install_package}[/]"
            )

            if Confirm.ask("Install now?", default=True):
                console.print(f"[{theme.DIM}]Installing...[/]")
                success = await installer.install(template)
                if not success:
                    console.print(f"[{theme.ERROR}]Installation failed.[/]")
                    return None
                console.print(f"[{theme.SUCCESS}]Installed successfully.[/]")
            else:
                console.print(f"[{theme.WARNING}]Skipping - server not installed.[/]")
                return None

    # Collect credentials
    missing = configurator.get_missing_credentials(template)
    credentials: dict[str, str] = {}

    if missing:
        console.print(f"\n[{theme.HEADER}]Required credentials:[/]")
        for cred in missing:
            desc = template.credential_descriptions.get(cred, "")
            if desc:
                console.print(f"[{theme.DIM}]{desc}[/]")
            value = Prompt.ask(f"[{theme.MCP_NAME}]{cred}[/]", password=True)
            if not value:
                console.print(f"[{theme.WARNING}]Skipping - missing required credentials.[/]")
                return None
            credentials[cred] = value

    # Create and save config
    config = configurator.configure_from_template(template, credentials)
    console.print(f"[{theme.SUCCESS}]Configured '{template.name}' successfully.[/]")

    return config


def collect_mcp_credentials(
    missing_credentials: list[str],
    template: MCPServerTemplate | None = None,
    console: Console | None = None,
) -> dict[str, str]:
    """Collect credentials from user for MCP server.

    Args:
        missing_credentials: List of credential names to collect.
        template: Optional template for credential descriptions.
        console: Rich console for output.

    Returns:
        Dict of credential name -> value.
    """
    console = console or Console()
    credentials: dict[str, str] = {}

    for cred in missing_credentials:
        desc = ""
        if template:
            desc = template.credential_descriptions.get(cred, "")
        if desc:
            console.print(f"[{theme.DIM}]{desc}[/]")
        value = Prompt.ask(f"[{theme.MCP_NAME}]{cred}[/]", password=True)
        credentials[cred] = value

    return credentials
