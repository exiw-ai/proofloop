from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.text import Text

from src.domain.ports.agent_port import AgentMessage

# Current working directory for relative path display
_cwd: Path | None = None


def _make_relative(path: str) -> str:
    """Convert absolute path to relative if it's under cwd."""
    if not _cwd or not path:
        return path
    try:
        p = Path(path).resolve()
        rel = p.relative_to(_cwd)
        return str(rel)
    except ValueError:
        # Path is not relative to cwd
        return path


# Map tool names to display operation names (Claude Code style)
TOOL_OPERATIONS: dict[str, str] = {
    "Bash": "Run",
    "Read": "Read",
    "Write": "Write",
    "Edit": "Update",
    "Glob": "Search",
    "Grep": "Search",
    "WebFetch": "Fetch",
    "WebSearch": "Search",
    "LSP": "LSP",
    "TodoWrite": "Todo",
    "Task": "Agent",
    "NotebookEdit": "Update",
}

TODO_STATUS_ICONS: dict[str, tuple[str, str]] = {
    "completed": ("✓", "green"),
    "in_progress": ("⟳", "yellow"),
    "pending": ("○", "dim"),
}


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _shorten_paths_in_command(cmd: str) -> str:
    """Shorten absolute paths in a command to relative paths."""
    if not _cwd:
        return cmd

    cwd_str = str(_cwd)
    # Replace the cwd path with "." in the command
    if cwd_str in cmd:
        cmd = cmd.replace(cwd_str, ".")
        # Clean up double slashes
        cmd = cmd.replace("/./", "/").replace("//", "/")
    return cmd


def _get_tool_argument(tool_name: str, tool_input: dict[str, object] | None) -> str:
    """Extract the main argument for display in parentheses."""
    if not tool_input:
        return ""

    if tool_name == "Bash":
        cmd = str(tool_input.get("command", ""))
        # Shorten paths and truncate
        cmd = _shorten_paths_in_command(cmd)
        return cmd  # Will be truncated later in format_tool_use

    if tool_name == "Read":
        path = str(tool_input.get("file_path", ""))
        return _make_relative(path)

    if tool_name in ("Write", "Edit"):
        path = str(tool_input.get("file_path", ""))
        return _make_relative(path)

    if tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        path = str(tool_input.get("path", ""))
        rel_path = _make_relative(path) if path else ""
        if rel_path and rel_path != ".":
            return f"{pattern} in {rel_path}"
        return str(pattern)

    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        path = str(tool_input.get("path", ""))
        rel_path = _make_relative(path) if path else ""
        if rel_path and rel_path != ".":
            return f'"{pattern}" in {rel_path}'
        return f'"{pattern}"'

    if tool_name == "WebFetch":
        return str(tool_input.get("url", ""))

    if tool_name == "WebSearch":
        return str(tool_input.get("query", ""))

    if tool_name == "Task":
        return str(tool_input.get("description", ""))

    if tool_name == "NotebookEdit":
        path = str(tool_input.get("notebook_path", ""))
        return _make_relative(path)

    return ""


def _format_todo_item(todo: dict[str, object]) -> tuple[str, str, str]:
    """Format a single todo item.

    Returns (icon, color, content).
    """
    status = str(todo.get("status", "pending"))
    content = str(todo.get("activeForm") or todo.get("content", ""))
    icon, color = TODO_STATUS_ICONS.get(status, ("?", "white"))
    return icon, color, content


def _format_todowrite(console: Console, tool_input: dict[str, object] | None) -> None:
    """Format TodoWrite tool with nice todo list display."""
    if not tool_input:
        return

    todos = tool_input.get("todos", [])
    if not isinstance(todos, list):
        return

    # Header line - Claude Code style
    text = Text()
    text.append("⏺ ", style="bold cyan")
    text.append("Todo", style="bold white")
    text.append(f"({len(todos)} items)", style="white")
    console.print(text)

    # Todo items with ⎿ prefix
    for todo in todos:
        if not isinstance(todo, dict):
            continue
        icon, color, content = _format_todo_item(todo)
        console.print(f"  [dim]⎿[/]  [{color}]{icon}[/] {content}")


def _format_edit_result(console: Console, tool_input: dict[str, object] | None) -> None:
    """Format Edit result showing diff preview."""
    if not tool_input:
        return

    old_str = str(tool_input.get("old_string", ""))
    new_str = str(tool_input.get("new_string", ""))

    old_lines = old_str.splitlines()
    new_lines = new_str.splitlines()

    # Show diff preview (max 6 lines total)
    max_preview = 6
    shown = 0

    # Show removed lines
    for line in old_lines[: max_preview // 2]:
        console.print(f"  [dim]⎿[/]  [red]-[/] {line[:70]}")
        shown += 1

    # Show added lines
    for line in new_lines[: max_preview - shown]:
        console.print(f"  [dim]⎿[/]  [green]+[/] {line[:70]}")
        shown += 1

    # Indicate if there's more
    total = len(old_lines) + len(new_lines)
    if total > shown:
        console.print(f"  [dim]⎿[/]  [dim]... {total - shown} more lines[/]")


def format_assistant_message(console: Console, msg: AgentMessage) -> bool:  # noqa: ARG001
    """Display assistant text message with 💭 icon.

    Returns True if something was printed.
    """
    if not msg.content:
        return False

    content = msg.content.strip()
    if not content:
        return False

    # Skip JSON-like content (agent responses with structured data)
    if content.startswith("{") or content.startswith("["):
        return False

    # Skip markdown code blocks (especially ```json responses)
    if content.startswith("```"):
        return False

    # Skip if content is mostly JSON (contains typical JSON patterns)
    if '"source_types"' in content or '"queries"' in content or '"findings"' in content:
        return False

    # Skip very short content (likely internal)
    if len(content) < 20:
        return False

    # For research mode, skip agent reasoning/internal thoughts
    # Only show user-facing messages
    return False  # Disable assistant message display for cleaner output


def format_tool_use(console: Console, msg: AgentMessage) -> None:
    """Display tool invocation with clean formatting."""
    if not msg.tool_name:
        return

    # Special handling for TodoWrite
    if msg.tool_name == "TodoWrite":
        _format_todowrite(console, msg.tool_input)
        return

    operation = TOOL_OPERATIONS.get(msg.tool_name, msg.tool_name)
    argument = _get_tool_argument(msg.tool_name, msg.tool_input)

    # Build clean line with indentation: → Operation: argument
    text = Text()
    text.append("   ", style="")  # Indent to align with stage description
    text.append("→ ", style="cyan")
    text.append(operation, style="white")
    if argument:
        # Truncate long arguments (100 chars should fit most terminals)
        display_arg = _truncate(argument, 100)
        text.append(f": {display_arg}", style="dim")

    console.print(text)

    # For Edit, show changes summary immediately
    if msg.tool_name == "Edit" and msg.tool_input:
        _format_edit_result(console, msg.tool_input)


def format_tool_result(console: Console, msg: AgentMessage, tool_name: str | None = None) -> bool:
    """Display tool result summary (minimal, only for key tools).

    Returns True if something was printed.
    """
    # Skip most tool results for cleaner output
    # Only show results for tools where the result is important
    if tool_name in ("Edit", "TodoWrite", "Read", "WebFetch", "WebSearch"):
        return False

    if not msg.content:
        return False

    content = msg.content.strip()
    if not content:
        return False

    # Only show results for Glob/Grep (useful to know how many matches)
    if tool_name in ("Glob", "Grep"):
        lines = content.split("\n")
        count = len([line for line in lines if line.strip()])
        if tool_name == "Glob":
            console.print(f"   [dim]  ↳ {count} files[/]")
        else:
            console.print(f"   [dim]  ↳ {count} matches[/]")
        return True

    return False


def create_tool_callback(
    console: Console, cwd: str | None = None
) -> Callable[[AgentMessage], None]:
    """Factory to create a tool display callback for the given console.

    Args:
        console: Rich console for output
        cwd: Working directory for relative path display
    """
    global _cwd
    _cwd = Path(cwd).resolve() if cwd else Path.cwd()

    last_tool_name: list[str | None] = [None]

    def callback(msg: AgentMessage) -> None:
        if msg.role == "assistant" and msg.content and not msg.tool_name:
            # Skip assistant messages (JSON responses, reasoning)
            format_assistant_message(console, msg)
        elif msg.role == "tool_use" and msg.tool_name:
            last_tool_name[0] = msg.tool_name
            format_tool_use(console, msg)
        elif msg.role == "tool_result":
            tool = last_tool_name[0]
            format_tool_result(console, msg, tool)
            last_tool_name[0] = None

    return callback
