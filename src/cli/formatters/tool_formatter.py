from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.text import Text

from src.cli.theme import theme
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


# Map tool names to display operation names
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
    "completed": ("✓", theme.TODO_COMPLETED),
    "in_progress": ("⟳", theme.TODO_IN_PROGRESS),
    "pending": ("○", theme.TODO_PENDING),
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
    icon, color = TODO_STATUS_ICONS.get(status, ("?", theme.TEXT))
    return icon, color, content


def _format_todowrite(console: Console, tool_input: dict[str, object] | None) -> None:
    """Format TodoWrite tool with nice todo list display."""
    if not tool_input:
        return

    todos = tool_input.get("todos", [])
    if not isinstance(todos, list):
        return

    # Header line
    text = Text()
    text.append("⏺ ", style=theme.INFO_BOLD)
    text.append("Todo", style="bold " + theme.TEXT)
    text.append(f"({len(todos)} items)", style=theme.TEXT)
    console.print(text)

    # Todo items with ⎿ prefix
    for todo in todos:
        if not isinstance(todo, dict):
            continue
        icon, color, content = _format_todo_item(todo)
        console.print(f"  [{theme.DIM}]⎿[/]  [{color}]{icon}[/] {content}")


def _format_edit_result(console: Console, tool_input: dict[str, object] | None) -> None:
    """Format Edit result showing diff preview with colors."""
    if not tool_input:
        return

    old_str = str(tool_input.get("old_string", ""))
    new_str = str(tool_input.get("new_string", ""))

    old_lines = old_str.splitlines()
    new_lines = new_str.splitlines()

    # Summary line
    console.print(
        f"        [{theme.DIM}]⎿[/]  [{theme.DIM}]Removed {len(old_lines)} lines, added {len(new_lines)} lines[/]"
    )

    # Show diff preview (max 8 lines total)
    max_preview = 8
    shown = 0

    # Show removed lines in red
    for line in old_lines[: max_preview // 2]:
        console.print(
            f"        [{theme.DIM}]⎿[/]  [{theme.DIFF_REMOVE}]-[/] [{theme.DIFF_REMOVE}]{line[:70]}[/]"
        )
        shown += 1

    # Show added lines in green
    for line in new_lines[: max_preview - shown]:
        console.print(
            f"        [{theme.DIM}]⎿[/]  [{theme.DIFF_ADD}]+[/] [{theme.DIFF_ADD}]{line[:70]}[/]"
        )
        shown += 1

    # Indicate if there's more
    total = len(old_lines) + len(new_lines)
    if total > shown:
        console.print(f"        [{theme.DIM}]⎿[/]  [{theme.DIM}]... {total - shown} more lines[/]")


def format_thought(console: Console, msg: AgentMessage) -> bool:
    """Display agent thinking/reasoning with 💭 icon.

    Returns True if something was printed.
    """
    if not msg.content:
        return False

    content = msg.content.strip()
    if not content:
        return False

    # Clean up markdown formatting (** for bold)
    content = content.replace("**", "")

    # Truncate long thoughts
    if len(content) > 200:
        content = content[:200] + "..."

    # Empty line before thought for visual separation
    console.print()

    # Display thinking - white for readability
    text = Text()
    text.append("   ", style="")
    text.append(content, style=theme.TEXT)
    console.print(text)
    return True


def format_status(console: Console, msg: AgentMessage) -> bool:
    """Display status message (e.g., 'Agent is processing...').

    Returns True if something was printed.
    """
    if not msg.content:
        return False

    content = msg.content.strip()
    if not content:
        return False

    # Display status with dim styling
    text = Text()
    text.append("   ", style="")
    text.append("⏳ ", style=theme.DIM)
    text.append(content, style=theme.DIM_ITALIC)
    console.print(text)
    return True


def format_assistant_message(console: Console, msg: AgentMessage) -> bool:
    """Display assistant text message as thought.

    Returns True if something was printed.
    """
    from loguru import logger

    if not msg.content:
        return False

    content = msg.content.strip()
    if not content:
        return False

    # Skip JSON-like content (agent responses with structured data)
    if content.startswith("{") or content.startswith("["):
        logger.debug(f"[THOUGHT] Skipping JSON content: {content[:50]}...")
        return False

    # Skip markdown code blocks (especially ```json responses)
    if content.startswith("```"):
        logger.debug(f"[THOUGHT] Skipping code block: {content[:50]}...")
        return False

    # Skip if content is mostly JSON (contains typical JSON patterns)
    if '"source_types"' in content or '"queries"' in content or '"findings"' in content:
        logger.debug(f"[THOUGHT] Skipping JSON pattern: {content[:50]}...")
        return False

    # Skip very short content (single words like "OK", "Done")
    if len(content) < 5:
        logger.debug(f"[THOUGHT] Skipping short content: {content}")
        return False

    # Convert status markers to user-friendly icons
    if "CONDITION_PASS" in content:
        console.print(f"   [{theme.SUCCESS}]✓ Condition verified[/]")
        return True
    if "CONDITION_FAIL" in content:
        console.print(f"   [{theme.ERROR}]✗ Condition failed[/]")
        return True
    if "QUALITY_OK" in content:
        console.print(f"   [{theme.SUCCESS}]✓ Quality check passed[/]")
        return True

    # Show as thought - agent describing what it's doing
    logger.debug(f"[THOUGHT] Displaying: {content[:100]}...")

    # Clean up markdown formatting
    content = content.replace("**", "")

    # Truncate long content
    if len(content) > 200:
        content = content[:200] + "..."

    # Empty line before for visual separation
    console.print()

    # Display as thought
    text = Text()
    text.append("   ", style="")
    text.append(content, style=theme.TEXT)
    console.print(text)
    return True


def format_tool_use(
    console: Console, msg: AgentMessage, last_thought: list[str | None] | None = None
) -> None:
    """Display tool invocation with clean formatting."""
    if not msg.tool_name:
        return

    # Special handling for TodoWrite
    if msg.tool_name == "TodoWrite":
        _format_todowrite(console, msg.tool_input)
        return

    # Display description as thought if present (from tool_input)
    if msg.tool_input:
        description = msg.tool_input.get("description")
        # Skip if same as last thought (avoid duplicates)
        is_new_thought = last_thought is None or description != last_thought[0]
        if description and isinstance(description, str) and len(description) > 5 and is_new_thought:
            console.print()  # Empty line before description
            thought_text = Text()
            thought_text.append("   ", style="")
            thought_text.append(description, style=theme.TEXT)
            console.print(thought_text)
            if last_thought is not None:
                last_thought[0] = description

    operation = TOOL_OPERATIONS.get(msg.tool_name, msg.tool_name)
    argument = _get_tool_argument(msg.tool_name, msg.tool_input)

    # Build clean line: → ToolName(argument)
    # Arrow bold cyan (like stage headers), operation light_steel_blue, argument grey74
    text = Text()
    text.append("      ", style="")  # Extra indent to show under thoughts
    text.append("→ ", style=theme.INFO_BOLD)
    text.append(operation, style=theme.TOOL_OPERATION)
    if argument:
        # Truncate long arguments (80 chars)
        display_arg = _truncate(argument, 80)
        text.append("(", style=theme.DIM)
        text.append(display_arg, style=theme.TOOL_ARGS)
        text.append(")", style=theme.DIM)

    console.print(text)

    # For Edit, show changes summary immediately
    if msg.tool_name == "Edit" and msg.tool_input:
        _format_edit_result(console, msg.tool_input)


def format_tool_result(console: Console, msg: AgentMessage, tool_name: str | None = None) -> bool:
    """Display tool result summary with ⎿ prefix.

    Returns True if something was printed.
    """
    # Skip Edit (handled separately) and TodoWrite
    if tool_name in ("Edit", "TodoWrite"):
        return False

    if not msg.content:
        return False

    content = msg.content.strip()
    if not content:
        return False

    # Show results for different tools
    if tool_name in ("Glob", "Grep"):
        lines = content.split("\n")
        count = len([line for line in lines if line.strip()])
        if tool_name == "Glob":
            console.print(f"        [{theme.DIM}]⎿[/]  [{theme.DIM}]Found {count} files[/]")
        else:
            console.print(f"        [{theme.DIM}]⎿[/]  [{theme.DIM}]Found {count} matches[/]")
        return True

    if tool_name == "Read":
        lines = content.split("\n")
        count = len(lines)
        console.print(f"        [{theme.DIM}]⎿[/]  [{theme.DIM}]Read {count} lines[/]")
        return True

    if tool_name == "Bash":
        lines = content.split("\n")
        count = len([line for line in lines if line.strip()])
        if count > 0:
            console.print(f"        [{theme.DIM}]⎿[/]  [{theme.DIM}]{count} lines output[/]")
        return True

    if tool_name in ("WebFetch", "WebSearch"):
        console.print(f"        [{theme.DIM}]⎿[/]  [{theme.DIM}]Fetched content[/]")
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

    from loguru import logger

    last_tool_name: list[str | None] = [None]
    last_thought: list[str | None] = [None]  # Track last displayed thought to avoid duplicates

    def callback(msg: AgentMessage) -> None:
        logger.debug(f"[CALLBACK] {msg}")
        if msg.role == "status" and msg.content:
            format_status(console, msg)
        elif msg.role == "thought" and msg.content:
            # Skip if same as last thought (avoid duplicates)
            if msg.content != last_thought[0]:
                format_thought(console, msg)
                last_thought[0] = msg.content
        elif msg.role == "assistant" and msg.content and not msg.tool_name:
            # Skip if same as last thought (avoid duplicates)
            if msg.content != last_thought[0]:
                format_assistant_message(console, msg)
                last_thought[0] = msg.content
        elif msg.role == "tool_use" and msg.tool_name:
            last_tool_name[0] = msg.tool_name
            format_tool_use(console, msg, last_thought)
        elif msg.role == "tool_result":
            tool = last_tool_name[0]
            format_tool_result(console, msg, tool)
            last_tool_name[0] = None

    return callback
