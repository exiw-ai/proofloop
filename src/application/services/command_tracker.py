"""Track commands executed during agent sessions.

Provides context about what commands were run and their results,
enabling independent verifiers to make informed decisions.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.domain.ports.agent_port import AgentMessage


@dataclass
class CommandRecord:
    """Record of a single command execution."""

    command: str
    tool_name: str
    output: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def format_for_prompt(self) -> str:
        """Format for inclusion in verification prompt."""
        output_preview = ""
        if self.output:
            # Take last 200 chars of output as preview
            preview = self.output[-200:] if len(self.output) > 200 else self.output
            # Clean up for prompt
            preview = preview.strip()
            if preview:
                output_preview = f"\n   Output: {preview[:100]}..."

        return f"- {self.tool_name}: `{self.command}`{output_preview}"


class CommandTracker:
    """Tracks tool executions during agent sessions.

    Creates a factual log of what commands were run, to be passed to
    independent verifiers as context (not interpretation).
    """

    def __init__(self) -> None:
        self._records: list[CommandRecord] = []
        self._pending_command: str | None = None
        self._pending_tool: str | None = None

    def on_message(self, msg: AgentMessage) -> None:
        """Process agent message to track commands."""
        if msg.role == "tool_use" and msg.tool_name:
            self._handle_tool_use(msg)
        elif msg.role == "tool_result":
            self._handle_tool_result(msg)

    def _handle_tool_use(self, msg: AgentMessage) -> None:
        """Extract command from tool_use message."""
        if not msg.tool_input:
            return

        command: str | None = None
        tool_name = msg.tool_name or "unknown"

        if msg.tool_name == "Bash":
            command = str(msg.tool_input.get("command", ""))
        elif msg.tool_name == "Read" or msg.tool_name in ("Write", "Edit"):
            command = str(msg.tool_input.get("file_path", ""))
        elif msg.tool_name in ("Glob", "Grep"):
            pattern = msg.tool_input.get("pattern", "")
            path = msg.tool_input.get("path", ".")
            command = f"{pattern} in {path}"

        if command:
            self._pending_command = command
            self._pending_tool = tool_name

    def _handle_tool_result(self, msg: AgentMessage) -> None:
        """Record result for pending command."""
        if self._pending_command and self._pending_tool:
            self._records.append(
                CommandRecord(
                    command=self._pending_command,
                    tool_name=self._pending_tool,
                    output=msg.content,
                )
            )
        self._pending_command = None
        self._pending_tool = None

    def get_bash_commands(self) -> list[CommandRecord]:
        """Get only Bash command records."""
        return [r for r in self._records if r.tool_name == "Bash"]

    def get_all_records(self) -> list[CommandRecord]:
        """Get all command records."""
        return list(self._records)

    def format_for_verification(self, max_commands: int = 20) -> str:
        """Format command log for verification prompt.

        Returns factual summary of commands executed, prioritizing Bash
        commands as they're most relevant for verification.
        """
        bash_records = self.get_bash_commands()

        if not bash_records:
            return "No shell commands were executed during implementation."

        # Take most recent commands
        recent = bash_records[-max_commands:]

        lines = ["Commands executed during implementation:"]
        for record in recent:
            lines.append(record.format_for_prompt())

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all records."""
        self._records.clear()
        self._pending_command = None
        self._pending_tool = None
